from django.test import TestCase

import utils.html


class TestUtils(TestCase):

    def test_clean_text(self):

        sample = 'The quick brown fox jumps over the lazy dog.'
        cleaned = utils.html.clean_user_text(sample, 'Sample')
        self.assertEqual(sample, cleaned)

    def test_clean_text_with_entities(self):
        sample = 'Party with Bob & Doug'
        cleaned = utils.html.clean_user_text(sample, 'Sample')
        self.assertEqual(sample, cleaned)

    def test_clean_text_with_brackets(self):
        sample = 'This is <em>emphasis</em>.'
        cleaned = utils.html.clean_user_text(sample, 'Sample')
        self.assertEqual(sample, cleaned)

    def test_clean_text_with_quotes(self):
        sample = 'This is "quoted".'
        cleaned = utils.html.clean_user_text(sample, 'Sample')
        self.assertEqual(sample, cleaned)
