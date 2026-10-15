import json
import tempfile
import threading
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from clinic_agent.config import Settings
from clinic_agent.server import create_server


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.settings = Settings(host="127.0.0.1", port=0, database_path=f"{cls.temp.name}/server.db")
        cls.server = create_server(cls.settings)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.server.service.store.close()
        cls.thread.join(timeout=2)
        cls.temp.cleanup()

    def request(self, path, method="GET", payload=None):
        body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode()
        request = Request(
            self.base + path,
            data=body,
            method=method,
            headers={"Content-Type": "application/json"} if body else {},
        )
        with urlopen(request, timeout=3) as response:
            return response.status, json.loads(response.read().decode())

    def test_health_and_static_page(self):
        status, health = self.request("/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(health["status"], "ok")
        with urlopen(self.base + "/", timeout=3) as response:
            self.assertEqual(response.status, 200)
            self.assertIn("clinic-agent", response.read().decode())

    def test_session_conversation_round_trip(self):
        status, created = self.request(
            "/api/sessions", "POST", {"patient_alias": "集成测试", "age_years": 28}
        )
        self.assertEqual(status, 201)
        session_id = created["session"]["id"]
        status, answered = self.request(
            f"/api/sessions/{session_id}/messages", "POST", {"content": "咳嗽两天，喉咙痛"}
        )
        self.assertEqual(status, 200)
        self.assertEqual(answered["triage"]["urgency"], "routine")
        self.assertEqual(answered["session"]["departments"], answered["triage"]["departments"])

        status, loaded = self.request(f"/api/sessions/{session_id}")
        self.assertEqual(status, 200)
        self.assertEqual(len(loaded["messages"]), 2)

    def test_missing_session_is_404(self):
        with self.assertRaises(HTTPError) as context:
            self.request("/api/sessions/missing")
        self.assertEqual(context.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
