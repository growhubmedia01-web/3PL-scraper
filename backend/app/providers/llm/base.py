"""LLM provider abstraction (§47).

Business logic depends on LLMProvider only. Swapping Groq for Gemini is a
config change, never a code change.
"""
from __future__ import annotations

import abc
import json
import re
from dataclasses import dataclass

_JSON_BLOCK = re.compile(r"```(?:json)?\s*(.*?)```", re.S)


@dataclass
class LLMResponse:
    text: str
    model: str
    provider: str
    tokens_in: int = 0
    tokens_out: int = 0

    def json(self) -> dict:
        """Parse JSON out of a model response, tolerating fenced code blocks
        and leading prose."""
        raw = self.text.strip()
        block = _JSON_BLOCK.search(raw)
        if block:
            raw = block.group(1).strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            start, end = raw.find("{"), raw.rfind("}")
            if start != -1 and end > start:
                return json.loads(raw[start:end + 1])
            raise


class LLMError(RuntimeError):
    pass


class LLMProvider(abc.ABC):
    name: str = "base"
    default_model: str = ""

    @abc.abstractmethod
    def complete(self, *, system: str, user: str, model: str | None = None,
                 temperature: float | None = None,
                 max_tokens: int | None = None,
                 json_mode: bool = False) -> LLMResponse:
        ...

    @property
    def configured(self) -> bool:
        return True
