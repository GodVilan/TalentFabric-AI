"""
Shared provenance types for the retrieval layer.

This module defines the single, shared chunk type that *both* the local
synthetic retriever (Foundry IQ stand-in) and the Microsoft Learn MCP client
emit, so that every piece of retrieved knowledge carries an explicit
provenance tag and (for public content) its source URL.

Provenance serves two purposes:

  1. **Reasoning** — agents can weigh authoritative public docs against the
     organisation's synthetic internal knowledge base.
  2. **Compliance** — it is the audit trail that keeps the two content
     categories strictly separated (see the "two-category model" in the
     README / docs/ARCHITECTURE.md). Synthetic record files in ``data/`` must
     never be polluted with public Learn content, and the
     :func:`assert_not_public` guard enforces that on any ``data/`` write
     path.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

# The only two content tiers the system recognises.
SourceTier = Literal["synthetic-internal", "microsoft-learn-public"]

SYNTHETIC_INTERNAL: SourceTier = "synthetic-internal"
MICROSOFT_LEARN_PUBLIC: SourceTier = "microsoft-learn-public"


@dataclass
class RetrievedChunk:
    """A single retrieved passage with explicit provenance.

    Attributes:
        text: The passage body.
        source_tier: Which content category this came from.
        source_ref: A human-readable reference — for synthetic content this is
            ``"<document> → <section>"`` (preserving the existing citation
            scheme); for Learn content it is the doc title/section.
        source_url: The public URL for Learn content; ``None`` for synthetic
            internal content (which has no public URL by design).
        score: Optional relevance score (normalised), used by fusion.
    """

    text: str
    source_tier: SourceTier
    source_ref: str
    source_url: str | None = None
    score: float = 0.0

    def citation(self) -> str:
        """Return a display citation, appending the URL for public content."""
        if self.source_url:
            return f"{self.source_ref} ({self.source_url})"
        return self.source_ref

    @property
    def is_public(self) -> bool:
        return self.source_tier == MICROSOFT_LEARN_PUBLIC


class ProvenanceViolationError(RuntimeError):
    """Raised when public Learn content would be written into ``data/``."""


def assert_not_public(chunk: RetrievedChunk | dict) -> None:
    """Guard: reject any attempt to persist public content into ``data/``.

    Call this on any code path that serialises content into the synthetic
    record files. Accepts either a :class:`RetrievedChunk` or a dict carrying
    a ``source_tier`` key, so it can guard loosely-typed payloads too.
    """
    tier = chunk.source_tier if isinstance(chunk, RetrievedChunk) else chunk.get("source_tier")
    if tier == MICROSOFT_LEARN_PUBLIC:
        raise ProvenanceViolationError(
            "Refusing to write microsoft-learn-public content into a synthetic "
            "data/ record. Public Learn content may only flow through the "
            "retrieval/citation layer, never into data/."
        )
