import logging
import time
from typing import List, Dict

from openai import (
    OpenAI,
    APIConnectionError,
    APITimeoutError,
    InternalServerError,
    NotFoundError,
    RateLimitError,
)

from src.config.config import Config

logger = logging.getLogger(__name__)

# Transient errors worth retrying. NotFoundError (404) is included on purpose:
# self-hosted vLLM behind an ingress returns 404 for /v1/chat/completions while
# the model pod is still starting/loading, even though the route is valid.
RETRYABLE_ERRORS = (
    APIConnectionError,
    APITimeoutError,
    InternalServerError,
    NotFoundError,
    RateLimitError,
)


class LLMClient:
    def __init__(self, base_url: str = None, api_key: str = None, model: str = None):

        self.base_url = base_url or Config.OPENAI_API_BASE_URL
        self.api_key = api_key or Config.OPENAI_API_KEY
        self.model = model or Config.OPENAI_MODEL

        self.max_retries = getattr(Config, "LLM_MAX_RETRIES", 4)
        self.retry_backoff = getattr(Config, "LLM_RETRY_BACKOFF", 2.0)

        # Initialize OpenAI client with custom base URL. Disable the SDK's own
        # retries so retry/backoff is handled in one place (and covers 404).
        self.client = OpenAI(
            base_url=self.base_url, api_key=self.api_key, max_retries=0
        )

        logger.info("Connected to LLM at %s (model: %s)", self.base_url, self.model)

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.1,
        max_tokens: int = 8000,
        timeout: int = None,
    ) -> str:

        timeout = timeout or Config.LLM_TIMEOUT
        last_error = None

        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout=timeout,
                )

                if response.choices and len(response.choices) > 0:
                    content = response.choices[0].message.content
                    if content:
                        return content

                logger.warning("LLM returned an empty response")
                return "Error: No response generated"

            except RETRYABLE_ERRORS as e:
                last_error = e
                if attempt < self.max_retries:
                    wait = self.retry_backoff * (2 ** (attempt - 1))
                    logger.warning(
                        "LLM request failed (attempt %d/%d): %s. Retrying in %.1fs",
                        attempt,
                        self.max_retries,
                        type(e).__name__,
                        wait,
                    )
                    time.sleep(wait)
                else:
                    logger.error(
                        "LLM request failed after %d attempts: %s",
                        self.max_retries,
                        e,
                    )

            except Exception as e:
                # Non-transient (e.g. bad request, auth) — retrying won't help.
                logger.error("LLM request failed (non-retryable): %s", e)
                return f"Error: {str(e)}"

        return f"Error: {last_error}"

    def generate(
        self,
        prompt: str,
        temperature: float = 0.1,
        max_tokens: int = 8000,
        timeout: int = None,
    ) -> str:
        messages = [{"role": "user", "content": prompt}]
        return self.chat(messages, temperature, max_tokens, timeout)

    def chat_with_system(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.1,
        max_tokens: int = 8000,
        timeout: int = None,
    ) -> str:

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        return self.chat(messages, temperature, max_tokens, timeout)
