import tempfile
from pathlib import Path
import unittest

from clinic_agent.storage import NotFoundError, Store


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / "test.db")

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def test_session_and_message_round_trip(self):
        session = self.store.create_session("测试用户", 30, "female")
        first = self.store.add_message(session.id, "user", "咳嗽两天")
        triage = {"urgency": "routine", "departments": ["呼吸内科"]}
        second = self.store.add_message(session.id, "assistant", "建议门诊评估", triage)
        self.store.update_triage(session.id, "routine", ["呼吸内科"])

        stored_session = self.store.get_session(session.id)
        messages = self.store.list_messages(session.id)
        self.assertEqual(stored_session.urgency, "routine")
        self.assertEqual(stored_session.departments, ["呼吸内科"])
        self.assertEqual([message.id for message in messages], [first.id, second.id])
        self.assertEqual(messages[1].triage, triage)

    def test_missing_session_raises(self):
        with self.assertRaises(NotFoundError):
            self.store.get_session("does-not-exist")

    def test_invalid_age_rejected(self):
        with self.assertRaises(ValueError):
            self.store.create_session("测试", 121, "unknown")


if __name__ == "__main__":
    unittest.main()
