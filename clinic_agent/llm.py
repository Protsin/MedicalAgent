"""Optional model backend with a deterministic safety-first fallback."""
from __future__ import annotations

from abc import ABC, abstractmethod
import json
import urllib.error
import urllib.request
from typing import Protocol, Sequence

from .config import Settings
from .triage import TriageResult, compose_reply

SYSTEM_PROMPT = (
    "你是医疗预问诊助手，只做安全分诊、就医建议和病史信息整理，不诊断、不开处方。"
    "必须使用简体中文，语气冷静清晰。遇到任何急症提示时，把立即拨打120或去急诊放在第一条。"
    "若信息不足，优先询问关键症状。只输出面向用户的回复，不要输出JSON、诊断结论或处方。"
)

CORRECTION = "你的上一条回复不符合安全要求。请重新输出，不得提供诊断或处方，并优先处理急症。"


class Consultant(Protocol):
    def reply(self, message: str, triage: TriageResult, history: Sequence[str]) -> str:
        """Return a safe user-facing reply."""


class RuleBasedConsultant(ABC):
    """Base implementation; subclasses may customize model generation."""

    def __init__(self) -> None:
        self.last_error: str | None = None

    def reply(self, message: str, triage: TriageResult, history: Sequence[str]) -> str:
        fallback = compose_reply(triage, message)
        try:
            generated = self.generate(message, triage, history)
        except Exception as exc:
            self.last_error = f"model generation failed: {exc}"
            generated = None
        if not generated:
            return fallback
        if not self.is_safe(generated, triage):
            self.last_error = "generated reply failed safety validation"
            corrected = self.generate(CORRECTION, triage, (*history, generated))
            if corrected and self.is_safe(corrected, triage):
                return corrected
            return fallback
        return generated.strip()

    @abstractmethod
    def generate(self, message: str, triage: TriageResult, history: Sequence[str]) -> str | None:
        """Generate raw text, or return None to use the deterministic fallback."""

    def is_safe(self, text: str, triage: TriageResult) -> bool:
        required = ["120"] if triage.urgency.value == "emergency" else []
        return all(item in text for item in required) and len(text) <= 4000


class DeterministicConsultant(RuleBasedConsultant):
    def generate(self, message: str, triage: TriageResult, history: Sequence[str]) -> str | None:
        return None


class OpenAICompatibleConsultant(RuleBasedConsultant):
    """Small adapter for OpenAI-compatible chat completion endpoints."""

    def __init__(self, settings: Settings):
        super().__init__()
        self.settings = settings

    def generate(self, message: str, triage: TriageResult, history: Sequence[str]) -> str | None:
        payload = {
            "model": self.settings.model,
            "temperature": 0.2,
            "max_tokens": 900,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                *[
                    {"role": "assistant" if index % 2 else "user", "content": item}
                    for index, item in enumerate(list(history)[-6:])
                ],
                {
                    "role": "user",
                    "content": (
                        f"用户消息：{message}\n规则引擎安全分诊：{json.dumps(triage.as_dict(), ensure_ascii=False)}\n"
                        "请基于规则结果回复。"
                    ),
                },
            ],
        }
        request = urllib.request.Request(
            f"{self.settings.base_url}/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.settings.api_key}",
                "Content-Type": "application/json",
                "User-Agent": "clinic-agent/0.1",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.settings.request_timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
                content = body["choices"][0]["message"]["content"]
                return content if isinstance(content, str) else None
        except (OSError, ValueError, KeyError, IndexError, urllib.error.URLError) as exc:
            self.last_error = f"model request failed: {exc}"
            return None


def build_consultant(settings: Settings) -> Consultant:
    if settings.llm_enabled:
        return OpenAICompatibleConsultant(settings)
    return DeterministicConsultant()
