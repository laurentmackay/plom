# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2020 Andrew Rechnitzer
# Copyright (C) 2019-2023 Colin B. Macdonald

"""Backend bits 'n bobs to talk to a Plom server."""

import hashlib
from io import BytesIO
import json
import logging
import mimetypes
from typing import Union, Tuple

import requests
from requests_toolbelt import MultipartEncoder

from plom.baseMessenger import BaseMessenger
from plom.scanMessenger import ScanMessenger
from plom.managerMessenger import ManagerMessenger
from plom.plom_exceptions import PlomSeriousException
from plom.plom_exceptions import (
    PlomAuthenticationException,
    PlomConflict,
    PlomTakenException,
    PlomRangeException,
    PlomVersionMismatchException,
    PlomTaskChangedError,
    PlomTaskDeletedError,
    PlomTimeoutError,
)


__all__ = [
    "Messenger",
    "ManagerMessenger",
    "ScanMessenger",
]

log = logging.getLogger("messenger")
# requests_log = logging.getLogger("urllib3")
# requests_log.setLevel(logging.DEBUG)
# requests_log.propagate = True


class Messenger(BaseMessenger):
    """Handle communication with a Plom Server."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    # ------------------------
    # ------------------------
    # ID client API stuff

    def IDprogressCount(self):
        """Return info about progress on identifiying.

        Return:
            list: with two integers, indicating the number of papers
            identified and the total number of papers to be identified.

        Raises:
            PlomAuthenticationException:
            PlomSeriousException: something unexpected happened.
        """
        with self.SRmutex:
            try:
                response = self.get(
                    "/ID/progress",
                    json={"user": self.user, "token": self.token},
                )
                # throw errors when response code != 200.
                response.raise_for_status()
                return response.json()
            except requests.HTTPError as e:
                if response.status_code == 401:
                    raise PlomAuthenticationException(response.reason) from None
                raise PlomSeriousException(f"Some other sort of error {e}") from None

    def IDaskNextTask(self):
        """Return the TGV of a paper that needs IDing.

        Return:
            string or None if no papers need IDing.

        Raises:
            SeriousError: if something has unexpectedly gone wrong.
        """
        self.SRmutex.acquire()
        try:
            response = self.get(
                "/ID/tasks/available",
                json={"user": self.user, "token": self.token},
            )
            # throw errors when response code != 200.
            response.raise_for_status()
            if response.status_code == 204:
                return None
            tgv = response.json()
            return tgv
        except requests.HTTPError as e:
            if response.status_code == 401:
                raise PlomAuthenticationException() from None
            raise PlomSeriousException(f"Some other sort of error {e}") from None
        finally:
            self.SRmutex.release()

    def IDrequestDoneTasks(self):
        self.SRmutex.acquire()
        try:
            response = self.get(
                "/ID/tasks/complete",
                json={"user": self.user, "token": self.token},
            )
            response.raise_for_status()
            idList = response.json()
            return idList
        except requests.HTTPError as e:
            if response.status_code == 401:
                raise PlomAuthenticationException() from None
            raise PlomSeriousException(f"Some other sort of error {e}") from None
        finally:
            self.SRmutex.release()

    # ------------------------

    def IDclaimThisTask(self, code):
        with self.SRmutex:
            try:
                response = self.patch(
                    f"/ID/tasks/{code}",
                    json={"user": self.user, "token": self.token},
                )
                response.raise_for_status()
            except requests.HTTPError as e:
                if response.status_code == 401:
                    raise PlomAuthenticationException() from None
                if response.status_code == 409:
                    raise PlomTakenException(response.reason)
                raise PlomSeriousException(f"Some other sort of error {e}") from None

    def IDreturnIDdTask(self, task, studentID, studentName):
        """Return a completed IDing task: identify a paper.

        Exceptions:
            PlomConflict: `studentID` already used on a different paper.
            PlomTakenException: someone else owns that task.  This is unexpected
                if you Claimed this task.
            PlomRangeException: no such test number or not yet scanned
            PlomAuthenticationException: login problems.
            PlomSeriousException: other errors.
        """
        with self.SRmutex:
            try:
                response = self.put(
                    f"/ID/tasks/{task}",
                    json={
                        "user": self.user,
                        "token": self.token,
                        "sid": studentID,
                        "sname": studentName,
                    },
                )
                response.raise_for_status()
            except requests.HTTPError as e:
                if response.status_code == 409:
                    raise PlomConflict(response.reason) from None
                if response.status_code == 401:
                    raise PlomAuthenticationException(response.reason) from None
                if response.status_code == 403:
                    raise PlomTakenException(response.reason) from None
                if response.status_code == 404:
                    raise PlomRangeException(response.reason) from None
                raise PlomSeriousException(f"Some other sort of error {e}") from None

    # ------------------------
    # ------------------------
    # Marker stuff
    def MrequestDoneTasks(self, q, v):
        self.SRmutex.acquire()
        try:
            response = self.get(
                "/MK/tasks/complete",
                json={"user": self.user, "token": self.token, "q": q, "v": v},
            )
            response.raise_for_status()
            mList = response.json()
            return mList
        except requests.HTTPError as e:
            if response.status_code == 401:
                raise PlomAuthenticationException() from None
            raise PlomSeriousException(f"Some other sort of error {e}") from None
        finally:
            self.SRmutex.release()

    def MprogressCount(self, q, v):
        """Return info about progress on a particular question-version pair.

        Args:
            q (str/int): a question number.
            v (str/int): a version number.

        Return:
            list: with two integers, indicating the number of questions
            graded and the total number of questions to be graded of
            this question-version pair.

        Raises:
            PlomRangeException: `q` or `v` is out of range.
            PlomAuthenticationException:
            PlomSeriousException: something unexpected happened, such as
                non-integer `q` or `v`.
        """
        with self.SRmutex:
            try:
                response = self.get(
                    "/MK/progress",
                    json={"user": self.user, "token": self.token, "q": q, "v": v},
                )
                # throw errors when response code != 200.
                response.raise_for_status()
                return response.json()
            except requests.HTTPError as e:
                if response.status_code == 401:
                    raise PlomAuthenticationException(response.reason) from None
                if response.status_code == 416:
                    raise PlomRangeException(response.reason) from None
                raise PlomSeriousException(f"Some other sort of error {e}") from None

    def MaskNextTask(self, q, v, tag=None, above=None):
        """Ask server for a new marking task, return tgv or None.

        Args:
            q (int): question.
            v (int): version.

        Keyword Args:
            tag (str/None): if any tasks are available with this tag,
                we have a preference for those.  (But we will still
                accept tasks without the tag).
            above (int/None): start asking for tasks with paper
                number at least this large, but wrapping around if
                necessary.

        If you specify both ``tag`` and ``above``, the logic is
        currently "or" but this could change without notice!

        Returns:
            str/None: either the task string or `None` indicated no
            more tasks available.

        TODO: why are we using json for a string return?
        """
        self.SRmutex.acquire()
        try:
            if self.webplom:
                response = self.get(
                    f"/MK/tasks/available?q={q}&v={v}&above={above}&tag={tag}",
                    json={
                        "user": self.user,
                        "token": self.token,
                    },
                )
            else:
                response = self.get(
                    "/MK/tasks/available",
                    json={
                        "user": self.user,
                        "token": self.token,
                        "q": q,
                        "v": v,
                        "above": above,
                        "tag": tag,
                    },
                )
            # throw errors when response code != 200.
            if response.status_code == 204:
                return None
            response.raise_for_status()
            tgv = response.json()
            return tgv
        except requests.HTTPError as e:
            if response.status_code == 401:
                raise PlomAuthenticationException() from None
            raise PlomSeriousException(f"Some other sort of error {e}") from None
        finally:
            self.SRmutex.release()

    def MclaimThisTask(self, code, version):
        """Claim a task from server and get back metadata.

        Args:
            code (str): a task code such as `"q0123g2"`.

        Returns:
            list: Consisting of image_metadata, [list of tags], integrity_check.

        Raises:
            PlomTakenException: someone got it before you
            PlomRangeException: no such test number or not yet scanned
            PlomVersionMismatchException: the version supplied does not
                match the task's version.
            PlomAuthenticationException:
            PlomSeriousException: generic unexpected error
        """
        with self.SRmutex:
            try:
                response = self.patch(
                    f"/MK/tasks/{code}",
                    json={"user": self.user, "token": self.token, "version": version},
                )
                response.raise_for_status()
                return response.json()
            except requests.HTTPError as e:
                if response.status_code == 401:
                    raise PlomAuthenticationException() from None
                if response.status_code == 409:
                    raise PlomTakenException(response.reason) from None
                if response.status_code == 417:
                    raise PlomVersionMismatchException(response.reason) from None
                if response.status_code == 404:
                    raise PlomRangeException(response.reason) from None
                if response.status_code == 410:
                    raise PlomRangeException(response.reason) from None
                raise PlomSeriousException(f"Some other sort of error {e}") from None

    def MlatexFragment(self, latex: str) -> Tuple[bool, Union[bytes, str]]:
        """Give some text to the server, it comes back as a PNG image processed via TeX.

        Args:
            latex: a fragment of text including TeX markup.

        Returns:
            `(True, png_bytes)` or `(False, fail_reason)`.
        """
        with self.SRmutex:
            try:
                response = self.post_auth(
                    "/MK/latex",
                    json={"fragment": latex},
                )
                response.raise_for_status()
                image = BytesIO(response.content).getvalue()
                return (True, image)
            except requests.HTTPError as e:
                if response.status_code == 401:
                    raise PlomAuthenticationException() from None
                if response.status_code == 406:
                    r = response.json()
                    assert r["error"]
                    return (False, r["tex_output"])
                    # raise PlomLatexException(
                    #     f"Server reported an error processing your TeX fragment:\n\n{response.text}"
                    # ) from None
                raise PlomSeriousException(f"Some other sort of error {e}") from None

    def MreturnMarkedTask(
        self,
        code,
        pg,
        ver,
        score,
        marking_time,
        annotated_img,
        plomfile,
        rubrics,
        integrity_check,
    ):
        """Upload annotated image and associated data to the server.

        Args:
            code (str): e.g., "q0003g1"
            pg (int): question number.
            ver (int): which version.
            marking_time (int/float): number of seconds spend on grading
                the paper.
            annotated_img (pathlib.Path): the annotated image, either a
                png or a jpeg.
            plomfile (pathlib.Path): machine-readable json of annotations
                on the page.
            rubrics (list): list of rubric IDs used on the page.
            integrity_check (str): a blob that the server expects to get
                back.

        Returns:
            list: a 2-list of the form `[#done, #total]`.

        Raises:
            PlomAuthenticationException
            PlomConflict: integrity check failed, perhaps manager
                altered task.
            PlomTimeoutError: network trouble such as timeouts.
            PlomTaskChangedError
            PlomTaskDeletedError
            PlomSeriousException
        """
        # can't change the legacy api during 0.12.x, which expects the src_img_data
        # duplicated outside of plomfile.
        # TODO: take it out of the django API, and pass `pdict` instead of file.
        with open(plomfile, "rb") as f:
            pdict = json.load(f)
        image_md5_list = pdict["base_images"]

        if self.webplom:
            return self._MreturnMarkedTask_webplom(
                code,
                pg,
                ver,
                score,
                marking_time,
                annotated_img,
                plomfile,
                integrity_check,
            )

        img_mime_type = mimetypes.guess_type(annotated_img)[0]
        with self.SRmutex:
            try:
                with open(annotated_img, "rb") as fh, open(plomfile, "rb") as f2:
                    # doesn't like ints, so convert ints to strings
                    param = {
                        "user": self.user,
                        "token": self.token,
                        "pg": str(pg),
                        "ver": str(ver),
                        "score": str(score),
                        "mtime": str(round(marking_time)),
                        "rubrics": rubrics,
                        "md5sum": hashlib.md5(fh.read()).hexdigest(),
                        "integrity_check": integrity_check,
                        "image_md5s": image_md5_list,
                    }
                    # reset stream position to start before reading again
                    fh.seek(0)
                    dat = MultipartEncoder(
                        fields={
                            "param": json.dumps(param),
                            "annotated": (annotated_img.name, fh, img_mime_type),
                            "plom": (plomfile.name, f2, "text/plain"),
                        }
                    )
                    # increase read timeout relative to default: Issue #1575
                    timeout = (self.default_timeout[0], 3 * self.default_timeout[1])
                    response = self.put(
                        f"/MK/tasks/{code}",
                        data=dat,
                        headers={"Content-Type": dat.content_type},
                        timeout=timeout,
                    )
                response.raise_for_status()
                return response.json()
            except (requests.ConnectionError, requests.Timeout) as e:
                raise PlomTimeoutError(
                    "Upload timeout/connect error: {}\n\n".format(e)
                    + "Retries are NOT YET implemented: as a workaround,"
                    + "you can re-open the Annotator on '{}'.\n\n".format(code)
                    + "We will now process any remaining upload queue."
                ) from None
            except requests.HTTPError as e:
                if response.status_code == 401:
                    raise PlomAuthenticationException() from None
                if response.status_code == 406:
                    if response.text == "integrity_fail":
                        raise PlomConflict(
                            "Integrity fail: can happen if manager altered task while you annotated"
                        ) from None
                    raise PlomSeriousException(response.text) from None
                if response.status_code == 409:
                    raise PlomTaskChangedError("Task ownership has changed.") from None
                if response.status_code == 410:
                    raise PlomTaskDeletedError(
                        "No such task - it has been deleted from server."
                    ) from None
                if response.status_code == 400:
                    raise PlomSeriousException(response.text) from None
                raise PlomSeriousException(f"Some other sort of error {e}") from None

    def _MreturnMarkedTask_webplom(
        self,
        code,
        pg,
        ver,
        score,
        marking_time,
        annotated_img,
        plomfile,
        integrity_check,
    ):
        """Upload annotated image and data to Django server, using it's built-in multipart data handling.

        See :meth:`MreturnMarkedTask` for docs.
        """
        with self.SRmutex:
            try:
                with open(annotated_img, "rb") as annot_img_file, open(
                    plomfile, "rb"
                ) as plom_data_file:
                    data = {
                        "pg": str(pg),
                        "ver": str(ver),
                        "score": str(score),
                        "marking_time": marking_time,
                        "md5sum": hashlib.md5(annot_img_file.read()).hexdigest(),
                        "integrity_check": integrity_check,
                    }

                    annot_img_file.seek(0)

                    # automatically puts the filename in
                    files = {
                        "annotation_image": annot_img_file,
                        "plomfile": plom_data_file,
                    }

                    # increase read timeout relative to default: Issue #1575
                    timeout = (self.default_timeout[0], 3 * self.default_timeout[1])
                    response = self.post_auth(
                        f"/MK/tasks/{code}",
                        data=data,
                        files=files,
                        timeout=timeout,
                    )
                    response.raise_for_status()
                    return response.json()
            except (requests.ConnectionError, requests.Timeout) as e:
                raise PlomTimeoutError(
                    "Upload timeout/connect error: {}\n\n".format(e)
                    + "Retries are NOT YET implemented: as a workaround,"
                    + "you can re-open the Annotator on '{}'.\n\n".format(code)
                    + "We will now process any remaining upload queue."
                ) from None
            except requests.HTTPError as e:
                if response.status_code == 401:
                    raise PlomAuthenticationException() from None
                if response.status_code == 406:
                    if response.text == "integrity_fail":
                        raise PlomConflict(
                            "Integrity fail: can happen if manager altered task while you annotated"
                        ) from None
                    raise PlomSeriousException(response.text) from None
                if response.status_code == 409:
                    raise PlomTaskChangedError("Task ownership has changed.") from None
                if response.status_code == 410:
                    raise PlomTaskDeletedError(
                        "No such task - it has been deleted from server."
                    ) from None
                if response.status_code == 400:
                    raise PlomSeriousException(response.text) from None
                raise PlomSeriousException(f"Some other sort of error {e}") from None

    def MgetUserRubricTabs(self, question):
        """Ask server for the user's rubric-tabs config file for this question.

        Args:
            question (int): which question to save to (rubric tabs are
                generally per-question).

        Raises:
            PlomAuthenticationException
            PlomSeriousException

        Returns:
            dict/None: a dict of information about user's tabs for that
            question or `None` if server has no saved tabs for that
            user/question pair.
        """
        self.SRmutex.acquire()
        try:
            response = self.get(
                f"/MK/user/{self.user}/{question}",
                json={
                    "user": self.user,
                    "token": self.token,
                    "question": question,
                },
            )
            response.raise_for_status()

            if response.status_code == 200:
                return response.json()
            elif response.status_code == 204:
                return None
            else:
                raise PlomSeriousException(
                    "No other 20x response expected from server."
                ) from None

        except requests.HTTPError as e:
            if response.status_code in (401, 403):
                raise PlomSeriousException(response.text) from None
            raise PlomSeriousException(
                f"Error of type {e} when creating new rubric"
            ) from None
        finally:
            self.SRmutex.release()

    def MsaveUserRubricTabs(self, question, tab_config):
        """Cache the user's rubric-tabs config for this question onto the server.

        Args:
            question (int): the current question number
            tab_config (dict): the user's rubric pane configuration for
                this question.

        Raises:
            PlomAuthenticationException
            PlomSeriousException

        Returns:
            None
        """
        self.SRmutex.acquire()
        try:
            response = self.put(
                f"/MK/user/{self.user}/{question}",
                json={
                    "user": self.user,
                    "token": self.token,
                    "question": question,
                    "rubric_config": tab_config,
                },
            )
            response.raise_for_status()

        except requests.HTTPError as e:
            if response.status_code in (401, 403):
                raise PlomSeriousException(response.text) from None
            raise PlomSeriousException(
                f"Error of type {e} when creating new rubric"
            ) from None
        finally:
            self.SRmutex.release()
