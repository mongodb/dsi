"""Tests for dsi/common/local_host.py"""


import os
import shutil
import unittest
from io import StringIO

from mock import MagicMock, ANY

from dsi.common import local_host
from dsi.common import utils
from dsi.common import whereami
from dsi.common.config import ConfigDict
from dsi.common.log import TeeStream
from test_lib.comparator_utils import ANY_IN_STRING
from test_lib.fixture_files import FixtureFiles

FIXTURE_FILES = FixtureFiles()


class LocalHostTestCase(unittest.TestCase):
    """ Unit Test for LocalHost library """

    def _delete_fixtures(self):
        """ delete fixture path and set filename attribute """
        local_host_path = FIXTURE_FILES.fixture_file_path("fixtures")
        self.filename = os.path.join(local_host_path, "file")
        shutil.rmtree(os.path.dirname(self.filename), ignore_errors=True)

    def setUp(self):
        """ Init a ConfigDict object and load the configuration files from docs/config-specs/ """
        self.config = ConfigDict("mongodb_setup", whereami.dsi_repo_path("docs", "config-specs"))
        self.config.load()
        self.parent_dir = os.path.join(os.path.expanduser("~"), "checkout_repos_test")

        self._delete_fixtures()

    def tearDown(self):
        """ Restore working directory """
        self._delete_fixtures()

    def test_local_host_exec_command(self):
        """ Test LocalHost.exec_command """

        local = local_host.LocalHost()
        utils.mkdir_p(os.path.dirname(self.filename))

        self.assertEqual(local.exec_command("exit 0"), 0)

        # test that the correct warning is issued
        mock_logger = MagicMock(name="LOG")
        local_host.LOG.warning = mock_logger
        self.assertEqual(local.exec_command("exit 1"), 1)
        mock_logger.assert_called_once_with(ANY_IN_STRING("Failed with exit status"), ANY, ANY, ANY)

        local.exec_command("touch {}".format(self.filename))
        self.assertTrue(os.path.isfile(self.filename))

        local.exec_command("touch {}".format(self.filename))
        self.assertTrue(os.path.isfile(self.filename))

        with open(self.filename, "w", encoding="utf-8") as the_file:
            the_file.write("Hello\n")
            the_file.write("World\n")
        out = StringIO()
        err = StringIO()
        local.exec_command("cat {}".format(self.filename), out, err)
        self.assertEqual(out.getvalue(), "Hello\nWorld\n")

        out = StringIO()
        err = StringIO()
        self.assertEqual(local.exec_command("cat {}; exit 1".format(self.filename), out, err), 1)
        self.assertEqual(out.getvalue(), "Hello\nWorld\n")
        self.assertEqual(err.getvalue(), "")

        out = StringIO()
        err = StringIO()
        local.exec_command("cat {} >&2; exit 1".format(self.filename), out, err)
        self.assertEqual(out.getvalue(), "")
        self.assertEqual(err.getvalue(), "Hello\nWorld\n")

        out = StringIO()
        err = StringIO()
        command = """cat {filename} && cat -n {filename} >&2; \
        exit 1""".format(
            filename=self.filename
        )
        local.exec_command(command, out, err)
        self.assertEqual(out.getvalue(), "Hello\nWorld\n")
        self.assertEqual(err.getvalue(), "     1\tHello\n     2\tWorld\n")

        out = StringIO()
        err = StringIO()
        command = "seq 10 -1 1 | xargs  -I % sh -c '{ echo %; sleep .1; }'; \
        echo 'blast off!'"

        local.exec_command(command, out, err)
        self.assertEqual(out.getvalue(), "10\n9\n8\n7\n6\n5\n4\n3\n2\n1\nblast off!\n")
        self.assertEqual(err.getvalue(), "")

        # test timeout and that the correct warning is issued
        out = StringIO()
        err = StringIO()
        command = "sleep 1"

        mock_logger = MagicMock(name="LOG")
        local_host.LOG.warning = mock_logger
        self.assertEqual(local.exec_command(command, out, err, max_time_ms=500), 1)
        mock_logger.assert_called_once_with(ANY_IN_STRING("Timeout after"), ANY, ANY, ANY, ANY)

    def test_local_host_tee(self):
        """ Test run command map retrieve_files """

        local = local_host.LocalHost()
        utils.mkdir_p(os.path.dirname(self.filename))

        expected = "10\n9\n8\n7\n6\n5\n4\n3\n2\n1\nblast off!\n"
        with open(self.filename, "w", encoding="utf-8") as the_file:
            out = StringIO()
            tee = TeeStream(the_file, out)
            err = StringIO()
            command = "seq 10 -1 1 | xargs  -I % sh -c '{ echo %; sleep .1; }'; \
        echo 'blast off!'"

            local.exec_command(command, tee, err)
            self.assertEqual(out.getvalue(), expected)
            self.assertEqual(err.getvalue(), "")

        with open(self.filename) as the_file:
            self.assertEqual(expected, "".join(the_file.readlines()))


if __name__ == "__main__":
    unittest.main()
