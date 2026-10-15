import unittest

from clinic_agent.triage import Urgency, compose_reply, extract_age, triage


class TriageTests(unittest.TestCase):
    def test_emergency_chest_pain_includes_escalation(self):
        result = triage("55岁，突然胸痛伴出冷汗，呼吸困难")
        self.assertEqual(result.urgency, Urgency.EMERGENCY)
        self.assertIn("呼吸内科", result.departments)
        self.assertTrue(result.red_flags)
        self.assertIn("120", compose_reply(result, "胸痛"))

    def test_infant_fever_escalates_to_urgent(self):
        result = triage("8个月宝宝发热，精神差，有点拒奶")
        self.assertEqual(result.urgency, Urgency.URGENT)
        self.assertEqual(result.departments[0], "儿科")

    def test_mild_cough_can_be_self_care(self):
        result = triage("轻微咳嗽两天，没有发热，精神还可以")
        self.assertEqual(result.urgency, Urgency.SELF_CARE)
        self.assertIn("呼吸内科", result.departments)

    def test_unspecified_symptom_is_routine(self):
        result = triage("最近肚子不舒服，偶尔腹痛，持续三天")
        self.assertEqual(result.urgency, Urgency.ROUTINE)
        self.assertIn("消化内科", result.departments)
        self.assertTrue(result.follow_ups)

    def test_insufficient_information_asks_questions(self):
        result = triage("你好")
        self.assertEqual(result.urgency, Urgency.INFO_NEEDED)
        self.assertEqual(result.departments, [])
        self.assertTrue(result.follow_ups)

    def test_history_contributes_red_flag(self):
        result = triage("现在更严重了", history=["之前有胸痛"])
        self.assertEqual(result.urgency, Urgency.EMERGENCY)

    def test_age_extraction(self):
        self.assertEqual(extract_age("年龄：42岁"), 42)
        self.assertEqual(extract_age("宝宝9个月"), 0)
        self.assertIsNone(extract_age("今天天气不错"))


if __name__ == "__main__":
    unittest.main()
