.. Plom documentation
   Copyright (C) 2023 Andrew Rechnitzer
   Copyright (C) 2023 Colin B. Macdonald
   SPDX-License-Identifier: AGPL-3.0-or-later

Processing homework
===================

This document outlines how we might Plom to mark homework.
The main issue here is that homework (say uploaded by
students to an LMS like Canvas) are **not** structured. A typical
homework pdf will not contain an ID-page nor will it have questions
neatly arranged so that we know (with certainty) what precisely is on
page-7 of the PDF.

.. caution::

   This feature is under active development.  Plom's primary use
   case is for QR-coded hardcopy assessments; we are working
   toward supporting scripting for other use-cases such as
   homework.

.. note::

   For the legacy server, the process is similar and described
   later in this document.


Assumptions
-----------

So let us make a few assumptions about the homework submission:

* a homework submission is exactly 1 PDF (though perhaps this can be
  loosened later) containing at least 1 page.
* we know which student submitted a given HW pdf (their name and ID)
* we know a "free" paper-number to which we can assign this homework (again, this can potentially be loosened later)
* we know (or can make a reasonable guess) as to which questions appear on which pages of the HW pdf - ie a question-mapping.

and also a few assumptions about the server:

* we have a running server
* with manager + scanner users
* a test-specification - notice that we need this so that we know how many questions, how many marks etc
* enough "built" test-papers so that the database has at least one paper per student. The corresponding pdfs do not need to be built, but we need the database rows (again - this can perhaps be loosened in the future)


Processing a single homework pdf
--------------------------------

Let's upload, process and push a single homework PDF.

* It will be uploaded as paper-number 61.
* Homework pdf ``"fake_hw_bundle_61.pdf"`` containing 5 pages.
* We will map

   - p1 = q1
   - p2 = q2
   - p3 = garbage (ie no questions)
   - p4 = q2 and q3
   - p5 = q3
* We write this page-to-question mapping as a list of lists: ``[ [1], [2], [], [2, 3], [3] ]``
* The homework was submitted by student with id "88776655" and name "Kenson, Ken".
* We will upload the homework as user "demoScanner1"
* We will process the homework as user "demoManager1"


We first upload the homework using ``plom_staging_bundles``::

    $ python manage.py plom_staging_bundles upload demoScanner1 fake_hw_bundle_61.pdf
    Uploaded fake_hw_bundle_61.pdf as user demoScanner1 - processing it in the background now.

We can then check on the progress via::

    $ python manage.py plom_staging_bundles status

and we get a table by way of reply which tells us that the bundle has
been uploaded, has 5 pages, but its qr-codes have not been read nor has
it been pushed.
This is good because it does not have qr-codes.

Next to map the pages of this bundle to questions we use ``plom_paper_scan``::

    $ python manage.py plom_paper_scan list_bundles map fake_hw_bundle_61 -t 61 -q [[1],[2],[],[2,3],[3]]

The server then returns something like::

    CAUTION: paper_scan is an experimental tool
    DEBUG: numpages in bundle: 5
    DEBUG: pre-canonical question:  [[1],[2],[],[2,3],[3]]
    DEBUG: canonical question list: [[1], [2], [], [2, 3], [3]]


Now the system knows which pages contain which questions, so we can "push" the bundle to server::

    $ python manage.py plom_staging_bundles push fake_hw_bundle_61 demoScanner1
    Bundle fake_hw_bundle_61 - pushed from staging.

At this point the homework is in the system and marking can begin.
The server knows which pages contain which questions etc.
However the system does not yet know which student to associate with the paper.
Accordingly we now ID the paper using ``plom_id_direct``::

    python manage.py plom_id_direct demoManager1 61 88776655 "Kenson, Ken"

Now the homework is in the system, and the system knows who it belongs to.


Summary of process
------------------

* make sure server is set up.
* ``python manage.py plom_staging_bundles upload <scannerName> <hwpdf>``

   - This does synchronous processing---so we should wait until it is done.
     The remaining steps are synchronous.
* ``python manage.py plom_paper_scan list_bundles map <hwpdf> -t <papernumber> -q <question_map>``
* ``python manage.py plom_staging_bundles push <hwpdf> <scannerName>``
* ``python manage.py plom_id_direct <managerName> <paper_number> <student_id> <student_name>``


Processing homework with the legacy Plom server
-----------------------------------------------

A script can be used, roughly:

* prename a paper to an available paper number.  A script to do this is
  ``contrib/plom-preid.py``.
  This will associate a particular Student ID to a paper number
* Use ``plom-hwscan`` to upload a PDF file to that student number.
* Optionally, use ``msgr.id_paper`` to "finalize" the identity of that paper.
  Alternatively, you can do this manually in the Plom Client identifier app.

An work-in-progress script that does these steps while pulling from
Canvas is ``contrib/plom-server-from-canvas.py``.

.. caution::

   Do not prename the same student number to more than one paper in this process.
   Its not well-defined what happens.

.. note::

   Do not use ``id_paper`` to identify the paper before you upload do it.  This
   will create a situation where the paper is not seen as scanned.  We're unlikely
   to fix this, instead focusing on workflows for the nextgen server instead.
