"""Application service connecting storage, triage, and model backend."""
from __future__ import annotations

from typing import Any

from .config import Settings
from .llm import Consultant, build_consultant
from .storage import Store
from .triage import TriageResult, triage


class ClinicService:
    def __init__(self, store: Store, consultant: Consultant, settings: Settings):
        self.store = store
        self.consultant = consultant
        self.settings = settings

    def create_session(self, payload: dict[str, Any]) -> dict[str, Any]:
        alias = self._string(payload.get("patient_alias", "未命名访客"), "patient_alias", 80)
        sex = self._string(payload.get("sex", "unknown"), "sex", 20)
        age = payload.get("age_years")
        if age not in (None, "") and (isinstance(age, bool) or not isinstance(age, int)):
            raise ValueError("age_years must be an integer")
        session = self.store.create_session(
            patient_alias=alias or "未命名访客",
            age_years=age if age != "" else None,
            sex=sex or "unknown",
        )
        return {"session": session.as_dict(), "messages": []}

    def list_sessions(self, limit: int = 50) -> dict[str, Any]:
        return {"sessions": [session.as_dict() for session in self.store.list_sessions(limit)]}

    def get_session(self, session_id: str) -> dict[str, Any]:
        session = self.store.get_session(session_id)
        return {
            "session": session.as_dict(),
            "messages": [message.as_dict() for message in self.store.list_messages(session_id)],
        }

    def handle_message(self, session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        content = self._string(payload.get("content"), "content", self.settings.max_message_chars)
        content = content.strip()
        if not content:
            raise ValueError("content cannot be empty")
        if len(content) > self.settings.max_message_chars:
            raise ValueError(f"content exceeds {self.settings.max_message_chars} characters")

        session = self.store.get_session(session_id)
        prior_messages = self.store.list_messages(session_id)
        user_symptom_history = [
            message.content for message in prior_messages if message.role == "user"
        ]
        user_message = self.store.add_message(session_id, "user", content)
        result = triage(
            content,
            age_years=session.age_years,
            history=user_symptom_history,
        )
        conversation_history = [message.content for message in prior_messages]
        reply = self.consultant.reply(content, result, conversation_history)
        assistant_message = self.store.add_message(
            session_id,
            "assistant",
            reply,
            triage=result.as_dict(),
        )
        updated = self.store.update_triage(session_id, result.urgency.value, result.departments)
        return {
            "session": updated.as_dict(),
            "user_message": user_message.as_dict(),
            "assistant_message": assistant_message.as_dict(),
            "triage": result.as_dict(),
        }

    @staticmethod
    def _string(value: object, field: str, maximum: int) -> str:
        if value is None:
            return ""
        if not isinstance(value, str):
            raise ValueError(f"{field} must be a string")
        if len(value) > maximum:
            raise ValueError(f"{field} exceeds {maximum} characters")
        return value.strip()
