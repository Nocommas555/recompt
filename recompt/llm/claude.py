from recompt.llm.base import SYSTEM_PROMPT, DocSection, LLMUnavailable, user_prompt
from recompt.models import ExtractedPlan


class ClaudeBackend:
    name = "claude"

    def __init__(self, model: str, client=None):
        self.model = model
        self._client = client

    def extract_plan(self, sections: list[DocSection]) -> ExtractedPlan:
        try:
            import anthropic
        except ImportError as exc:
            raise LLMUnavailable("The Claude backend needs the anthropic package: pip install recompt[claude]") from exc

        try:
            client = self._client or anthropic.Anthropic()
            response = client.messages.parse(
                model=self.model,
                max_tokens=16000,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt(sections)}],
                output_format=ExtractedPlan,
            )
        except anthropic.RateLimitError as exc:
            raise LLMUnavailable(f"Claude API rate limit: {exc}") from exc
        except anthropic.APIStatusError as exc:
            raise LLMUnavailable(f"Claude API error: {exc}") from exc
        except anthropic.APIConnectionError as exc:
            raise LLMUnavailable(f"Cannot reach the Claude API: {exc}") from exc
        except anthropic.AnthropicError as exc:
            raise LLMUnavailable(f"Claude client error: {exc}") from exc
        except TypeError as exc:
            if "authentication method" not in str(exc):
                raise
            raise LLMUnavailable("No Claude API credentials found (set ANTHROPIC_API_KEY or run `ant auth login`)") from exc

        if response.stop_reason == "refusal" or response.parsed_output is None:
            raise LLMUnavailable(f"Claude returned no plan (stop reason: {response.stop_reason})")
        return response.parsed_output
