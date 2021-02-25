# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2019-2021 Andrew Rechnitzer
# Copyright (C) 2020-2021 Colin B. Macdonald
# Copyright (C) 2020 Vala Vakilian

from aiohttp import web

from .routeutils import authenticate_by_token, authenticate_by_token_required_fields
from .routeutils import validate_required_fields, log_request
from .routeutils import log


class RubricHandler:
    def __init__(self, plomServer):
        self.server = plomServer

    # @routes.put("/MK/rubric")
    @authenticate_by_token_required_fields(["user", "rubric"])
    def McreateRubric(self, data, request):
        """Respond with updated comment list and add received comments to the database.

        Args:
            data (dict): A dictionary including user/token and the new rubric to be created
            request (aiohttp.web_request.Request): A request of type GET /MK/rubric.

        Returns:
            aiohttp.web_response.Response: either 200,newkey or 406 if sent rubric was incomplete
        """
        username = data["user"]
        new_rubric = data["rubric"]

        rval = self.server.McreateRubric(username, new_rubric)
        if rval[0]:  # worked - so return key
            return web.json_response(rval[1], status=200)
        else:  # failed - rubric sent is incomplete
            return web.Response(status=406)

    # @routes.get("/MK/rubric")
    @authenticate_by_token_required_fields(["user"])
    def MgetRubrics(self, data, request):
        """Respond with updated comment list and add received comments to the database.

        Args:
            data (dict): A dictionary including user/token
            request (aiohttp.web_request.Request): A request of type GET /MK/rubric.

        Returns:
            aiohttp.web_response.Response: List of all comments in DB
        """
        username = data["user"]

        rubrics = self.server.MgetRubrics()
        return web.json_response(rubrics, status=200)

    # @routes.put("/MK/rubric")
    @authenticate_by_token_required_fields(["user", "rubric"])
    def McreateRubric(self, data, request):
        """Add new rubric to DB and respond with its key

        Args:
            data (dict): A dictionary including user/token and the new rubric to be created
            request (aiohttp.web_request.Request): A request of type GET /MK/rubric.

        Returns:
            aiohttp.web_response.Response: either 200,newkey or 406 if sent rubric was incomplete
        """
        username = data["user"]
        new_rubric = data["rubric"]

        rval = self.server.McreateRubric(username, new_rubric)
        if rval[0]:  # worked - so return key
            return web.json_response(rval[1], status=200)
        else:  # failed - rubric sent is incomplete
            return web.Response(status=406)

    # @routes.patch("/MK/rubric/{key}")
    @authenticate_by_token_required_fields(["user", "rubric"])
    def MmodifyRubric(self, data, request):
        """Add modify rubric to DB and respond with its key

        Args:
            data (dict): A dictionary including user/token and the new rubric to be created
            request (aiohttp.web_request.Request): A request of type GET /MK/rubric.

        Returns:
            aiohttp.web_response.Response: either 200,newkey or
            406 if sent rubric was incomplete or inconsistent
        """
        username = data["user"]
        updated_rubric = data["rubric"]
        key = request.match_info["key"]

        if key != updated_rubric["id"]:  # key mismatch
            return web.Response(status=400)

        rval = self.server.MmodifyRubric(username, key, updated_rubric)
        if rval[0]:  # worked - so return key
            return web.json_response(rval[1], status=200)
        else:  # failed - rubric sent is incomplete
            if rval[1] == "incomplete":
                return web.Response(status=406)
            else:
                return web.Response(status=409)

    def setUpRoutes(self, router):
        """Adds the response functions to the router object.

        Args:
            router (aiohttp.web_urldispatcher.UrlDispatcher): Router object which we will add the response functions to.
        """
        router.add_put("/MK/rubric", self.McreateRubric)
        router.add_get("/MK/rubric", self.MgetRubrics)
        router.add_patch("/MK/rubric/{key}", self.MmodifyRubric)
