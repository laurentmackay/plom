# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2022 Edith Coates

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.exceptions import APIException
from rest_framework import status

from Papers.services import SpecificationService


class GetSpecification(APIView):
    """
    Return the public part of the specification.

    Returns:
        (200) JsonResponse: the spec
        (400) spec not found
    """

    def get(self, request):
        spec = SpecificationService()
        if not spec.is_there_a_spec():
            exc = APIException()
            exc.status_code = status.HTTP_400_BAD_REQUEST
            exc.detail = "Server does not have a spec."
            raise exc

        the_spec = spec.get_the_spec()
        the_spec.pop("privateSeed", None)
        the_spec.pop("publicCode", None)

        return Response(the_spec)


class ServerVersion(APIView):
    """
    Get the server version. (Debug: hardcoded for now)
    """

    def get(self, request):
        version = "Plom server version 0.12.0.dev with API 55"
        return Response(version)