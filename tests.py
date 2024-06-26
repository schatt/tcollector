#!/usr/bin/python
# This file is part of tcollector.
# Copyright (C) 2013  The tcollector Authors.
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or (at your
# option) any later version.  This program is distributed in the hope that it
# will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty
# of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Lesser
# General Public License for more details.  You should have received a copy
# of the GNU Lesser General Public License along with this program.  If not,
# see <http://www.gnu.org/licenses/>.

import os
import sys
import time
from stat import S_ISDIR, S_ISREG, ST_MODE
import unittest
import subprocess
import json
import threading
try:
    import flask
except ImportError:
    flask = None
import tcollector


class ReaderThreadTests(unittest.TestCase):

    def test_bool_false_converted_int(self):
        """Values that aren't ints/floats aren't sent to OpenTSDB.

        This can happen if a specific collector is buggy.
        """
        thread = tcollector.ReaderThread(1, 10, True)  # pylint:disable=no-member
        collector = tcollector.Collector("c", 1, "c")  # pylint:disable=no-member
        line = "mymetric 123 False a=b"
        thread.process_line(collector, line)
        self.assertEqual(thread.readerq.qsize(), 1, line)
        self.assertEqual(thread.readerq.get(), line)
        self.assertEqual(collector.lines_received, 1)
        self.assertEqual(collector.lines_invalid, 0)

    def test_bool_true_converted_int(self):
        """Values that aren't ints/floats aren't sent to OpenTSDB.

        This can happen if a specific collector is buggy.
        """
        thread = tcollector.ReaderThread(1, 10, True)  # pylint:disable=no-member
        collector = tcollector.Collector("c", 1, "c")  # pylint:disable=no-member
        line = "mymetric 123 True a=b"
        thread.process_line(collector, line)
        self.assertEqual(thread.readerq.qsize(), 1, line)
        self.assertEqual(thread.readerq.get(), line)
        self.assertEqual(collector.lines_received, 1)
        self.assertEqual(collector.lines_invalid, 0)

    def test_bad_float(self):
        """Values that aren't ints/floats aren't sent to OpenTSDB.

        This can happen if a specific collector is buggy.
        """
        thread = tcollector.ReaderThread(1, 10, True)  # pylint:disable=no-member
        collector = tcollector.Collector("c", 1, "c")  # pylint:disable=no-member
        for line in ["xxx", "mymetric 123 Value a=b"]:
            thread.process_line(collector, line)
        self.assertEqual(thread.readerq.qsize(), 0)
        self.assertEqual(collector.lines_received, 2)
        self.assertEqual(collector.lines_invalid, 2)

    def test_ok_lines(self):
        """Good lines are passed on to OpenTSDB."""
        thread = tcollector.ReaderThread(1, 10, True)  # pylint:disable=no-member
        collector = tcollector.Collector("c", 1, "c")  # pylint:disable=no-member
        for line in ["mymetric 123.24 12 a=b",
                     "mymetric 124 12.7 a=b",
                     "mymetric 125 12.7"]:
            thread.process_line(collector, line)
            self.assertEqual(thread.readerq.qsize(), 1, line)
            self.assertEqual(thread.readerq.get(), line)
        self.assertEqual(collector.lines_received, 3)
        self.assertEqual(collector.lines_invalid, 0)


class CollectorsTests(unittest.TestCase):

    def test_collectorsAccessRights(self):
        """Test of collectors access rights, permissions should be 0100755."""

        def check_access_rights(top):
            for file in os.listdir(top):
                pathname = os.path.join(top, file)
                mode = os.stat(pathname).st_mode

                if S_ISDIR(mode):
                    # directory, recurse into it
                    check_access_rights(pathname)
                elif S_ISREG(mode):
                    # file, skip .gitkeep files that keep empty dirs in git
                    if file == '.gitkeep':
                        continue

                    # file, check permissions
                    permissions = oct(os.stat(pathname)[ST_MODE])
                    self.assertEqual("0o100755", permissions, f'file: {pathname}')
                else:
                    # unknown file type
                    pass

        collectors_path = os.path.dirname(os.path.abspath(__file__)) + \
            "/collectors/available"
        check_access_rights(collectors_path)

    def test_json(self):
        """A collector can be serialized to JSON."""
        collector = tcollector.Collector("myname", 17, "myname.py", mtime=23, lastspawn=15)  # pylint:disable=no-member
        collector.nextkill += 8
        collector.killstate += 2
        collector.lines_sent += 10
        collector.lines_received += 65
        collector.lines_invalid += 7
        self.assertEqual(collector.to_json(),
                         {"name": "myname",
                          "mtime": 23,
                          "lastspawn": 15,
                          "killstate": 2,
                          "nextkill": 8,
                          "lines_sent": 10,
                          "lines_received": 65,
                          "lines_invalid": 7,
                          "last_datapoint": collector.last_datapoint,
                          "dead": False})


class StatusServerTests(unittest.TestCase):
    """Tests for StatusServer."""

    def test_endtoend(self):
        """We can get JSON status of collectors from StatusServer."""
        collectors = {
            "a": tcollector.Collector("mycollector", 5, "a.py"),  # pylint:disable=no-member
            "b": tcollector.Collector("second", 3, "b.py"),  # pylint:disable=no-member
        }
        server = tcollector.StatusServer("127.0.0.1", 32025, collectors)  # pylint:disable=no-member
        # runs in background until test suite exits :( but it works.
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        with tcollector.urlopen("http://127.0.0.1:32025") as resource:
            result = resource.read()
        self.assertEqual(json.loads(result), [c.to_json() for c in collectors.values()])


@unittest.skipUnless(flask, "Flask not installed")
class SenderThreadHTTPTests(unittest.TestCase):
    """Tests for HTTP sending."""

    def run_fake_opentsdb(self, response_code):
        env = os.environ.copy()
        env["FLASK_APP"] = "fake_opentsdb.py"
        env["FAKE_OPENTSDB_RESPONSE"] = str(response_code)
        flask = subprocess.Popen(["flask", "run", "--port", "4242"], env=env)
        time.sleep(1)  # wait for it to start
        self.addCleanup(flask.terminate)

    def send_query_with_response_code(self, response_code):
        """
        Send a HTTP query using SenderThread, with server that returns given
        response code.
        """
        self.run_fake_opentsdb(response_code)
        reader = tcollector.ReaderThread(1, 10, True)  # pylint:disable=no-member
        sender = tcollector.SenderThread(  # pylint:disable=no-member
            reader, False, [("localhost", 4242)], False, {},
            http=True, http_api_path="api/put"
        )
        sender.sendq.append("mymetric 123 12 a=b")
        sender.send_data()
        return sender

    def test_normal(self):
        """If response is OK, sendq is cleared."""
        sender = self.send_query_with_response_code(204)
        self.assertEqual(len(sender.sendq), 0)

    def test_error(self):
        """
        If response is unexpected, e.g. 500 error, sendq is not cleared so we
        can retry.
        """
        sender = self.send_query_with_response_code(500)
        self.assertEqual(len(sender.sendq), 1)

    def test_bad_messages(self):
        """
        If response is 400, sendq is cleared since there's no point retrying
        bad messages.
        """
        sender = self.send_query_with_response_code(400)
        self.assertEqual(len(sender.sendq), 0)


class NamespacePrefixTests(unittest.TestCase):
    """Tests for metric namespace prefix."""

    def test_prefix_added(self):
        """Namespace prefix gets added to metrics as they are read."""
        thread = tcollector.ReaderThread(1, 10, True, "my.namespace.")  # pylint:disable=no-member
        collector = tcollector.Collector("c", 1, "c")  # pylint:disable=no-member
        line = "mymetric 123 12 a=b"
        thread.process_line(collector, line)
        self.assertEqual(thread.readerq.get(), "my.namespace." + line)
        self.assertEqual(collector.lines_received, 1)
        self.assertEqual(collector.lines_invalid, 0)


class TSDBlacklistingTests(unittest.TestCase):
    """
    Tests of TSD blacklisting logic
    https://github.com/OpenTSDB/tcollector/commit/c191d0d0889860db2ea231cad02e398843031a74
    """

    def setUp(self):
        # Stub out the randomness
        self.random_shuffle = tcollector.random.shuffle  # pylint: disable=maybe-no-member
        tcollector.random.shuffle = lambda x: x  # pylint: disable=maybe-no-member

    def tearDown(self):
        tcollector.random.shuffle = self.random_shuffle  # pylint: disable=maybe-no-member

    def mkSenderThread(self, tsds):
        return tcollector.SenderThread(None, True, tsds, False, {}, reconnectinterval=5)  # pylint: disable=maybe-no-member

    def test_blacklistOneConnection(self):
        tsd = ("localhost", 4242)
        sender = self.mkSenderThread([tsd])
        sender.pick_connection()
        self.assertEqual(tsd, (sender.host, sender.port))
        sender.blacklist_connection()
        sender.pick_connection()
        self.assertEqual(tsd, (sender.host, sender.port))

    def test_blacklistTwoConnections(self):
        tsd1 = ("localhost", 4242)
        tsd2 = ("localhost", 4243)
        sender = self.mkSenderThread([tsd1, tsd2])
        sender.pick_connection()
        self.assertEqual(tsd1, (sender.host, sender.port))
        sender.blacklist_connection()
        sender.pick_connection()
        self.assertEqual(tsd2, (sender.host, sender.port))
        sender.blacklist_connection()
        sender.pick_connection()
        self.assertEqual(tsd1, (sender.host, sender.port))

    def test_doublePickOneConnection(self):
        tsd = ("localhost", 4242)
        sender = self.mkSenderThread([tsd])
        sender.pick_connection()
        self.assertEqual(tsd, (sender.host, sender.port))
        sender.pick_connection()
        self.assertEqual(tsd, (sender.host, sender.port))

    def test_doublePickTwoConnections(self):
        tsd1 = ("localhost", 4242)
        tsd2 = ("localhost", 4243)
        sender = self.mkSenderThread([tsd1, tsd2])
        sender.pick_connection()
        self.assertEqual(tsd1, (sender.host, sender.port))
        sender.pick_connection()
        self.assertEqual(tsd2, (sender.host, sender.port))
        sender.pick_connection()
        self.assertEqual(tsd1, (sender.host, sender.port))


if __name__ == '__main__':
    import logging
    logging.basicConfig()
    cdir = os.path.join(os.path.dirname(os.path.realpath(sys.argv[0])),
                        'collectors')
    tcollector.setup_python_path(cdir)  # pylint: disable=maybe-no-member
    tcollector.populate_collectors(cdir)  # pylint: disable=maybe-no-member

    unittest.main(verbosity=2)
