"""Optional Groq generation, used only when explicitly enabled in .env.

No Groq SDK required: uses Python stdlib and the official chat completions API.
No prompt, bearer key, or response body is printed as an exception or logged.
External cloud processing is opt-in, controlled by the administrator's .env.
"""
from __future__ import annotations

import json
import socket
from urllib import error, request

from config.chat_assistant_settings import get_chat_assistant_settings
from services.runtime_connection_service import (
    RuntimeServiceResponseError,
    RuntimeServiceTimeoutError,
    RuntimeServiceUnavailableError,
)

# Fixed HTTPS endpoint (not configurable to an arbitrary URL).
GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"


class GroqClient:
    def __init__(self) -> None:
        self.settings = get_chat_assistant_settings()

    def check_available(self) -> None:
        """Validate local configuration without transmitting any company data."""
        key = self.settings.groq_api_key.get_secret_value().strip()
        if not key or key.casefold() in {"your_groq_api_key", "your-secret-key", "replace_me"}:
            raise RuntimeServiceUnavailableError("groq")
        if not str(self.settings.groq_model or "").strip():
            raise RuntimeServiceResponseError("groq", detail="Groq model is not configured")

    def generate(
        self,
        prompt: str,
        *,
        quality: bool = False,
        timeout_seconds: float | None = None,
    ) -> str | None:
        self.check_available()
        settings = self.settings
        timeout = float(
            timeout_seconds if timeout_seconds is not None
            else settings.groq_timeout_seconds
        )
        if not 1 <= timeout <= 300:
            raise ValueError("Groq timeout must be 1 to 300 seconds")
        token_budget = int(
            settings.quality_max_tokens if quality else settings.standard_max_tokens
        )
        payload = {
            "model": str(settings.groq_model).strip(),
            "messages": [
                {"role": "system", "content": (
                    "Answer company HR questions ONLY from the authorized evidence "
                    "provided in the user prompt. Never assume external HR policies "
                    "or reveal secrets or information from another company."
                )},
                {"role": "user", "content": prompt},
            ],
            "temperature": float(settings.temperature),
            "max_completion_tokens": token_budget,
            "stream": False,
        }
        # Keep authorization header and full evidence out of traces/errors.
        req = request.Request(
            GROQ_CHAT_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": "Bearer " + settings.groq_api_key.get_secret_value().strip(),
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=timeout) as response:
                data = json.loads(response.read(2_000_000).decode("utf-8"))
        except error.HTTPError as exc:
            # Never expose the raw body: upstream could echo a prompt or key.
            raise RuntimeServiceResponseError(
                "groq", status_code=int(exc.code),
                detail=f"HTTP {int(exc.code)}", cause=None,
            ) from None
        except (error.URLError, TimeoutError, OSError) as exc:
            reason = getattr(exc, "reason", None)
            if isinstance(exc, (TimeoutError, socket.timeout)) or isinstance(reason, (TimeoutError, socket.timeout)):
                raise RuntimeServiceTimeoutError(
                    "groq", operation="generation", timeout_seconds=timeout,
                ) from None
            raise RuntimeServiceUnavailableError("groq") from None
        except (ValueError, json.JSONDecodeError):
            raise RuntimeServiceResponseError("groq", detail="Invalid JSON") from None
        try:
            content = data["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                raise TypeError("No completion text")
            # Compatible with the local generation cleanup applied by portal_ai.
            from modules.smart_ai.portal_ai import _clean_model_answer
            answer = _clean_model_answer(content)
            if not answer:
                raise ValueError("Empty completion")
            return answer
        except (KeyError, IndexError, TypeError, ValueError):
            raise RuntimeServiceResponseError(
                "groq", detail="Missing completion text",
            ) from None
