# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2023 Andrew Rechnitzer
# Copyright (C) 2023 Colin B. Macdonald

from django.test import TestCase
from django.contrib.auth.models import User, Group
from django.core.exceptions import PermissionDenied, ObjectDoesNotExist
from model_bakery import baker

from ..models import StagingBundle, StagingImage
from ..models import (
    UnknownStagingImage,
    KnownStagingImage,
    ErrorStagingImage,
    DiscardStagingImage,
    ExtraStagingImage,
)
from ..services import ScanCastService


class ScanCastServiceTests(TestCase):
    def make_image(self, image_type):
        # put images into first available order
        number_of_pages = self.bundle.stagingimage_set.count()
        img = baker.make(
            StagingImage,
            bundle=self.bundle,
            bundle_order=number_of_pages,
            image_type=image_type,
        )

        if image_type == StagingImage.UNKNOWN:
            baker.make(UnknownStagingImage, staging_image=img)
        elif image_type == StagingImage.KNOWN:
            baker.make(KnownStagingImage, staging_image=img)
        elif image_type == StagingImage.EXTRA:
            baker.make(ExtraStagingImage, staging_image=img)
        elif image_type == StagingImage.DISCARD:
            baker.make(DiscardStagingImage, staging_image=img)
        elif image_type == StagingImage.ERROR:
            baker.make(ErrorStagingImage, staging_image=img)
        else:
            raise RuntimeError(f"Do not recognise image type '{image_type}'")

    def setUp(self):
        # make scan-group, two users, one with permissions and the other not.
        scan_group = baker.make(Group, name="scanner")
        self.user0 = baker.make(User, username="user0")
        self.user0.groups.add(scan_group)
        self.user0.save()
        self.user1 = baker.make(User, username="user1")
        # make a bundle
        self.bundle = baker.make(StagingBundle, user=self.user0, slug="testbundle")
        # make some pages
        for img in [
            StagingImage.UNKNOWN,
            StagingImage.UNKNOWN,
            StagingImage.KNOWN,
            StagingImage.KNOWN,
            StagingImage.EXTRA,
            StagingImage.EXTRA,
            StagingImage.DISCARD,
            StagingImage.DISCARD,
            StagingImage.ERROR,
            StagingImage.ERROR,
            StagingImage.EXTRA,
            StagingImage.EXTRA,
            StagingImage.EXTRA,
            StagingImage.EXTRA,
        ]:
            self.make_image(img)

        return super().setUp()

    def tearDown(self):
        return super().tearDown()

    def test_permissions(self):
        scs = ScanCastService()
        # get the ord of an error page from the bundle
        ord = (
            self.bundle.stagingimage_set.filter(image_type=StagingImage.ERROR)
            .first()
            .bundle_order
        )

        with self.assertRaises(PermissionDenied):
            scs.discard_image_type_from_bundle_cmd(
                "user1", "testbundle", ord, image_type=StagingImage.ERROR
            )
        with self.assertRaises(PermissionDenied):
            scs.unknowify_image_type_from_bundle_cmd(
                "user1", "testbundle", ord, image_type=StagingImage.ERROR
            )

        scs.discard_image_type_from_bundle_cmd(
            "user0", "testbundle", ord, image_type=StagingImage.ERROR
        )
        # get the ord of another error page from the bundle
        ord = (
            self.bundle.stagingimage_set.filter(image_type=StagingImage.ERROR)
            .first()
            .bundle_order
        )
        scs.unknowify_image_type_from_bundle_cmd(
            "user0", "testbundle", ord, image_type=StagingImage.ERROR
        )

    def test_cast_to_discard(self):
        for img_type, typemodel, typestr, reason in [
            (
                StagingImage.ERROR,
                ErrorStagingImage,
                "errorstagingimage",
                "Error page discarded by user0",
            ),
            (
                StagingImage.EXTRA,
                ExtraStagingImage,
                "extrastagingimage",
                "Extra page discarded by user0",
            ),
            (
                StagingImage.KNOWN,
                KnownStagingImage,
                "knownstagingimage",
                "Known page discarded by user0",
            ),
            (
                StagingImage.UNKNOWN,
                UnknownStagingImage,
                "unknownstagingimage",
                "Unknown page discarded by user0",
            ),
        ]:
            # get the order of an page from the bundle
            ord = (
                self.bundle.stagingimage_set.filter(image_type=img_type)
                .first()
                .bundle_order
            )

            # grab the corresponding staging_image
            stimg = StagingImage.objects.get(bundle=self.bundle, bundle_order=ord)
            self.assertIsNotNone(getattr(stimg, typestr))
            # verify no discard image there
            with self.assertRaises(ObjectDoesNotExist):
                DiscardStagingImage.objects.get(staging_image=stimg)
            # cast it to a discard
            ScanCastService().discard_image_type_from_bundle_cmd(
                "user0", "testbundle", ord, image_type=img_type
            )
            # verify that no error image remains and that a discard image now exists
            stimg.refresh_from_db()
            with self.assertRaises(ObjectDoesNotExist):
                typemodel.objects.get(staging_image=stimg)
            # verify that a discard image exists
            self.assertIsNotNone(stimg.discardstagingimage)
            # verify discard reason
            self.assertEqual(
                reason,
                stimg.discardstagingimage.discard_reason,
            )

    def test_cast_to_unknown(self):
        for img_type, typemodel, typestr in [
            (StagingImage.ERROR, ErrorStagingImage, "errorstagingimage"),
            (StagingImage.EXTRA, ExtraStagingImage, "extrastagingimage"),
            (StagingImage.KNOWN, KnownStagingImage, "knownstagingimage"),
            (StagingImage.DISCARD, DiscardStagingImage, "discardstagingimage"),
        ]:
            # get the order of an page from the bundle
            ord = (
                self.bundle.stagingimage_set.filter(image_type=img_type)
                .first()
                .bundle_order
            )
            # grab the corresponding staging_image
            stimg = StagingImage.objects.get(bundle=self.bundle, bundle_order=ord)
            self.assertIsNotNone(getattr(stimg, typestr))
            # verify no discard image there
            with self.assertRaises(ObjectDoesNotExist):
                UnknownStagingImage.objects.get(staging_image=stimg)
            # cast it to a discard
            ScanCastService().unknowify_image_type_from_bundle_cmd(
                "user0", "testbundle", ord, image_type=img_type
            )
            # verify that no error image remains and that a discard image now exists
            stimg.refresh_from_db()
            with self.assertRaises(ObjectDoesNotExist):
                typemodel.objects.get(staging_image=stimg)
            # verify that an unknown image exists
            self.assertIsNotNone(stimg.unknownstagingimage)

    def test_attempt_discard_discard(self):
        ord = (
            self.bundle.stagingimage_set.filter(image_type=StagingImage.DISCARD)
            .first()
            .bundle_order
        )
        with self.assertRaises(ValueError):
            ScanCastService().discard_image_type_from_bundle_cmd(
                "user0", "testbundle", ord, image_type=StagingImage.DISCARD
            )

    def test_attempt_unknowify_unknown(self):
        ord = (
            self.bundle.stagingimage_set.filter(image_type=StagingImage.UNKNOWN)
            .first()
            .bundle_order
        )
        with self.assertRaises(ValueError):
            ScanCastService().unknowify_image_type_from_bundle_cmd(
                "user0", "testbundle", ord, image_type=StagingImage.UNKNOWN
            )

    def test_attempt_modify_pushed(self):
        # set the bundle to "pushed"
        self.bundle.pushed = True
        self.bundle.save()
        # now grab an error page and attempt to modify it
        ord = (
            self.bundle.stagingimage_set.filter(image_type=StagingImage.ERROR)
            .first()
            .bundle_order
        )
        with self.assertRaises(ValueError):
            ScanCastService().discard_image_type_from_bundle_cmd(
                "user0", "testbundle", ord, image_type=StagingImage.ERROR
            )
        with self.assertRaises(ValueError):
            ScanCastService().unknowify_image_type_from_bundle_cmd(
                "user0", "testbundle", ord, image_type=StagingImage.ERROR
            )
