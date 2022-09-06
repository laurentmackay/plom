from django.urls import reverse
from django.shortcuts import render

from TestCreator.views import TestSpecPageView

from ..services import TestSpecService
from .. import forms


class TestSpecCreatorQuestionsPage(TestSpecPageView):
    """Set the number of questions and total marks"""

    def build_form(self):
        spec = TestSpecService()
        initial = {
            "questions": spec.get_n_questions(),
            "total_marks": spec.get_total_marks(),
        }

        form = forms.TestSpecQuestionsMarksForm(initial=initial)
        return form

    def build_context(self):
        context = super().build_context('questions')
        spec = TestSpecService()
        context.update({
            "prev_n_questions": spec.get_n_questions(),
        })
        return context

    def get(self, request):
        context = self.build_context()
        context.update({'form': self.build_form()})
        return render(request, "TestCreator/test-spec-questions-marks-page.html")

    def post(self, request):
        return reverse('q_detail', args=(1,))


# class TestSpecCreatorQuestionsPage(BaseTestSpecFormView):
#     template_name = 'TestCreator/test-spec-questions-marks-page.html'
#     form_class = forms.TestSpecQuestionsMarksForm

#     def get_context_data(self, **kwargs):
#         context = super().get_context_data('questions', **kwargs)
#         spec = TestSpecService()
#         context['prev_n_questions'] = spec.get_n_questions()
#         return context

#     def get_initial(self):
#         initial = super().get_initial()
#         spec = TestSpecService()
#         if spec.get_n_questions() > 0:
#             initial['questions'] = spec.get_n_questions()
#         if spec.get_total_marks() > 0:
#             initial['total_marks'] = spec.get_total_marks()

#         return initial

#     def form_valid(self, form):
#         form_data = form.cleaned_data
#         spec = TestSpecService()

#         prev_questions = spec.get_n_questions()
#         spec.set_total_marks(form_data['total_marks'])

#         if prev_questions != form_data['questions']:
#             spec.clear_questions()
#             spec.set_n_questions(form_data['questions'])
        
#         return super().form_valid(form)

#     def get_success_url(self):
#         return reverse('q_detail', args=(1,))