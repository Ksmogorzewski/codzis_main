"""Self-contained DeepSeek client (copied from ModelTagowania/tagger/client.py).

Verbatim copy so the recommender has no runtime dependency on the ModelTagowania
package. The original in ModelTagowania/ is left untouched.
"""

from __future__ import annotations

import os

from openai import OpenAI

from .env import load_env_value

DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-flash"  # DeepSeek-V4.1-Flash-1017


def resolve_api_key(explicit: str | None = None) -> str:
    if explicit:
        return explicit.strip()
    key = os.environ.get("DEEPSEEK_API_KEY") or load_env_value("DEEPSEEK_API_KEY")
    if not key:
        raise RuntimeError(
            "No DeepSeek API key found. Set DEEPSEEK_API_KEY in the "
            "environment or add DEEPSEEK_API_KEY=... to the .env file."
        )
    return key.strip()


class DeepSeekClient:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = DEEPSEEK_BASE_URL,
        model: str = DEEPSEEK_MODEL,
        timeout: float = 120,
    ):
        self.base_url = base_url
        self.model = model
        self._client = OpenAI(
            api_key=resolve_api_key(api_key),
            base_url=base_url,
            timeout=timeout,
        )

    def chat(self, messages: list[dict], json_mode: bool = False, **kwargs):
        """Raw chat.completions.create call. Returns the OpenAI response object.

        Pass any standard params via kwargs (temperature, max_tokens, ...).
        json_mode=True sets response_format={'type': 'json_object'}.
        """
        params = {"model": self.model, "messages": messages}
        if json_mode:
            params["response_format"] = {"type": "json_object"}
        params.update(kwargs)
        return self._client.chat.completions.create(**params)

    def complete_text(self, messages: list[dict], **kwargs) -> str:
        """Convenience: return just the assistant's text content."""
        response = self.chat(messages, **kwargs)
        return response.choices[0].message.content
