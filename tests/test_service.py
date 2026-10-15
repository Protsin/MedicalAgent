import tempfile
from pathlib import Path
import unittest

from clinic_agent.config import Settings
from clinic_agent.llm import DeterministicConsultant
from clinic_agent.service import ClinicService
from clinic_agent.storage import Store


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.settings = Settings(database_path=Path(self.temp.name) / "test.db")
        self.store = Store(self.settings.database_path)
        self.service = ClinicService(self.store, DeterministicConsultant(), self.settings)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def test_message_persists_conversation_and_triage(self):
        session = self.service.create_session({"patient_alias": "小李", "age_years": 40, "sex": "male"})["session"]
        result = self.service.handle_message(session["id"], {"content": "咳嗽三天，喉咙痛，没有胸痛"})
        self.assertEqual(result["triage"]["urgency"], "routine")
        self.assertIn("呼吸内科", result["triage"]["departments"])
        self.assertIn("呼吸内科", result["session"]["departments"])
        loaded = self.service.get_session(session["id"])
        self.assertEqual(len(loaded["messages"]), 2)
        self.assertEqual(loaded["messages"][-1]["role"], "assistant")

    def test_empty_message_rejected(self):
        session = self.service.create_session({})["session"]
        with self.assertRaises(ValueError):
            self.service.handle_message(session["id"], {"content": "   "})

    def test_model_failure_uses_fallback(self):
        class FailingConsultant(DeterministicConsultant):
            def generate(self, *args, **kwargs):
                raise RuntimeError("network unavailable")

        service = ClinicService(self.store, FailingConsultant(), self.settings)
        session = service.create_session({})["session"]
        result = service.handle_message(session["id"], {"content": "突然剧烈胸痛，出冷汗"})
        self.assertEqual(result["triage"]["urgency"], "emergency")
        self.assertIn("120", result["assistant_message"]["content"])


if __name__ == "__main__":
    unittest.main()
