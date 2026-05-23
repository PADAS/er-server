from django.test import TestCase

import utils.html


class TestUtils(TestCase):

    def test_clean_text(self):

        sample = "The quick brown fox jumps over the lazy dog."
        cleaned = utils.html.clean_user_text(sample, "Sample")
        self.assertEqual(sample, cleaned)

    def test_clean_text_with_entities(self):
        sample = "Party with Bob & Doug"
        cleaned = utils.html.clean_user_text(sample, "Sample")
        self.assertEqual(sample, cleaned)

    def test_clean_text_with_brackets(self):
        sample = "This is <em>emphasis</em>."
        cleaned = utils.html.clean_user_text(sample, "Sample")
        self.assertEqual(sample, cleaned)

    def test_clean_text_with_quotes(self):
        sample = 'This is "quoted".'
        cleaned = utils.html.clean_user_text(sample, "Sample")
        self.assertEqual(sample, cleaned)

    def test_clean_user_data_strips_script_in_nested_dict(self):
        sample = {
            "title": "ok",
            "details": {
                "description": "<script>alert(1)</script>hello",
                "tags": ["safe", "<img src=x onerror=alert(1)>"],
            },
            "count": 3,
            "active": True,
            "missing": None,
        }
        cleaned = utils.html.clean_user_data(sample, "EventDetails.data")
        self.assertNotIn("<script>", cleaned["details"]["description"])
        self.assertIn("hello", cleaned["details"]["description"])
        self.assertNotIn("onerror", cleaned["details"]["tags"][1])
        self.assertEqual(cleaned["count"], 3)
        self.assertEqual(cleaned["active"], True)
        self.assertIsNone(cleaned["missing"])
        self.assertEqual(cleaned["details"]["tags"][0], "safe")
