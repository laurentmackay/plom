# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2021 Colin B. Macdonald

import os
from pathlib import Path
from pytest import raises

from plom.server import PlomQuickDemoServer


def setup_module(module):
    # TODO: get a random port from OS instead?
    module.Test.server = PlomQuickDemoServer(
        port=41981, scans=False, backend="multiprocessing"
    )
    module.Test.env = {**os.environ, **module.Test.server.get_env_vars()}


def teardown_module(module):
    module.Test.server.stop(erase_dir=True)


class Test:
    def test_its_alive(self):
        assert self.server.process_is_running()

    def test_has_pid(self):
        assert self.server.process_pid()

    def test_can_ping(self):
        assert self.server.ping_server()

    def test_is_multiprocessing(self):
        assert hasattr(self.server, "_server_proc")
        # subprocess has wait, multiprocessing as join
        assert hasattr(self.server._server_proc, "join")
