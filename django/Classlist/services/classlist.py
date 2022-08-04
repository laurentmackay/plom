from django.core.files import File
from django.db import transaction, IntegrityError

from Classlist.models import Student, ClasslistCSV

import logging
from pathlib import Path
from tempfile import NamedTemporaryFile

log = logging.getLogger("ClasslistService")


class ClasslistCSVService:
    def take_classlist_from_upload(self, in_memory_file):
        from plom.create.classlistValidator import PlomClasslistValidator

        # delete any old classlists
        self.delete_classlist_csv()
        # now save the in-memory file to a tempfile and validate
        tmp_csv = Path(NamedTemporaryFile(delete=False).name)
        with open(tmp_csv, "wb") as fh:
            for chunk in in_memory_file:
                fh.write(chunk)

        vlad = PlomClasslistValidator()
        success, werr = vlad.validate_csv(tmp_csv)
        
        tmp_csv.unlink()

        with transaction.atomic():
            dj_file = File(in_memory_file, name="classlist.csv")
            cl_obj = ClasslistCSV(
                valid=success, csv_file=dj_file, warnings_errors_list=werr
            )
            cl_obj.save()

        return (success, werr)

    @transaction.atomic()
    def delete_classlist_csv(self):
        ClasslistCSV.objects.filter().delete()


class ClasslistService:
    @transaction.atomic
    def how_many_students(self):
        return Student.objects.all().count()

    @transaction.atomic()
    def get_students(self):
        return list(Student.objects.all().values("student_id", "student_name"))

    def add_students_from_list(self, student_list):
        """Add all students in the list.

        student_list (list): list of dict of students. Each item
            should be {'id': blah, 'name': blah}

        return list: list of any errors.
        """
        errors = []
        for student in student_list:
            try:
                if "id" in student and "name" in student:
                    self.add_student(student["id"], student["name"])
                else:
                    errors.append(f"{student} missing id or name field")
            except IntegrityError:
                errors.append(f"{student} has non-unique id")
        return errors

    @transaction.atomic()
    def add_student(self, student_id, student_name):
        # will raise an integrity error if id not unique

        s_obj = Student(student_id=student_id, student_name=student_name)
        s_obj.save()

    @transaction.atomic()
    def remove_all_students(self):
        Student.objects.all().delete()
