import glob
import os
import pathlib
from pathlib import Path
from wsgiref.util import FileWrapper

from django.shortcuts import render
from django.views.generic import View
from braces.views import LoginRequiredMixin, GroupRequiredMixin

from BuildPaperPDF.forms import BuildNumberOfPDFsForm
from django.http import FileResponse
from django.http import HttpResponse
from django.core.files.uploadedfile import SimpleUploadedFile
from django.conf import settings
from django.core.files import File
from io import BytesIO

from Connect.services import CoreConnectionService

from .services import (generate_pdf, BuildPapersService, RenamePDFFile)
from .models import Task


# Create your views here.


class BuildPaperPDFs(LoginRequiredMixin, GroupRequiredMixin, View):
    template_name = 'BuildPaperPDF/build_paper_pdfs.html'
    login_url = "login"
    group_required = ["manager"]
    navbar_colour = "#AD9CFF"
    form = BuildNumberOfPDFsForm()

    def get(self, request):

        context = {'navbar_colour': self.navbar_colour, 'user_group': self.group_required[0],
                   'form': self.form, 'message': ''}
        return render(request, self.template_name, context)

    def post(self, request):
        form = BuildNumberOfPDFsForm(request.POST)
        if form.is_valid():
            number_of_pdfs = int(request.POST.get('pdfs'))
            bps = BuildPapersService()
            ccs = CoreConnectionService()
            credentials = (ccs.get_server_name(), ccs.get_manager_password())
            bps.clear_tasks()
            bps.build_n_papers(number_of_pdfs, credentials)

            # code below is to write dummy pdf file to model, can be deleted later
            # for num in range(1, 4):
            #     index = f'{num:04n}'
            #     Task(
            #         paper_number=index,
            #         pdf_file_path=str(path) + '/' + str(pdf_file_list[num-1]),
            #         status='todo'
            #     ).save()

            task_objects = Task.objects.all()
            Rename = RenamePDFFile()

            tasks_paper_number = []
            tasks_pdf_file_path = []
            tasks_status = []

            for task in task_objects:
                tasks_paper_number.append(task.paper_number)
                tasks_pdf_file_path.append(Rename.get_PDF_name(task.pdf_file_path))
                tasks_status.append(task.status)
            message = 'Your pdf finished building! See below.'
            context = {'navbar_colour': self.navbar_colour, 'user_group': self.group_required[0],
                       'form': self.form, 'message': message,
                       'tasks': zip(tasks_paper_number, tasks_pdf_file_path, tasks_status)}
            return render(request, self.template_name, context)


class GetPDFFile(View):
    # TODO: modify pdf file name
    def get(self, request, paper_number):
        pdf_file = Task.objects.get(paper_number=paper_number).pdf_file_path
        pdf_path = pathlib.Path(pdf_file)
        if not pdf_path.exists() or not pdf_path.is_file():
            return HttpResponse(status=500)

        file = pdf_path.open('rb')
        pdf = SimpleUploadedFile('paper.pdf', file.read(), content_type='application/pdf')

        return FileResponse(pdf)
