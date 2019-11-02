# -*- coding: utf-8 -*-

"""
Backend bits n bobs to talk to the server
"""

__author__ = "Andrew Rechnitzer, Colin B. Macdonald"
__copyright__ = "Copyright (C) 2018-2019 Andrew Rechnitzer, Colin B. Macdonald"
__credits__ = ["Andrew Rechnitzer", "Colin Macdonald", "Elvis Cai", "Matt Coles"]
__license__ = "AGPL-3.0-or-later"
# SPDX-License-Identifier: AGPL-3.0-or-later

import sys
import asyncio
import easywebdav2
import json
import ssl
from PyQt5.QtWidgets import QMessageBox
import urllib3
from useful_classes import ErrorMessage
import time
import threading

sys.path.append("..")  # this allows us to import from ../resources
from resources.version import Plom_API_Version

# If we use unverified ssl certificates we get lots of warnings,
# so put in this to hide them.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
sslContext = ssl.create_default_context(purpose=ssl.Purpose.CLIENT_AUTH)
sslContext.check_hostname = False
# Server defaults
server = "127.0.0.1"
message_port = 41984
webdav_port = 41985
SRmutex = threading.Lock()
_userName = None
_token = None


def setServerDetails(s, mp, dp):
    """Set the server IP, message port and webdav port"""
    global server, message_port, webdav_port
    server = s
    message_port = mp
    webdav_port = dp


async def handle_messaging(msg):
    """Asyncio messager handler.
    Sends message over the connection.
    Message should be a list [cmd, user, password, arg1, arg2, etc]
    Reads return message from the stream - usually ['ACK', arg1, arg2,...]
    """
    reader, writer = await asyncio.open_connection(
        server, message_port, loop=loop, ssl=sslContext
    )
    # Message should be  [cmd, user, password, arg1, arg2, etc]
    jm = json.dumps(msg)
    writer.write(jm.encode())
    # SSL does not support EOF, so send a null byte to indicate the end
    # of the message.
    writer.write(b"\x00")
    await writer.drain()

    # data = await reader.read(100)
    data = await reader.readline()
    terminate = data.endswith(b"\x00")
    data = data.rstrip(b"\x00")
    rmesg = json.loads(data.decode())  # message should be a list [ACK, arg1, arg2, etc]
    writer.close()
    return rmesg


def requestAndSaveToken(user, pw):
    """Get a authorisation token from the server

    The request sends name and password (over ssl) to the server. If
    hash of password matches the one on file, then the server sends
    back an "ACK" and an authentication token. The token is then used
    to authenticate future transactions with the server (since
    password hashing is slow).

    Raise a ValueError with message from the server.

    TODO: what happens on timeout?
    """
    global _userName, _token
    msg, token = SRMsg(["AUTH", user, pw, Plom_API_Version])
    if not msg == "ACK":
        raise ValueError(token)
    _userName = user
    _token = token


def msg(msgcode, *args):
    """Send message to server and get back a reply"""
    a = (msgcode, _userName, _token, *args)
    return SRMsg(a)


def SRMsg(msg):
    """Send message using the asyncio message handler and get back
    return message. If error then pop-up an error message.
    """
    #N = 0.5
    #print("Messenger [{}]: want to do '{}', acquiring mutex first...".format(str(threading.get_ident()), msg[0]))
    SRmutex.acquire()
    try:
        #print("Messenger: got mutex, pretending to work for {}s, then talking to server".format(N))

        #time.sleep(N)
        rmsg = loop.run_until_complete(handle_messaging(msg))
    finally:
        SRmutex.release()
    #print("Messenger [{}]: got rmsg = {}".format(str(threading.get_ident()), str(rmsg)))
    if rmsg[0] == "ACK":
        return rmsg
    elif rmsg[0] == "ERR":
        msg = ErrorMessage("Server says: " + rmsg[1])
        msg.exec_()
        return rmsg
    else:
        print(">>> Error I didn't expect. Return message was {}".format(rmsg))
        msg = ErrorMessage("Something really wrong has happened.")
        msg.exec_()


def SRMsg_nopopup(msg):
    """Send message using the asyncio message handler and get back
    return message.
    """
    #N = 15
    #print("Messenger [nopop, {}]: want to do '{}', acquiring mutex first...".format(str(threading.get_ident()), msg[0]))
    SRmutex.acquire()
    try:
        #print("Messenger [nopop]: got mutex, pretending to work for {}s, then talking to server".format(N))
        #time.sleep(N)
        rmsg = loop.run_until_complete(handle_messaging(msg))
    finally:
        SRmutex.release()
    #print("Messenger [nopop, {}]: got rmsg = {}".format(str(threading.get_ident()), str(rmsg)))
    if rmsg[0] in ("ACK", "ERR"):
        return rmsg
    else:
        raise RuntimeError("Unexpected response from server.  Consider filing a bug?  The return from the server was:\n\n" + str(rmsg))


def getFileDav(dfn, lfn):
    """Get file dfn from the webdav server and save as lfn."""
    webdav = easywebdav2.connect(
        server, port=webdav_port, protocol="https", verify_ssl=False
    )
    try:
        webdav.download(dfn, lfn)
    except Exception as ex:
        template = ">>> An exception of type {0} occurred. Arguments:\n{1!r}"
        message = template.format(type(ex).__name__, ex.args)
        print(message)


def putFileDav(lfn, dfn):
    """Upload file lfn to the webdav as dfn."""
    webdav = easywebdav2.connect(
        server, port=webdav_port, protocol="https", verify_ssl=False
    )
    try:
        webdav.upload(lfn, dfn)
    except Exception as ex:
        template = ">>> An exception of type {0} occurred. Arguments:\n{1!r}"
        message = template.format(type(ex).__name__, ex.args)
        print(message)


async def handle_ping_test():
    """ A simple ping to test if the server is up and running.
    If nothing back after a few seconds then assume the server is
    down and tell the user, then exit.
    """
    ptest = asyncio.open_connection(server, message_port, loop=loop, ssl=sslContext)
    try:
        reader, writer = await asyncio.wait_for(ptest, timeout=6)
        jm = json.dumps(["PING"])
        writer.write(jm.encode())
        writer.write(b"\x00")
        await writer.drain()

        data = await reader.read(100)
        terminate = data.endswith(b"\x00")
        data = data.rstrip(b"\x00")
        rmesg = json.loads(data.decode())  # message should be ['ACK']
        writer.close()
        return True
    except asyncio.TimeoutError as e:
        # TODO: str(e) does nothing useful to keep separate from below
        msg = ErrorMessage(
            "Server timed out.  " \
            "Please double check details and try again."
        )
        msg.exec_()
        return False
    except (ConnectionRefusedError, OSError) as e:
        msg = ErrorMessage(
            "Server does not return ping.  " \
            "Please double check details and try again.\n\n" \
            "Details:\n" + str(e)
        )
        msg.exec_()
        return False


def pingTest():
    """Use the asyncio handler to send a ping to the server
    to check it is up and running
    """
    rmsg = loop.run_until_complete(handle_ping_test())
    return rmsg


def startMessenger():
    """Start the asyncio event loop"""
    global loop
    print("Starting asyncio loop")
    loop = asyncio.get_event_loop()


def stopMessenger():
    """Stop the asyncio event loop"""
    loop.close()
    print("Stopped asyncio loop")
