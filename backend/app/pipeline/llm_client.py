from typing import Dict, Any, List, Optional
import httpx

from app.config.settings import settings
from app.config.logging import get_logger

logger = get_logger(__name__)

class LLMClient:
    def __init__(self):
        self.provider = settings.LLM_PROVIDER.lower()
        self.ollama_url = settings.OLLAMA_URL
        self.ollama_model = settings.OLLAMA_MODEL
        self.openai_key = settings.OPENAI_API_KEY
        self.openai_model = settings.OPENAI_MODEL

    def chat(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        temperature: float = 0.7
    ) -> str:
        """Dispatches conversational chat query."""
        all_messages = []
        if system_prompt:
            all_messages.append({"role": "system", "content": system_prompt})
        all_messages.extend(messages)

        if self.provider == "openai" and self.openai_key:
            try:
                return self._chat_openai(all_messages, temperature)
            except Exception as e:
                logger.warning(f"OpenAI chat failed: {e}")
                raise RuntimeError("Configured OpenAI provider is unavailable") from e

        if self.provider == "ollama":
            try:
                return self._chat_ollama(all_messages, temperature)
            except Exception as e:
                logger.warning(f"Ollama chat failed: {e}")
                raise RuntimeError("Configured Ollama provider is unavailable") from e

<<<<<<< HEAD
        # No model answered: say so rather than inventing a reply
        return (
            f"(The chat model is not available. Start Ollama and pull '{self.ollama_model}', "
            f"or set LLM_PROVIDER in backend/.env.)"
        )
=======
        raise RuntimeError(f"Unsupported or incomplete LLM provider configuration: {self.provider}")
>>>>>>> feature/graph-timeline

    def _chat_ollama(self, messages: List[Dict[str, str]], temperature: float) -> str:
        payload = {
            "model": self.ollama_model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature, "num_ctx": settings.OLLAMA_NUM_CTX}
        }
        if settings.OLLAMA_THINK is not None:          # Qwen3.5 thinks by default: minutes per reply on a laptop GPU
            payload["think"] = settings.OLLAMA_THINK
        # ponytail: the first request loads the model (6.6 GB for qwen3.5:9b), hence the long timeout
        with httpx.Client(timeout=300.0) as client:
            resp = client.post(self.ollama_url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data.get("message", {}).get("content", "")

    def _chat_openai(self, messages: List[Dict[str, str]], temperature: float) -> str:
        headers = {
            "Authorization": f"Bearer {self.openai_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.openai_model,
            "messages": messages,
            "temperature": temperature
        }
        with httpx.Client(timeout=120.0) as client:
            resp = client.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]

# Global singleton
llm_client = LLMClient()
