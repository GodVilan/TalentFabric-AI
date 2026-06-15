"""
Tests for the resilient Microsoft Learn MCP client (mocked transport).

These run with **zero network**: a fake session factory stands in for the real
streamable-HTTP session. Live endpoint checks live in the opt-in
``pytest -m live`` suite (Phase 4).
"""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager

import pytest

from src.config import LearnMCPConfig
from src.iq_layers.learn_mcp import LearnMCPClient, run_sync
from src.iq_layers.provenance import MICROSOFT_LEARN_PUBLIC


# --- fakes -----------------------------------------------------------------
class _FakeTool:
    def __init__(self, name: str) -> None:
        self.name = name


class _FakeListToolsResult:
    def __init__(self, names: list[str]) -> None:
        self.tools = [_FakeTool(n) for n in names]


class _FakeText:
    type = "text"

    def __init__(self, text: str) -> None:
        self.text = text


class _FakeCallToolResult:
    def __init__(self, content, is_error: bool = False, structured=None) -> None:
        self.content = content
        self.isError = is_error
        self.structuredContent = structured


class FakeSession:
    def __init__(self, tools: list[str], responses: dict) -> None:
        self._tools = tools
        self._responses = responses
        self.calls: list[tuple] = []

    async def initialize(self) -> None:  # noqa: D401
        pass

    async def list_tools(self):
        return _FakeListToolsResult(self._tools)

    async def call_tool(self, name, arguments=None):
        self.calls.append((name, arguments))
        resp = self._responses[name]
        if isinstance(resp, Exception):
            raise resp
        return resp


def _factory(session: FakeSession):
    @asynccontextmanager
    async def factory(endpoint: str):
        yield session

    return factory


def _config() -> LearnMCPConfig:
    return LearnMCPConfig(
        enabled=True,
        endpoint="https://learn.microsoft.com/api/mcp",
        max_token_budget=4000,
        cache_ttl_hours=24,
    )


def _search_response(url="https://learn.microsoft.com/azure/azure-functions/"):
    payload = [
        {"title": "Azure Functions overview", "content": "Serverless compute on Azure.", "contentUrl": url},
        {"title": "Triggers and bindings", "content": "How functions are invoked.", "contentUrl": url + "triggers/"},
    ]
    return _FakeCallToolResult(content=[_FakeText(json.dumps(payload))])


# --- tests -----------------------------------------------------------------
def test_search_returns_public_tagged_chunks_with_urls():
    session = FakeSession(
        tools=["microsoft_docs_search", "microsoft_docs_fetch", "microsoft_code_sample_search"],
        responses={"microsoft_docs_search": _search_response()},
    )
    client = LearnMCPClient(config=_config(), session_factory=_factory(session), use_cache=False)

    chunks = client.search("azure functions")

    assert len(chunks) == 2
    assert all(c.source_tier == MICROSOFT_LEARN_PUBLIC for c in chunks)
    assert all(c.source_url and c.source_url.startswith("https://learn.microsoft.com") for c in chunks)
    assert chunks[0].source_ref == "Azure Functions overview"
    assert session.calls == [("microsoft_docs_search", {"query": "azure functions"})]


def test_search_from_running_loop_does_not_raise():
    """The loop-aware sync facade must work when called inside a running loop."""
    session = FakeSession(
        tools=["microsoft_docs_search"],
        responses={"microsoft_docs_search": _search_response()},
    )
    client = LearnMCPClient(config=_config(), session_factory=_factory(session), use_cache=False)

    async def caller():
        # Calling the *sync* API from within an async context (running loop).
        return client.search("functions")

    chunks = asyncio.run(caller())
    assert chunks and chunks[0].is_public


def test_client_never_raises_on_transport_failure():
    @asynccontextmanager
    async def exploding_factory(endpoint: str):
        raise ConnectionError("network down")
        yield  # pragma: no cover

    client = LearnMCPClient(config=_config(), session_factory=exploding_factory, use_cache=False)
    assert client.search("anything") == []
    assert client.stats.errors == 1


def test_client_handles_tool_error_result():
    session = FakeSession(
        tools=["microsoft_docs_search"],
        responses={"microsoft_docs_search": _FakeCallToolResult(content=[], is_error=True)},
    )
    client = LearnMCPClient(config=_config(), session_factory=_factory(session), use_cache=False)
    assert client.search("x") == []


def test_missing_tool_degrades_to_empty():
    session = FakeSession(
        tools=["some_other_tool"],  # search not advertised
        responses={},
    )
    client = LearnMCPClient(config=_config(), session_factory=_factory(session), use_cache=False)
    assert client.search("x") == []


def test_call_tool_error_triggers_discovery_refresh_and_retry():
    # First call_tool raises, second (after refresh) succeeds.
    class FlakySession(FakeSession):
        def __init__(self):
            super().__init__(["microsoft_docs_search"], {})
            self._attempts = 0

        async def call_tool(self, name, arguments=None):
            self.calls.append((name, arguments))
            self._attempts += 1
            if self._attempts == 1:
                raise RuntimeError("schema mismatch (400)")
            return _search_response()

    session = FlakySession()
    client = LearnMCPClient(config=_config(), session_factory=_factory(session), use_cache=False)
    chunks = client.search("retry me")
    assert len(chunks) == 2
    assert session._attempts == 2  # retried after refresh


def test_run_sync_outside_loop_returns_value():
    async def coro():
        return 42

    assert run_sync(lambda: coro()) == 42
