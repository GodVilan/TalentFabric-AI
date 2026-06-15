"""
Foundry IQ layer (local stand-in).

Suggested implementation pattern (from the challenge starter kit):
    "Use Foundry IQ as the grounded knowledge layer for the Learning Path
    Curator and Assessment Agent. Create a knowledge base from synthetic
    guidance docs ... connect one or more agents to that knowledge base ...
    require the agent to cite source content."

This module provides a permission-free, local equivalent of Foundry IQ's
agentic, cited retrieval: it loads the synthetic markdown documents in
data/knowledge_base, splits them into headed sections, and performs hybrid
retrieval combining:

  - BM25 (sparse / lexical) via rank_bm25
  - TF-IDF cosine similarity (dense-ish / semantic) via scikit-learn

Every result returned includes a `source` (document) and `section`
(heading) so that downstream agents can cite their grounding, mirroring
Foundry IQ's "permission-aware, grounded answers with citations" behaviour.

Production migration path
--------------------------
To move this to real Foundry IQ:
  1. Upload the markdown files in data/knowledge_base to a Foundry IQ
     knowledge source (Azure Blob Storage / SharePoint / OneLake).
  2. Create a Foundry IQ knowledge base referencing that source.
  3. Replace `FoundryIQ.query()` below with a call to the Foundry IQ
     agentic retrieval API, keeping the same return shape
     (list of {source, section, text, score}).

To upgrade the local retriever to dense embeddings (e.g. BGE-large-en +
FAISS, as used in the arXiv Agent project), replace the TF-IDF vectorizer
with a sentence-embedding model and a FAISS index, keeping the same hybrid
scoring approach (normalize + combine with BM25).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from rank_bm25 import BM25Okapi
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from src.config import get_learn_mcp_config
from src.iq_layers.provenance import (
    MICROSOFT_LEARN_PUBLIC,
    SYNTHETIC_INTERNAL,
    RetrievedChunk,
    SourceTier,
)

logger = logging.getLogger("talentfabric.foundry_iq")

# Reciprocal-rank-fusion constant (standard default).
RRF_K = 60
# Pseudo-document name used for Microsoft Learn results mapped into a
# RetrievalResult, so the existing source -> section citation scheme still holds.
LEARN_SOURCE = "microsoft-learn"


@dataclass
class Chunk:
    source: str
    section: str
    text: str


@dataclass
class RetrievalResult:
    source: str
    section: str
    text: str
    score: float
    source_tier: SourceTier = SYNTHETIC_INTERNAL
    source_url: Optional[str] = None

    def citation(self) -> str:
        base = f"{self.source} \u2192 {self.section}"
        if self.source_url:
            return f"{base} ({self.source_url})"
        return base


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _split_into_chunks(path: Path) -> List[Chunk]:
    """Split a markdown file into chunks on '## ' headings."""
    text = path.read_text(encoding="utf-8")
    source = path.stem

    # Split on level-2 headings, keeping the heading with its body.
    parts = re.split(r"\n(?=## )", text)
    chunks: List[Chunk] = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        lines = part.splitlines()
        heading = lines[0].lstrip("# ").strip() if lines[0].startswith("#") else lines[0].strip()
        body = "\n".join(lines[1:]).strip()
        if not body:
            continue
        chunks.append(Chunk(source=source, section=heading, text=body))
    return chunks


class FoundryIQ:
    """Foundry IQ stand-in: local hybrid retrieval, optionally fused with the
    Microsoft Learn MCP public knowledge layer.

    With ``LEARN_MCP_ENABLED`` off (default), behaviour is identical to the
    pure-synthetic retriever: BM25 + TF-IDF over the local knowledge base.
    With it on, results are fused (reciprocal-rank fusion) with live Microsoft
    Learn results, each tagged with its provenance tier and source URL. The
    Learn side never raises — a failure or empty result degrades cleanly to the
    synthetic-only path (three-tier fallback: Learn MCP -> synthetic KB ->
    empty-but-valid).

    Args:
        knowledge_base_dir: directory of synthetic markdown docs.
        learn_client: optional injected Learn MCP client (for tests); created
            lazily only when the toggle is on.
    """

    def __init__(self, knowledge_base_dir: str | Path, learn_client: object | None = None):
        self.knowledge_base_dir = Path(knowledge_base_dir)
        self._learn_client = learn_client
        self.chunks: List[Chunk] = []
        for md_path in sorted(self.knowledge_base_dir.glob("*.md")):
            self.chunks.extend(_split_into_chunks(md_path))

        if not self.chunks:
            raise ValueError(f"No markdown chunks found in {knowledge_base_dir}")

        corpus_texts = [f"{c.section}. {c.text}" for c in self.chunks]

        # Sparse retriever
        tokenized_corpus = [_tokenize(t) for t in corpus_texts]
        self._bm25 = BM25Okapi(tokenized_corpus)

        # Dense-ish retriever
        self._vectorizer = TfidfVectorizer(stop_words="english")
        self._tfidf_matrix = self._vectorizer.fit_transform(corpus_texts)

    def query(
        self,
        query_text: str,
        top_k: int = 3,
        boost_sources: List[str] | None = None,
        boost_amount: float = 0.5,
    ) -> List[RetrievalResult]:
        """Return grounded, provenance-tagged results for ``query_text``.

        With the Learn MCP toggle **off** this is exactly the original local
        BM25 + TF-IDF retrieval. With it **on**, local results are fused with
        Microsoft Learn results via reciprocal-rank fusion; the Learn side
        degrades silently to synthetic-only on any failure or empty response.

        ``boost_sources`` is a lightweight grounding filter on the *local*
        retriever: chunks whose source document is in this list get a score
        boost, mirroring how Foundry IQ scopes retrieval to permitted sources.
        """
        config = get_learn_mcp_config()
        if not config.enabled:
            return self._local_query(query_text, top_k, boost_sources, boost_amount)

        # Hybrid path: pull a larger local pool for fusion candidates.
        pool = max(top_k * 2, 6)
        local_results = self._local_query(query_text, pool, boost_sources, boost_amount)
        learn_results = self._learn_query(query_text, top_k=pool)

        if not learn_results:
            # Tier 2 fallback: synthetic-only, trimmed to the requested top_k.
            return local_results[:top_k]

        return _reciprocal_rank_fusion(local_results, learn_results, top_k)

    def _get_learn_client(self):
        """Lazily construct the Learn MCP client (only reached when enabled)."""
        if self._learn_client is None:
            from src.iq_layers.learn_mcp import LearnMCPClient

            self._learn_client = LearnMCPClient()
        return self._learn_client

    def _learn_query(self, query_text: str, top_k: int) -> List[RetrievalResult]:
        """Query Microsoft Learn and map results into RetrievalResults.

        Never raises — the client itself is resilient, and this method guards
        any mapping error, returning ``[]`` so the caller degrades to local.
        """
        try:
            chunks: List[RetrievedChunk] = self._get_learn_client().search(query_text)
        except Exception as exc:  # noqa: BLE001 - defensive; client already never-raises
            logger.warning("Learn query failed: %s — using synthetic KB only.", exc)
            return []

        results: List[RetrievalResult] = []
        for c in chunks[:top_k]:
            results.append(
                RetrievalResult(
                    source=LEARN_SOURCE,
                    section=c.source_ref,
                    text=c.text,
                    score=c.score,
                    source_tier=MICROSOFT_LEARN_PUBLIC,
                    source_url=c.source_url,
                )
            )
        return results

    def _local_query(
        self,
        query_text: str,
        top_k: int = 3,
        boost_sources: List[str] | None = None,
        boost_amount: float = 0.5,
    ) -> List[RetrievalResult]:
        """Local BM25 + TF-IDF hybrid retrieval over the synthetic KB."""
        tokenized_query = _tokenize(query_text)

        bm25_scores = self._bm25.get_scores(tokenized_query)
        bm25_max = max(bm25_scores) or 1.0
        bm25_norm = [s / bm25_max for s in bm25_scores]

        query_vec = self._vectorizer.transform([query_text])
        tfidf_scores = cosine_similarity(query_vec, self._tfidf_matrix)[0]
        tfidf_max = max(tfidf_scores) or 1.0
        tfidf_norm = [s / tfidf_max for s in tfidf_scores]

        combined = [0.5 * b + 0.5 * t for b, t in zip(bm25_norm, tfidf_norm)]

        if boost_sources:
            combined = [
                score + boost_amount if chunk.source in boost_sources else score
                for chunk, score in zip(self.chunks, combined)
            ]

        ranked = sorted(
            zip(self.chunks, combined), key=lambda pair: pair[1], reverse=True
        )

        results: List[RetrievalResult] = []
        for chunk, score in ranked[:top_k]:
            results.append(
                RetrievalResult(
                    source=chunk.source,
                    section=chunk.section,
                    text=chunk.text,
                    score=round(float(score), 4),
                )
            )
        return results


def _fusion_key(r: RetrievalResult) -> str:
    """Stable identity for dedupe/fusion: URL if present, else source::section."""
    return r.source_url or f"{r.source}::{r.section}"


def _reciprocal_rank_fusion(
    local_results: List[RetrievalResult],
    learn_results: List[RetrievalResult],
    top_k: int,
) -> List[RetrievalResult]:
    """Fuse two ranked lists with reciprocal-rank fusion (RRF).

    RRF score for an item = sum over the lists it appears in of
    ``1 / (RRF_K + rank)``. This blends the local synthetic retriever and the
    Microsoft Learn results without needing comparable raw score scales, and
    naturally interleaves both provenance tiers. Items are deduped by
    :func:`_fusion_key`; the surfaced ``score`` becomes the (rounded) RRF score.
    """
    fused: dict[str, RetrievalResult] = {}
    scores: dict[str, float] = {}

    for ranked_list in (local_results, learn_results):
        for rank, result in enumerate(ranked_list):
            key = _fusion_key(result)
            scores[key] = scores.get(key, 0.0) + 1.0 / (RRF_K + rank)
            if key not in fused:
                fused[key] = result

    ordered = sorted(fused.values(), key=lambda r: scores[_fusion_key(r)], reverse=True)
    for r in ordered:
        r.score = round(scores[_fusion_key(r)], 6)
    return ordered[:top_k]
