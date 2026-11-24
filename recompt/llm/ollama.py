from pydantic import ValidationError

from recompt.llm.base import SYSTEM_PROMPT, DocSection, LLMUnavailable, user_prompt
from recompt.models import ExtractedPlan


class OllamaBackend:
    name = "ollama"

    def __init__(self, model: str, client=None, host: str | None = None):
        self.model = model
        self._client = client
        self._host = host

    def extract_plan(self, sections: list[DocSection]) -> ExtractedPlan:
        try:
            import ollama
        except ImportError as exc:
            raise LLMUnavailable("The Ollama backend needs the ollama package: pip install recompt[ollama]") from exc

        client = self._client or ollama.Client(host=self._host)
        try:
            response = client.chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt(sections)},
                ],
                format=ExtractedPlan.model_json_schema(),
                options={"temperature": 0},
            )
            return ExtractedPlan.model_validate_json(response.message.content)
        except ollama.ResponseError as exc:
            raise LLMUnavailable(f"Ollama error: {exc}") from exc
        except ConnectionError as exc:
            raise LLMUnavailable(f"Cannot reach Ollama: {exc}") from exc
        except ValidationError as exc:
            raise LLMUnavailable(f"Ollama returned an invalid plan: {exc.error_count()} errors") from exc
