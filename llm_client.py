from openai import OpenAI
from typing import List, Dict, Optional
import time
from config import Config


class LLMClient:
    def __init__(self, base_url: str = None, api_key: str = None, model: str = None):

        self.base_url = base_url or Config.OPENAI_API_BASE_URL
        self.api_key = api_key or Config.OPENAI_API_KEY
        self.model = model or Config.OPENAI_MODEL

        # Initialize OpenAI client with custom base URL
        self.client = OpenAI(base_url=self.base_url, api_key=self.api_key)

        print(f"✅ Connected to LLM at {self.base_url}")
        print(f"📦 Using model: {self.model}")

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.0,
        max_tokens: int = 4000,
        timeout: int = None,
    ) -> str:

        timeout = timeout or Config.LLM_TIMEOUT

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout,
            )

            if response.choices and len(response.choices) > 0:
                return response.choices[0].message.content

            return "Error: No response generated"

        except Exception as e:
            return f"Error: {str(e)}"

    def generate(
        self,
        prompt: str,
        temperature: float = 0.0,
        max_tokens: int = 4000,
        timeout: int = None,
    ) -> str:
        messages = [{"role": "user", "content": prompt}]
        return self.chat(messages, temperature, max_tokens, timeout)

    def chat_with_system(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
        max_tokens: int = 4000,
    ) -> str:
       
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        return self.chat(messages, temperature, max_tokens)
