"""Provider adapters for the AI Service. Plain HTTPS (standard library) so no extra dependency is needed.

Each adapter takes a system prompt and a user prompt and returns the model's text. The provider, model and
endpoint are admin settings (Configuration > AI); the API key comes from GPHA_AI_API_KEY in the environment.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

PROVIDERS = {
    "anthropic": "Anthropic (Claude) Messages API",
    "azure_openai": "Azure OpenAI (chat completions on a deployment)",
    "openai_compatible": "OpenAI-compatible endpoint (Ollama, LM Studio, vLLM, OpenAI)",
}


class AiError(Exception):
    """Raised with a plain message the user can act on."""


@dataclass(frozen=True)
class ProviderConfig:
    provider: str
    model: str
    base_url: str
    api_key: str
    timeout: int


def _post(url: str, headers: dict[str, str], body: dict, timeout: int) -> dict:
    # Only web addresses: file:, ftp: and other schemes would let the endpoint setting read local files.
    if urllib.parse.urlsplit(url).scheme not in ("http", "https"):
        raise AiError("The AI endpoint address must start with http:// or https://")
    data = json.dumps(body).encode()
    request = urllib.request.Request(url, data=data, method="POST",
                                     headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - admin-set URL
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise AiError(f"The AI provider refused the request (HTTP {exc.code}): {detail}") from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        reason = getattr(exc, "reason", exc)
        raise AiError(f"Could not reach the AI provider: {reason}") from None
    except ValueError:
        raise AiError("The AI provider returned a response that is not JSON") from None


def _anthropic(cfg: ProviderConfig, system: str, prompt: str) -> str:
    if not cfg.api_key:
        raise AiError("No API key: set GPHA_AI_API_KEY on the server")
    out = _post(cfg.base_url.rstrip("/") + "/v1/messages",
                {"x-api-key": cfg.api_key, "anthropic-version": "2023-06-01"},
                {"model": cfg.model, "max_tokens": 2000, "system": system,
                 "messages": [{"role": "user", "content": prompt}]}, cfg.timeout)
    return "".join(block.get("text", "") for block in out.get("content", []) if block.get("type") == "text")


def _chat_text(out: dict) -> str:
    try:
        return out["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError):
        raise AiError("The AI provider returned an unexpected response") from None


def _azure(cfg: ProviderConfig, system: str, prompt: str) -> str:
    if not cfg.api_key:
        raise AiError("No API key: set GPHA_AI_API_KEY on the server")
    url = (f"{cfg.base_url.rstrip('/')}/openai/deployments/{cfg.model}/chat/completions"
           "?api-version=2024-10-21")
    out = _post(url, {"api-key": cfg.api_key},
                {"messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
                 "max_tokens": 2000}, cfg.timeout)
    return _chat_text(out)


def _openai_compatible(cfg: ProviderConfig, system: str, prompt: str) -> str:
    base = cfg.base_url.rstrip("/")
    url = base + ("/chat/completions" if base.endswith("/v1") else "/v1/chat/completions")
    headers = {"Authorization": f"Bearer {cfg.api_key}"} if cfg.api_key else {}
    out = _post(url, headers,
                {"model": cfg.model, "messages": [{"role": "system", "content": system},
                                                  {"role": "user", "content": prompt}], "max_tokens": 2000},
                cfg.timeout)
    return _chat_text(out)


ADAPTERS = {"anthropic": _anthropic, "azure_openai": _azure, "openai_compatible": _openai_compatible}


def complete(cfg: ProviderConfig, system: str, prompt: str) -> str:
    adapter = ADAPTERS.get(cfg.provider)
    if adapter is None:
        raise AiError(f"Unknown AI provider '{cfg.provider}'. Use one of: {', '.join(PROVIDERS)}")
    return adapter(cfg, system, prompt).strip()
