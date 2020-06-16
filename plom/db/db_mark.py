from plom.db.tables import *
from datetime import datetime

import logging

log = logging.getLogger("DB")

# ------------------
# Marker stuff


def McountAll(self, q, v):
    """Count all the scanned q/v groups.
    """
    try:
        return (
            QGroup.select()
            .join(Group)
            .where(QGroup.question == q, QGroup.version == v, Group.scanned == True,)
            .count()
        )
    except QGroup.DoesNotExist:
        return 0


def McountMarked(self, q, v):
    """Count all the q/v groups that have been marked.
    """
    try:
        return (
            QGroup.select()
            .join(Group)
            .where(
                QGroup.question == q,
                QGroup.version == v,
                QGroup.status == "done",
                Group.scanned == True,
            )
            .count()
        )
    except QGroup.DoesNotExist:
        return 0


def MgetDoneTasks(self, user_name, q, v):
    """When a marker-client logs on they request a list of papers they have already marked.
    Send back the list of [group-ids, mark, marking_time, tags] for each paper.
    """
    uref = User.get(name=user_name)  # authenticated, so not-None

    query = QGroup.select().where(
        QGroup.user == uref,
        QGroup.question == q,
        QGroup.version == v,
        QGroup.status == "done",
    )
    mark_list = []
    for qref in query:  # grab that questionData object
        aref = qref.annotations[-1]  # grab the last annotation
        mark_list.append([qref.group.gid, aref.mark, aref.marking_time, aref.tags])
        # note - used to return qref.status, but is redundant since these all "done"
    log.debug('Sending completed Q{}v{} tasks to user "{}"'.format(q, v, user_name))
    return mark_list


def MgetNextTask(self, q, v):
    """Find unmarked (but scanned) q/v-group and send the group-id back to client.
    """
    with plomdb.atomic():
        try:
            qref = (
                QGroup.select()
                .join(Group)
                .where(
                    QGroup.status == "todo",
                    QGroup.question == q,
                    QGroup.version == v,
                    Group.scanned == True,
                )
                .get()
            )
        except QGroup.DoesNotExist as e:
            log.info("Nothing left on Q{}v{} to-do pile".format(q, v))
            return None

        log.debug("Next Q{}v{} task = {}".format(q, v, qref.group.gid))
        return qref.group.gid


def MgiveTaskToClient(self, user_name, group_id):
    """Assign question/version #group_id as a task to the given user, unless has been taken by another user.
    Create new annotation (and associated pages, etc) by copying the last one for that qdata.
    Return [True, tags, image0, image1, image2,...].
    """

    uref = User.get(name=user_name)  # authenticated, so not-None

    with plomdb.atomic():
        gref = Group.get_or_none(Group.gid == group_id)
        if gref is None:  # this should not happen.
            log.info("That question {} not known".format(group_id))
            return [False]
        if gref.scanned == False:  # this should not happen either
            log.info("That question {} not scanned".format(group_id))
            return [False]
        # grab the qdata corresponding to that group
        qref = gref.qgroups[0]
        if (qref.user is not None) and (
            qref.user != uref
        ):  # has been claimed by someone else.
            return [False]
        # update status, username
        qref.status = "out"
        qref.user = uref
        qref.save()
        # update the associated annotation
        # - create a new annotation copied from the previous one
        aref = qref.annotations[-1]  # are these in right order
        new_aref = Annotation.create(
            qgroup=qref,
            user=uref,
            edition=aref.edition + 1,
            tags=aref.tags,
            time=datetime.now(),
        )
        # create its pages
        for p in aref.apages.order_by(APage.order):
            APage.create(annotation=new_aref, order=p.order, image=p.image)
        # update user activity
        uref.last_action = "Took M task {}".format(group_id)
        uref.last_activity = datetime.now()
        uref.save()
        # return [true, tags, page1, page2, etc]
        rval = [
            True,
            new_aref.tags,
        ]
        for p in new_aref.apages.order_by(APage.order):
            rval.append(p.image.file_name)
        log.debug('Giving marking task {} to user "{}"'.format(group_id, user_name))
        return rval


def MdidNotFinish(self, user_name, group_id):
    """When user logs off, any images they have still out should be put
    back on todo pile. This returns the given gid to the todo pile.
    """
    uref = User.get(name=user_name)  # authenticated, so not-None

    with plomdb.atomic():
        gref = Group.get_or_none(Group.gid == group_id)
        if gref is None:  # this should not happen.
            log.info("That task {} not known".format(group_id))
            return
        if gref.scanned == False:  # sanity check
            return  # should not happen
        qref = gref.qgroups[0]
        # sanity check that user has task
        if qref.user != uref or qref.status != "out":
            return  # has been claimed by someone else. Should not happen

        # update status, etc
        qref.status = "todo"
        qref.user = None
        qref.marked = False
        # delete the associated APages and then the annotation.
        aref = qref.annotations[-1]
        for p in aref.apages:
            p.delete_instance()
        aref.delete_instance()
        # now clean up the qgroup
        qref.test.marked = False
        qref.test.save()
        qref.save()
        # Log user returning given task.
        log.info("User {} did not mark task {}".format(user_name, group_id))


def MtakeTaskFromClient(
    self,
    task,
    user_name,
    mark,
    annot_fname,
    plom_fname,
    comment_fname,
    marking_time,
    tags,
    md5,
):
    """Get marked image back from client and update the record
    in the database.
    Update the annotation.
    Check to see if all questions for that test are marked and if so update the sum-mark data.
    """
    uref = User.get(name=user_name)  # authenticated, so not-None

    with plomdb.atomic():
        # grab the group corresponding to that task
        gref = Group.get_or_none(Group.gid == task)
        if gref is None:  # this should not happen
            log.error(
                "That returning marking task number {} / user {} pair not known".format(
                    task, user_name
                )
            )
            return False
        # and grab the qdata of that group
        qref = gref.qgroups[0]
        if qref.user != uref:  # this should not happen
            return False  # has been claimed by someone else.

        # update status, mark, annotate-file-name, time, and
        # time spent marking the image
        qref.status = "done"
        qref.marked = True
        aref = qref.annotations[-1]
        aref.image = Image.create(file_name=annot_fname, md5sum=md5)
        aref.mark = mark
        aref.plom_file = plom_fname
        aref.comment_file = comment_fname
        aref.time = datetime.now()
        aref.marking_time = marking_time
        aref.tags = tags
        qref.save()
        aref.save()
        # update user activity
        uref.last_action = "Returned M task {}".format(task)
        uref.last_activity = datetime.now()
        uref.save()
        # since this has been marked - check if all questions for test have been marked
        log.info(
            "Task {} marked {} by user {} and placed at {} with md5 = {}".format(
                task, mark, user_name, annot_fname, md5
            )
        )
        # check if there are any unmarked questions left in the test
        tref = qref.test
        if QGroup.get_or_none(QGroup.test == tref, QGroup.marked == False) is not None:
            log.info("Still unmarked questions in test {}".format(tref.test_number))
            return True
        # update the sum-mark
        tot = 0
        for qd in QGroup.select().where(QGroup.test == tref):
            tot += qd.annotations[-1].mark
        sref = tref.sumdata[0]
        # since the total is computed automatically, we assign the sumdata to HAL
        auto_uref = User.get(name="HAL")
        sref.user = auto_uref  # auto-totalled by HAL.
        sref.time = datetime.now()
        sref.sum_mark = tot
        sref.summed = True
        sref.status = "done"
        sref.save()
        log.info(
            "All of test {} is marked - total updated = {}".format(
                tref.test_number, tot
            )
        )
        tref.marked = True
        tref.totalled = True
        tref.save()
        return True


def MgetImages(self, user_name, task):
    """Send image list back to user for the given marking task.
    If question has been annotated then send back the annotated image and the plom file as well.
    """
    uref = User.get(name=user_name)  # authenticated, so not-None
    with plomdb.atomic():
        gref = Group.get_or_none(Group.gid == task)
        # some sanity checks
        if gref is None:
            log.info("Mgetimage - task {} not known".format(task))
            return [False]
        if gref.scanned == False:  # this should not happen either
            return [False, "Task {} is not completely scanned".format(task)]
        # grab associated qdata
        qref = gref.qgroups[0]
        if qref.user != uref:
            # belongs to another user - should not happen
            return [
                False,
                "Task {} does not belong to user {}".format(task, user_name),
            ]
        # return [true, n, page1,..,page.n]
        # or (if annotated already)
        # return [true, n, page1,..,page.n, annotatedFile, plom_file]
        pp = []
        aref = qref.annotations[-1]
        for p in aref.apages.order_by(APage.order):
            pp.append(p.image.file_name)
        if aref.image is not None:
            return [True, len(pp)] + pp + [aref.image.file_name, aref.plom_file]
        else:
            return [True, len(pp)] + pp


def MgetOriginalImages(self, task):
    """Return the original (unannotated) page images of the given task to the user.
    """
    with plomdb.atomic():
        gref = Group.get_or_none(Group.gid == task)
        if gref is None:  # should not happen
            log.info("MgetOriginalImages - task {} not known".format(task))
            return [False, "Task {} not known".format(task)]
        if gref.scanned == False:
            log.warning(
                "MgetOriginalImages - task {} not completely scanned".format(task)
            )
            return [False, "Task {} is not completely scanned".format(task)]
        aref = gref.qgroups[0].annotations[0]  # the original annotation pages
        # return [true, page1,..,page.n]
        rval = [True]
        for p in aref.apages.order_by(APage.order):
            rval.append(p.image.file_name)
        return rval


def MsetTag(self, user_name, task, tag):
    """Set tag on last annotation of given task.
    """

    uref = User.get(name=user_name)  # authenticated, so not-None
    with plomdb.atomic():
        gref = Group.get_or_none(Group.gid == task)
        if gref is None:  # should not happen
            log.error("MsetTag -  task {} not known".format(task))
            return False
        qref = gref.qgroups[0]
        if qref.user != uref:
            return False  # not your task - should not happen
        # grab the last annotation
        aref = qref.annotations[-1]
        if aref.user != uref:
            return False  # not your annotation - should not happen
        # update tag
        aref.tags = tag
        aref.save()
        log.info('Task {} tagged by user "{}": "{}"'.format(task, user_name, tag))
        return True


def MgetWholePaper(self, test_number, question):
    """Send page images of whole paper back to user, highlighting which belong to the given question. Do not show ID pages."""

    # we can show show not totally scanned test.
    tref = Test.get_or_none(Test.test_number == test_number)
    if tref is None:  # don't know that test - this shouldn't happen
        return [False]
    pageData = []  # for each page append a triple [
    # page-code = t.pageNumber, hw.questionNumber.order or l.order
    # image-id-reference number,
    # true/false - if belongs to the given question or not.
    pageFiles = []  # the corresponding filenames.
    question = int(question)
    # give TPages (aside from ID pages), then HWPages and then LPages
    for p in tref.tpages.order_by(TPage.page_number):
        if p.scanned is False:  # skip unscanned testpages
            continue
        if p.group.group_type == "i":  # skip IDpages (but we'll include dnm pages)
            continue
        val = ["t{}".format(p.page_number), p.image.id, False]
        # check if page belongs to our question
        if p.group.group_type == "q" and p.group.qgroups[0].question == question:
            val[2] = True
        pageData.append(val)
        pageFiles.append(p.image.file_name)
    # give HW pages by question
    for qref in tref.qgroups.order_by(QGroup.question):
        for p in qref.group.hwpages:
            val = ["h{}.{}".format(q, p.order), p.image.id, False]
            if qref.question == question:  # check if page belongs to our question
                val[2] = True
            pageData.append(val)
            pageFiles.append(p.image.file_name)
    # then give LPages
    for p in tref.lpages.order_by(LPage.order):
        pageData.append(["x{}".format(p.order), p.image.id, False])
        pageFiles.append(p.image.file_name)
    return [True, pageData] + pageFiles


def MshuffleImages(self, user_name, task, image_ref_list):
    """Rearrange page images in the annotation for that task.
    Permutation given by the references inside the image_ref_list.
    """
    uref = User.get(name=user_name)  # authenticated, so not-None

    with plomdb.atomic():
        gref = Group.get(Group.gid == task)
        qref = gref.qgroups[0]
        if qref.user != uref:
            return [False]  # not your task
        # grab the last annotation
        aref = gref.qgroups[0].annotations[-1]
        # delete the old pages
        for p in aref.apages:
            p.delete_instance()
        # now create new apages
        ord = 0
        for iref in image_ref_list:
            ord += 1
            APage.create(annotation=aref, image=iref, order=ord)
        aref.time = datetime.now()
        uref.last_activity = datetime.now()
        uref.last_action = "Shuffled images of {}".format(task)
        aref.save()
        uref.save()
    log.info("MshuffleImages - task {} now irefs {}".format(task, image_ref_list))
    return [True]


def MreviewQuestion(self, test_number, question, version):
    """Give ownership of the given marking task to the reviewer.
    """
    # shift ownership to "reviewer"
    revref = User.get(name="reviewer")  # should always be there

    tref = Test.get_or_none(Test.test_number == test_number)
    if tref is None:
        return [False]
    qref = QGroup.get_or_none(
        QGroup.test == tref,
        QGroup.question == question,
        QGroup.version == version,
        QGroup.marked == True,
    )
    if qref is None:
        return [False]
    with plomdb.atomic():
        qref.user = revref
        qref.time = datetime.now()
        qref.save()
    log.info("Setting tqv {}.{}.{} for reviewer".format(test_number, question, version))
    return [True]


def MrevertTask(self, task):
    """This needs work. The qgroup is set back to its original state, the annotations (and images) are deleted, and the corresponding to-delete-filenames are returned to the server which does the actual deleting of files. In future we should probably not delete any files and just move the references within the system?
    """
    gref = Group.get_or_none(Group.gid == task)
    if gref is None:
        return [False, "NST"]  # no such task
    # from the group get the test, question and sumdata - all need cleaning.
    qref = gref.qgroups[0]
    tref = gref.test
    sref = tref.sumdata[0]
    # check task is "done"
    if qref.status != "done" or qref.marked is False:
        return [False, "NAC"]  # nothing to do here
    # now update things
    log.info("Manager reverting task {}".format(task))
    with plomdb.atomic():
        # clean up test
        tref.marked = False
        tref.totalled = False
        tref.save()
        # clean up sum-data - no one should be totalling and marking at same time.
        # TODO = sort out the possible idiocy caused by simultaneous marking+totalling by client.
        sref.status = "todo"
        sref.sum_mark = None
        sref.user = None
        sref.time = datetime.now()
        sref.summed = False
        sref.save()
        # clean up the qgroup
        qref.marked = False
        qref.status = "todo"
        qref.user = None
        qref.save()
        rval = [True]  # keep list of files to delete.
        # now clean up annotations
        for aref in qref.annotations:
            if aref.edition == 0:  # leave 0th annotation alone.
                continue
            # delete the apages and then the annotation itself
            for pref in aref.apages:
                pref.delete_instance()
            rval.append(aref.plom_file)
            rval.append(aref.comment_file)
            rval.append(aref.image.file_name)
            # delete the annotated image from table.
            aref.image.delete_instance()
            # finally delete the annotation itself.
            aref.delete_instance()
    log.info("Reverting tq {}.{}".format(test_number, question))
    return rval