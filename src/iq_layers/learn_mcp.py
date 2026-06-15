"""
Microsoft Learn MCP client (public knowledge layer).

A resilient, mockable client for the Microsoft Learn MCP Server — a remote,
streamable-HTTP, unauthenticated server exposing exactly three tools:

  * ``microsoft_docs_search(query)``        — semantic search over MS docs
  * ``microsoft_docs_fetch(url)``           — fetch a doc page as markdown
  * ``microsoft_code_sample_search(query, language?)`` — official code samples

Design goals (see the approved plan):

  * **Wrap the official ``mcp`` SDK**, not hand-roll the protocol. Tools are
    discovered at runtime via ``list_tools`` and the discovery is cached;
    a schema-shaped error refreshes it and retries once.
  * **Loop-aware sync facade** — the synchronous agents (Learning Path
    Curator) and the asyncio-based callers (Agent Framework graph, Streamlit)
    can both call ``search`` / ``fetch`` / ``code_search`` directly. When a
    running event loop is detected the coroutine is dispatched to a dedicated
    worker thread with its own loop (``asyncio.run`` raises inside a running
    loop).
  * **Never raises** — every failure (network, schema, parse) is caught,
    logged, and degraded to an empty result. The hybrid retriever above this
    layer falls back to the synthetic KB.
  * **24h TTL disk cache** in ``.cache/learn_mcp/`` keyed by tool+args; the
    cache stores text and source URLs (never written into ``data/``).
  * **Mockable transport** — a ``session_factory`` can be injected so the test
    suite runs with zero network.

Every returned chunk is tagged ``microsoft-learn-public`` with its source URL.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import threading
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator, Awaitable, Callable, List, Optional

from src.config import LearnMCPConfig, get_learn_mcp_config
from src.iq_layers.provenance import MICROSOFT_LEARN_PUBLIC, RetrievedChunk

logger = logging.getLogger("talentfabric.learn_mcp")

CACHE_DIR = Path(__file__).resolve().parent.parent.parent / ".cache" / "learn_mcp"

# Logical tool names (the server is the source of truth; these are the names we
# look for during runtime discovery).
TOOL_SEARCH = "microsoft_docs_search"
TOOL_FETCH = "microsoft_docs_fetch"
TOOL_CODE_SEARCH = "microsoft_code_sample_search"


# ---------------------------------------------------------------------------
# Loop-aware sync facade
# ---------------------------------------------------------------------------
def run_sync(make_coro: Callable[[], Awaitable[Any]]) -> Any:
    """Run an async coroutine from sync code, safe inside a running loop.

    ``make_coro`` is a zero-arg factory returning a *fresh* coroutine (so it
    can be created on whichever thread/loop ends up running it).

    * No running loop  → run on a throwaway loop via ``asyncio.run``.
    * Running loop     → dispatch to a dedicated worker thread with its own
      event loop and block on the result (``asyncio.run`` would otherwise
      raise ``RuntimeError: asyncio.run() cannot be called from a running
      event loop``).
    """
    try:
        asyncio.get_running_loop()
        in_running_loop = True
    except RuntimeError:
        in_running_loop = False

    if not in_running_loop:
        return asyncio.run(make_coro())

    box: dict[str, Any] = {}

    def _worker() -> None:
        try:
            box["result"] = asyncio.run(make_coro())
        except BaseException as exc:  # noqa: BLE001 - re-raised on the caller thread
            box["error"] = exc

    thread = threading.Thread(target=_worker, name="learn-mcp-sync", daemon=True)
    thread.start()
    thread.join()
    if "error" in box:
        raise box["error"]
    return box["result"]


# ---------------------------------------------------------------------------
# Disk cache
# ---------------------------------------------------------------------------
def _cache_key(tool: str, arguments: dict) -> str:
    payload = json.dumps({"tool": tool, "args": arguments}, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _cache_path(key: str) -> Path:
    return CACHE_DIR / f"{key}.json"


def _read_cache(key: str, ttl_hours: int) -> Optional[List[RetrievedChunk]]:
    path = _cache_path(key)
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        age_seconds = time.time() - raw["ts"]
        if age_seconds > ttl_hours * 3600:
            return None
        return [
            RetrievedChunk(
                text=c["text"],
                source_tier=MICROSOFT_LEARN_PUBLIC,
                source_ref=c["source_ref"],
                source_url=c.get("source_url"),
                score=c.get("score", 0.0),
            )
            for c in raw["chunks"]
        ]
    except (json.JSONDecodeError, KeyError, OSError) as exc:
        logger.debug("cache read failed for %s: %s", key, exc)
        return None


def _write_cache(key: str, chunks: List[RetrievedChunk]) -> None:
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        payload = {
            "ts": time.time(),
            "chunks": [
                {
                    "text": c.text,
                    "source_ref": c.source_ref,
                    "source_url": c.source_url,
                    "score": c.score,
                }
                for c in chunks
            ],
        }
        _cache_path(key).write_text(json.dumps(payload), encoding="utf-8")
    except OSError as exc:  # pragma: no cover - cache write failure is non-fatal
        logger.debug("cache write failed for %s: %s", key, exc)


# ---------------------------------------------------------------------------
# Result parsing
# ---------------------------------------------------------------------------
def _chunk_from_dict(item: dict, default_ref: str) -> RetrievedChunk:
    text = item.get("content") or item.get("text") or item.get("snippet") or ""
    url = item.get("contentUrl") or item.get("url") or item.get("source_url")
    title = item.get("title") or item.get("section") or item.get("name") or default_ref
    return RetrievedChunk(
        text=str(text).strip(),
        source_tier=MICROSOFT_LEARN_PUBLIC,
        source_ref=str(title),
        source_url=url,
    )


def _parse_tool_result(result: Any, default_ref: str) -> List[RetrievedChunk]:
    """Parse an MCP ``CallToolResult`` into provenance-tagged chunks.

    Handles the common Learn shapes defensively: a JSON array/object of
    ``{title, content, contentUrl}`` inside a text block, multiple text
    blocks, or ``structuredContent``.
    """
    chunks: List[RetrievedChunk] = []

    # structuredContent (when the server provides it)
    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict):
        items = structured.get("results") or structured.get("items")
        if isinstance(items, list):
            for it in items:
                if isinstance(it, dict):
                    chunks.append(_chunk_from_dict(it, default_ref))

    # text content blocks
    texts: List[str] = []
    for block in getattr(result, "content", None) or []:
        if getattr(block, "type", None) == "text" and getattr(block, "text", None):
            texts.append(block.text)

    parsed_any = bool(chunks)
    for text in texts:
        data: Any = None
        try:
            data = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            data = None
        if isinstance(data, list):
            for it in data:
                if isinstance(it, dict):
                    chunks.append(_chunk_from_dict(it, default_ref))
                    parsed_any = True
        elif isinstance(data, dict):
            chunks.append(_chunk_from_dict(data, default_ref))
            parsed_any = True

    if not parsed_any:
        for text in texts:
            chunks.append(
                RetrievedChunk(
                    text=text.strip(),
                    source_tier=MICROSOFT_LEARN_PUBLIC,
                    source_ref=default_ref,
                    source_url=None,
                )
            )

    return [c for c in chunks if c.text]


# ---------------------------------------------------------------------------
# Default (real) session factory
# ---------------------------------------------------------------------------
@asynccontextmanager
async def _default_session_factory(endpoint: str) -> AsyncIterator[Any]:
    """Open a real streamable-HTTP MCP session (lazy ``mcp`` import)."""
    from mcp import ClientSession

    # Prefer the current name; fall back to the older alias on older SDKs.
    try:
        from mcp.client.streamable_http import streamable_http_client as _http_client
    except ImportError:  # pragma: no cover - depends on installed mcp version
        from mcp.client.streamable_http import streamablehttp_client as _http_client

    async with _http_client(endpoint) as (read, write, _get_session_id):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


SessionFactory = Callable[[str], "AsyncIterator[Any]"]


@dataclass
class LearnMCPStats:
    """Lightweight per-client telemetry (consumed by the Phase 4 panel)."""

    calls: int = 0
    cache_hits: int = 0
    errors: int = 0
    last_latency_ms: float = 0.0
    total_latency_ms: float = 0.0

    def as_dict(self) -> dict:
        return {
            "calls": self.calls,
            "cache_hits": self.cache_hits,
            "errors": self.errors,
            "cache_hit_rate": round(self.cache_hits / self.calls, 3) if self.calls else 0.0,
            "avg_latency_ms": round(self.total_latency_ms / self.calls, 1) if self.calls else 0.0,
            "last_latency_ms": round(self.last_latency_ms, 1),
        }


class LearnMCPTelemetry:
    """Process-wide aggregate of Learn MCP activity, for the monitoring panel.

    Populated as a side effect of every client call so the Streamlit telemetry
    panel and the eval harness can report calls / cache-hit rate / latency
    without threading a client handle through the whole workflow.
    """

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.calls = 0
        self.cache_hits = 0
        self.errors = 0
        self.total_latency_ms = 0.0

    def record(self, *, cache_hit: bool = False, error: bool = False, latency_ms: float = 0.0) -> None:
        self.calls += 1
        if cache_hit:
            self.cache_hits += 1
        if error:
            self.errors += 1
        self.total_latency_ms += latency_ms

    def as_dict(self) -> dict:
        return {
            "calls": self.calls,
            "cache_hits": self.cache_hits,
            "errors": self.errors,
            "cache_hit_rate": round(self.cache_hits / self.calls, 3) if self.calls else 0.0,
            "avg_latency_ms": round(self.total_latency_ms / self.calls, 1) if self.calls else 0.0,
        }


_TELEMETRY = LearnMCPTelemetry()


def get_telemetry() -> LearnMCPTelemetry:
    """Return the process-wide Learn MCP telemetry aggregate."""
    return _TELEMETRY


def reset_telemetry() -> None:
    _TELEMETRY.reset()


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------
class LearnMCPClient:
    """Resilient, mockable Microsoft Learn MCP client.

    Args:
        config: resolved Learn MCP config; defaults to :func:`get_learn_mcp_config`.
        session_factory: async context-manager factory taking an endpoint and
            yielding a connected session (``list_tools`` / ``call_tool``).
            Inject a fake for tests; defaults to a real streamable-HTTP session.
        use_cache: enable the 24h disk cache (disabled in most tests).
    """

    def __init__(
        self,
        config: Optional[LearnMCPConfig] = None,
        session_factory: Optional[SessionFactory] = None,
        use_cache: bool = True,
    ) -> None:
        self._config = config or get_learn_mcp_config()
        self._session_factory = session_factory or _default_session_factory
        self._use_cache = use_cache
        self._discovered_tools: Optional[set[str]] = None
        self.stats = LearnMCPStats()

    # -- public, synchronous API --------------------------------------------
    def search(self, query: str) -> List[RetrievedChunk]:
        return self._call(TOOL_SEARCH, {"query": query}, default_ref="Microsoft Learn search")

    def fetch(self, url: str) -> List[RetrievedChunk]:
        return self._call(TOOL_FETCH, {"url": url}, default_ref=url)

    def code_search(self, query: str, language: Optional[str] = None) -> List[RetrievedChunk]:
        args: dict[str, Any] = {"query": query}
        if language:
            args["language"] = language
        return self._call(TOOL_CODE_SEARCH, args, default_ref="Microsoft Learn code sample")

    # -- internals -----------------------------------------------------------
    def _call(self, tool: str, arguments: dict, default_ref: str) -> List[RetrievedChunk]:
        """Never-raises wrapper: cache → live call → []."""
        self.stats.calls += 1
        key = _cache_key(tool, arguments)

        if self._use_cache:
            cached = _read_cache(key, self._config.cache_ttl_hours)
            if cached is not None:
                self.stats.cache_hits += 1
                _TELEMETRY.record(cache_hit=True)
                return cached

        start = time.perf_counter()
        error = False
        chunks: List[RetrievedChunk] = []
        try:
            chunks = run_sync(lambda: self._acall_with_discovery(tool, arguments, default_ref))
        except BaseException as exc:  # noqa: BLE001 - resilience boundary; never propagate
            error = True
            self.stats.errors += 1
            logger.warning("Learn MCP call failed (%s): %s — degrading to synthetic KB.", tool, exc)
        finally:
            elapsed = (time.perf_counter() - start) * 1000
            self.stats.last_latency_ms = elapsed
            self.stats.total_latency_ms += elapsed
            _TELEMETRY.record(error=error, latency_ms=elapsed)

        if self._use_cache and chunks:
            _write_cache(key, chunks)
        return chunks

    async def _acall_with_discovery(self, tool: str, arguments: dict, default_ref: str) -> List[RetrievedChunk]:
        """Open a session, ensure the tool exists, call it, parse; one retry on schema refresh."""
        async with self._session_factory(self._config.endpoint_with_budget) as session:
            await self._ensure_discovered(session)
            if self._discovered_tools and tool not in self._discovered_tools:
                # Re-discover once in case the cache is stale, then give up gracefully.
                self._discovered_tools = None
                await self._ensure_discovered(session)
                if self._discovered_tools and tool not in self._discovered_tools:
                    logger.warning("Tool %s not advertised by server; available=%s", tool, self._discovered_tools)
                    return []

            try:
                result = await session.call_tool(tool, arguments)
            except Exception as exc:  # schema drift / transient → refresh discovery, retry once
                logger.info("call_tool(%s) error %s — refreshing tool discovery and retrying.", tool, exc)
                self._discovered_tools = None
                await self._ensure_discovered(session)
                result = await session.call_tool(tool, arguments)

            if getattr(result, "isError", False):
                logger.warning("Learn MCP reported isError for %s", tool)
                return []
            return _parse_tool_result(result, default_ref)

    async def _ensure_discovered(self, session: Any) -> None:
        if self._discovered_tools is not None:
            return
        listing = await session.list_tools()
        tools = getattr(listing, "tools", None) or []
        self._discovered_tools = {getattr(t, "name", None) for t in tools if getattr(t, "name", None)}
