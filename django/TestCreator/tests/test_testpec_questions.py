from django.test import TestCase
from .. import services
from .. import models


class TestSpecQuestionTests(TestCase):
    """Test services code for models.TestSpecQuestion"""

    @classmethod
    def get_default_pages(self):
        return {
        "0": {
            'id_page': False,
            'dnm_page': False,
            'question_page': False,
            'thumbnail': 'thumbnails/dummy/dummy-thumbnail0.png'
        },
        "1": {
            'id_page': False,
            'dnm_page': False,
            'question_page': False,
            'thumbnail': 'thumbnails/dummy/dummy-thumbnail1.png'
        }
    }

    def test_create_question(self):
        """Test services.create_question"""
        q1 = services.create_question(1, 'Q1', 1, False)
        self.assertEqual(q1.index, 1)
        self.assertEqual(q1.label, 'Q1')
        self.assertEqual(q1.mark, 1)
        self.assertEqual(q1.shuffle, False)

    def test_remove_question(self):
        """Test services.remove_question"""
        q1 = models.TestSpecQuestion(index=1, label='Q1', mark=1, shuffle=False)
        q1.save()

        services.remove_question(1)
        self.assertEqual(len(models.TestSpecQuestion.objects.all()), 0)

    def test_remove_question_update_spec(self):
        """Test that calling remove_question will update the pages in models.TestSpecInfo"""
        q1 = models.TestSpecQuestion(index=1, label='Q1', mark=1, shuffle=False)
        q1.save()

        spec = services.load_spec()
        spec.pages = self.get_default_pages()
        spec.pages["1"]['question_page'] = 1
        spec.save()

        services.remove_question(1)
        
        # You'll have calling load_spec() every time you want to lookup the most recent values
        spec = services.load_spec()
        self.assertEqual(spec.pages["1"]['question_page'], False)

    def test_clear_questions(self):
        """Test services.clear_questions"""
        q1 = models.TestSpecQuestion(index=1, label='Q1', mark=1, shuffle=False)
        q1.save()

        q2 = models.TestSpecQuestion(index=2, label='Q2', mark=1, shuffle=False)
        q2.save()

        q3 = models.TestSpecQuestion(index=3, label='Q3', mark=1, shuffle=False)
        q3.save()

        # Have to keep TestSpecInfo updated
        spec = services.load_spec()
        spec.n_questions = 3
        spec.save()

        services.clear_questions()
        self.assertEqual(len(models.TestSpecQuestion.objects.all()), 0)
