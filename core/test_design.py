from django.contrib.staticfiles import finders
from django.test import Client, TestCase


class DesignFilesTests(TestCase):
    def test_tokens_file_exists(self):
        self.assertIsNotNone(finders.find('css/tokens.css'))

    def test_inter_font_files_exist(self):
        for name in ['Inter-Regular.woff2', 'Inter-Medium.woff2',
                     'Inter-SemiBold.woff2', 'Inter-Bold.woff2']:
            self.assertIsNotNone(finders.find(f'vendor/inter/{name}'), name)

    def test_school_css_defines_derived_colours(self):
        response = Client().get('/school.css')
        css = response.content.decode()
        self.assertIn('--school-primary-soft', css)
        self.assertIn('--school-accent-soft', css)