"""
Shared LLM chat client used by all five agents.

Design goal: every agent's *grounded reasoning* (retrieval, readiness
scoring, scheduling, aggregation) is implemented as deterministic Python
logic against the IQ layers in src/iq_layers/. The chat client is used only
to turn that grounded, structured result into a natural-language narrative
for the demo UI.

This keeps the system:
  - Runnable end-to-end with no API keys (MockChatClient), which is useful
    for development, testing, and the evaluation harness.
  - Upgradeable to Microsoft Foundry-hosted models or Azure OpenAI by
    setting the environment variables below, satisfying the
    "Use Microsoft Foundry (UI or SDK) and/or the Microsoft Agent
    Framework" requirement once credentials are supplied.

Environment variables (see .env.example)
------------------------------------------
Option A -- Microsoft Foundry (new /openai/v1 unified endpoint):
  AZURE_OPENAI_ENDPOINT      e.g. https://<resource>.openai.azure.com/openai/v1
  AZURE_OPENAI_API_KEY
  AZURE_OPENAI_DEPLOYMENT    e.g. gpt-4o

  Note: the Foundry /openai/v1 endpoint uses the plain OpenAI API format
  (not the Azure-specific api-version query param), so this client uses the
  standard openai.OpenAI class, not AzureOpenAI.

Option B -- GitHub Models (free, no Azure quota required):
  GITHUB_MODELS_TOKEN        a GitHub PAT with the `models:read` permission
  GITHUB_MODELS_MODEL        defaults to "openai/gpt-4o-mini"

If neither is configured (or a call fails), narration falls back to
templated text -- the grounded reasoning is identical either way.
"""

from __future__ import annotations

import os
from typing import Optional

# Load .env automatically so credentials are picked up whether the user
# sets them in the shell or in a .env file at the project root.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed; env vars must be set in the shell


class ChatClient:
    """Interface: returns a narrative string, or None if unavailable."""

    def complete(self, system_prompt: str, user_prompt: str) -> Optional[str]:
        raise NotImplementedError


class MockChatClient(ChatClient):
    """Offline fallback. Returns None so agents use their templated narrative."""

    def complete(self, system_prompt: str, user_prompt: str) -> Optional[str]:
        return None


class FoundryChatClient(ChatClient):
    """
    Chat client for Microsoft Foundry's /openai/v1 unified endpoint.

    Foundry's new inference URL (e.g. https://<resource>.openai.azure.com/openai/v1)
    speaks plain OpenAI API format -- no api-version query parameter, and the
    standard openai.OpenAI class (not AzureOpenAI) is the right client.

    Environment variables:
        AZURE_OPENAI_ENDPOINT     Full endpoint URL including /openai/v1
        AZURE_OPENAI_API_KEY      API key from Foundry -> Keys and Endpoint
        AZURE_OPENAI_DEPLOYMENT   Model deployment name, e.g. gpt-4o
    """

    def __init__(self):
        from openai import OpenAI

        endpoint = os.getenv("AZURE_OPENAI_ENDPOINT") or os.getenv("AZURE_AI_PROJECT_ENDPOINT")
        api_key = os.getenv("AZURE_OPENAI_API_KEY")
        deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT") or os.getenv("AZURE_AI_MODEL_DEPLOYMENT")

        if not (endpoint and api_key and deployment):
            raise RuntimeError("AZURE_OPENAI_ENDPOINT / AZURE_OPENAI_API_KEY / AZURE_OPENAI_DEPLOYMENT not fully set")

        # Ensure the base_url ends with / so the OpenAI SDK appends
        # /chat/completions correctly.
        base_url = endpoint.rstrip("/") + "/"

        self._deployment = deployment
        self._client = OpenAI(base_url=base_url, api_key=api_key)

    def complete(self, system_prompt: str, user_prompt: str) -> Optional[str]:
        try:
            response = self._client.chat.completions.create(
                model=self._deployment,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
                max_tokens=400,
            )
            return response.choices[0].message.content
        except Exception as e:
            # Surface the error to stderr so it's visible during development,
            # then fall back gracefully to the agent's templated narrative.
            import sys
            print(f"[FoundryChatClient] call failed: {e}", file=sys.stderr)
            return None


class GitHubModelsChatClient(ChatClient):
    """
    Thin wrapper around the GitHub Models free inference API.

    Environment variables:
        GITHUB_MODELS_TOKEN   A GitHub PAT with the `models:read` permission
        GITHUB_MODELS_MODEL   Defaults to "openai/gpt-4o-mini"
    """

    def __init__(self):
        from openai import OpenAI

        token = os.getenv("GITHUB_MODELS_TOKEN")
        if not token:
            raise RuntimeError("GITHUB_MODELS_TOKEN not set")

        self._model = os.getenv("GITHUB_MODELS_MODEL", "openai/gpt-4o-mini")
        self._client = OpenAI(base_url="https://models.github.ai/inference", api_key=token)

    def complete(self, system_prompt: str, user_prompt: str) -> Optional[str]:
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
                max_tokens=400,
            )
            return response.choices[0].message.content
        except Exception as e:
            import sys
            print(f"[GitHubModelsChatClient] call failed: {e}", file=sys.stderr)
            return None


def get_chat_client() -> ChatClient:
    """
    Return the best available chat client.

    Priority:
      1. Microsoft Foundry / Azure OpenAI  (AZURE_OPENAI_ENDPOINT set)
      2. GitHub Models                      (GITHUB_MODELS_TOKEN set)
      3. MockChatClient                     (templated narration, no LLM)

    Prints which client was selected so it's visible on startup.
    """
    import sys

    if (os.getenv("AZURE_OPENAI_ENDPOINT") or os.getenv("AZURE_AI_PROJECT_ENDPOINT")) and os.getenv("AZURE_OPENAI_API_KEY"):
        try:
            client = FoundryChatClient()
            print("[LLM] Using Microsoft Foundry / Azure OpenAI for narration.", file=sys.stderr)
            return client
        except Exception as e:
            print(f"[LLM] FoundryChatClient init failed: {e} -- trying GitHub Models.", file=sys.stderr)

    if os.getenv("GITHUB_MODELS_TOKEN"):
        try:
            client = GitHubModelsChatClient()
            print("[LLM] Using GitHub Models for narration.", file=sys.stderr)
            return client
        except Exception as e:
            print(f"[LLM] GitHubModelsChatClient init failed: {e} -- falling back to mock.", file=sys.stderr)

    print("[LLM] No credentials found -- using templated narration (MockChatClient).", file=sys.stderr)
    return MockChatClient()
