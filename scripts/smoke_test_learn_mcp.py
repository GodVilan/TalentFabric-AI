"""
Opt-in live smoke test for the Microsoft Learn MCP Server.

Hits the real, public endpoint (https://learn.microsoft.com/api/mcp) and
exercises all three tools. **Requires network** — run it yourself in a
networked environment; it is intentionally not part of the default test suite.

    python scripts/smoke_test_learn_mcp.py

Exits non-zero if the endpoint returns nothing for the search probe.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("LEARN_MCP_ENABLED", "true")

from src.config import get_learn_mcp_config  # noqa: E402
from src.iq_layers.learn_mcp import LearnMCPClient, get_telemetry  # noqa: E402


def main() -> int:
    cfg = get_learn_mcp_config()
    print(f"Endpoint: {cfg.endpoint_with_budget}\n")

    client = LearnMCPClient(use_cache=False)

    print("== microsoft_docs_search('AZ-204 Azure Functions triggers') ==")
    results = client.search("AZ-204 Azure Functions triggers")
    for r in results[:3]:
        print(f"  - {r.source_ref}\n      {r.source_url}\n      {r.text[:140].strip()}…")
    print(f"  ({len(results)} chunk(s))\n")

    print("== microsoft_code_sample_search('Azure Functions HTTP trigger', language='python') ==")
    samples = client.code_search("Azure Functions HTTP trigger", language="python")
    for r in samples[:2]:
        print(f"  - {r.source_ref}  {r.source_url or ''}")
    print(f"  ({len(samples)} sample(s))\n")

    if results:
        url = next((r.source_url for r in results if r.source_url), None)
        if url:
            print(f"== microsoft_docs_fetch('{url}') ==")
            fetched = client.fetch(url)
            print(f"  ({len(fetched)} chunk(s); {sum(len(c.text) for c in fetched)} chars)\n")

    print("Telemetry:", get_telemetry().as_dict())

    if not results:
        print("\nFAIL: search returned no results.", file=sys.stderr)
        return 1
    print("\nOK: live Microsoft Learn MCP endpoint reachable and returning grounded results.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
