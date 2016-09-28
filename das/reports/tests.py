from django.test import TestCase

class TestReports(TestCase):

    def test_sitrep(self):
        response = self.client.get('/api/v1.0/reports/sitrep', follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'lewa_sitrep_template.html')