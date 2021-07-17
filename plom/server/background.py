# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2020 Andrew Rechnitzer
# Copyright (C) 2020-2021 Colin B. Macdonald
# Copyright (C) 2020 Victoria Schuster

"""A background Plom server.

This is a Plom server that forks a background process and returns
control to the caller with the server continuing in the background.
"""

import os
from multiprocessing import Process
from pathlib import Path
from shlex import split
import shutil
import subprocess

import toml

from plom import Default_Port
from plom import SpecVerifier
from plom.produce.demotools import buildDemoSourceFiles
from plom.server import theServer
from plom.server import specdir as specdirname
from plom.server import confdir
from plom.server.prepare import initialise_server
from plom.messenger import Messenger
from plom.plom_exceptions import PlomBenignException


class _PlomServerProcess(Process):
    def __init__(self, basedir):
        super().__init__()
        self.basedir = basedir

    def run(self):
        theServer.launch(self.basedir)


class PlomServer:
    @classmethod
    def initialise_server(cls, basedir, port=None):
        """Prepare a directory for a Plom server, roughly equivalent to `plom-server init` on cmdline.

        Args:
            port (int, None): internet port to use or None for default.
            basedir (Path-like/str): the base directory for the server.
                TODO: error/warning if it exists!
        """
        basedir = Path(basedir)
        basedir.mkdir(exist_ok=True)
        port = port if port else Default_Port
        initialise_server(basedir, port)

    initialize_server = initialise_server

    @classmethod
    def add_demo_users(cls, basedir):
        """Add users to a Plom server, roughly equivalent to `plom-server users` on cmdline.

        TODO: add features or other class methods to do other user settings.

        Args:
            basedir (Path-like/str): the base directory for the server.
        """
        # TODO: move these codes elsewhere?  Out of scripts?
        from plom.scripts.server import processUsers

        basedir = Path(basedir)
        basedir.mkdir(exist_ok=True)
        cwd = os.getcwd()
        try:
            os.chdir(basedir)
            processUsers(None, True, False, False)
        finally:
            os.chdir(cwd)

    @classmethod
    def add_demo_spec(cls, basedir, num_to_produce=10):
        """Add a spec file to a Plom server, roughly equivalent to `plom-build parse` cmdline.

        TODO: add features or other class methods?

        Args:
            basedir (Path-like/str): the base directory for the server.
            num_to_produce (int): the number of papers in the demo,
                defaults to 10.
        """
        basedir = Path(basedir)
        basedir.mkdir(exist_ok=True)
        specdir = basedir / specdirname
        specdir.mkdir(exist_ok=True)
        SpecVerifier.create_demo_template(
            basedir / "demoSpec.toml", num_to_produce=num_to_produce
        )
        sv = SpecVerifier.from_toml_file(basedir / "demoSpec.toml")
        sv.verifySpec()
        sv.checkCodes()
        sv.saveVerifiedSpec(verbose=True, basedir=basedir)
        if not buildDemoSourceFiles(basedir):
            raise RuntimeError("failed to build demo sources")

    def __init__(self, basedir=None, backend=None):
        """Start up Plom server to run in a separate process.

        Args:
            basedir (Path-like/str): the base directory for the server.
                Currently this must exist (use `plom-server init` etc).
                TODO: if does not exist, create and fill?
            backend (str/None): Controls the precise mechanism used to put
                the server into the background.  Probably you should not
                need to use this.  Can be the strings `"subprocess"` or
                `"multiprocessing"`.  Omit or set to None to choose the
                default (currently `"subprocess"`; subject to change).

        Raises:
            PermissionError: cannot write to `dir`.
            OSError: e.g., address already in use, various others.
            ...
        """
        if not basedir:
            raise ValueError('You must provide a directory as the "dir" parameter')
        self.basedir = Path(basedir)

        if backend is None:
            backend = "subprocess"
        if backend == "subprocess":
            self._pymp = False
        elif backend == "multiprocessing":
            self._pymp = True
        else:
            raise ValueError(f'background backend of "{backend}" is not supported')

        # TODO: if its empty we need to prepare?
        # if not any(self.basedir.iterdir()):
        #     print(f"PlomServer directory {dir} is empty: preparing demo")

        with open(self.basedir / confdir / "serverDetails.toml") as f:
            self.server_info = toml.load(f)

        if self._pymp:
            self._server_proc = _PlomServerProcess(self.basedir)
            self._server_proc.start()
        else:
            self._server_proc = subprocess.Popen(
                split(f"python3 -m plom.scripts.server launch {self.basedir}")
            )
        assert self.process_is_running()
        if not self.ping_server():
            # TODO: try to kill it?
            raise RuntimeError("The server did not successfully start")

    def process_is_running(self):
        """Forked/background process not yet dead.

        This just checks that the process is still running.  You probably
        want :py:method:`ping_server` to know if the server is responding.
        """
        if self._pymp:
            return self._server_proc.is_alive()
        # for subprocess, its a bit trickier
        try:
            self._server_proc.wait(0.01)
        except subprocess.TimeoutExpired:
            return True
        else:
            return False

    def process_pid(self):
        return self._server_proc.pid

    def _brief_wait(self, how_long=0.1):
        """Wait briefly on the subprocess, which should not have stopped.

        Returns:
            bool: True if process is still running, False if it stopped
                while we were waiting.
        """
        if self._pymp:
            r = self._server_proc.join(how_long)
            return r is None and self._server_proc.exitcode is None
        # for subprocess, very similar to checking if alive
        try:
            self._server_proc.wait(how_long)
        except subprocess.TimeoutExpired:
            return True
        else:
            return False

    def ping_server(self):
        """Try to connect to the background server.

        We sleep in a loop until we can ping the server.

        Args:
            TODO: kwargs number of retries etc?
            TODO: verbose kwarg?

        Returns
            bool: False if we cannot get a minimal response from the server.
        """
        m = Messenger(s=self.server_info["server"], port=self.server_info["port"])
        count = 0
        while True:
            assert self.process_is_running()
            assert self._brief_wait(0.25), "Server died on us!"
            try:
                r = m.start()
            except PlomBenignException:
                pass
            else:
                # successfully talked to server so break loop
                break
            count += 1
            if count >= 10:
                print("we tried 10 times but server is not up yet!")
                return False
        m.stop()
        assert self.process_is_running()
        return True

    def __del__(self):
        print(f'Deleting PlomServer object "{self}"')
        # at least once I saw it created without this attrib
        if hasattr(self, "_server_proc"):
            self.stop()

    def stop(self, erase_dir=False):
        """Take down the Plom server.

        Args:
            erase_dir (bool): by default, the files are left behind.
                Instead you can pass `True` to erase them.
                TODO: maybe only subclasses should allow this?
        """
        if self.process_is_running():
            print(f"Stopping PlomServer '{self}' in dir '{self.basedir}'")
            self._server_proc.terminate()
            # TODO: 10 sec timeout, then kill?
            if self._pymp:
                self._server_proc.join()
            else:
                self._server_proc.wait()
        if erase_dir:
            if self.basedir.exists():
                print(f'Erasing Plom server dir "{self.basedir}"')
                shutil.rmtree(self.basedir)
