"""Tests for dsi/common/host.py"""


import os
import shutil
import unittest

import mock
from mock import patch, MagicMock, call, ANY
from nose.tools import nottest

from dsi.common import whereami
from dsi.common.config import ConfigDict
from dsi.common.local_host import LocalHost
from dsi.common.remote_host import RemoteHost
from test_lib.fixture_files import FixtureFiles

FIXTURE_FILES = FixtureFiles()


class HostTestCase(unittest.TestCase):
    """ Unit Test for Host library """

    def _delete_fixtures(self):
        """ delete fixture path and set filename attribute """
        local_host_path = os.path.join(FIXTURE_FILES.fixture_file_path(), "fixtures")
        self.filename = os.path.join(local_host_path, "file")
        shutil.rmtree(os.path.dirname(self.filename), ignore_errors=True)

    def setUp(self):
        """ Init a ConfigDict object and load the configuration files from docs/config-specs/ """
        self.old_dir = os.getcwd()  # Save the old path to restore
        self.config = ConfigDict("mongodb_setup", whereami.dsi_repo_path("docs", "config-specs"))
        self.config.load()
        self.parent_dir = os.path.join(os.path.expanduser("~"), "checkout_repos_test")

        self._delete_fixtures()

    def tearDown(self):
        """ Restore working directory """
        os.chdir(self.old_dir)

        self._delete_fixtures()

    def test_kill_remote_procs(self):
        """ Test kill_remote_procs """

        local = LocalHost()
        local.run = MagicMock(name="run")
        local.run.return_value = False
        self.assertTrue(local.kill_remote_procs("mongo"))

        calls = [call(["pkill", "-9", "mongo"], quiet=True), call(["pgrep", "mongo"], quiet=True)]

        local.run.assert_has_calls(calls)

        with patch("dsi.common.host_utils.create_timer") as mock_create_watchdog:

            local.run = MagicMock(name="run")
            local.run.return_value = False
            local.kill_remote_procs("mongo", max_time_ms=None)
            mock_create_watchdog.assert_called_once_with(ANY, None)

        with patch("dsi.common.host_utils.create_timer") as mock_create_watchdog:

            local.run = MagicMock(name="run")
            local.run.return_value = False
            local.kill_remote_procs("mongo", max_time_ms=0, delay_ms=99)
            mock_create_watchdog.assert_called_once_with(ANY, 99)

        with patch("dsi.common.host_utils.create_timer") as mock_create_watchdog:
            local = LocalHost()
            local.run = MagicMock(name="run")
            local.run.return_value = True

            mock_is_timed_out = MagicMock(name="is_timed_out")
            mock_create_watchdog.return_value = mock_is_timed_out
            mock_is_timed_out.side_effect = [False, True]
            self.assertFalse(local.kill_remote_procs("mongo", delay_ms=1))

        local = LocalHost()
        local.run = MagicMock(name="run")
        local.run.side_effect = [False, True, False, False]
        self.assertTrue(local.kill_remote_procs("mongo", signal_number=15, delay_ms=1))

        calls = [
            call(["pkill", "-15", "mongo"], quiet=True),
            call(["pgrep", "mongo"], quiet=True),
            call(["pkill", "-15", "mongo"], quiet=True),
            call(["pgrep", "mongo"], quiet=True),
        ]

        local.run.assert_has_calls(calls)
        # mock_sleep.assert_not_called()

    def test_kill_mongo_procs(self):
        """ Test kill_mongo_procs """
        local = LocalHost()
        local.kill_remote_procs = MagicMock(name="kill_remote_procs")
        local.kill_remote_procs.return_value = True
        self.assertTrue(local.kill_mongo_procs())
        local.kill_remote_procs.assert_called_once_with("mongo", 9, max_time_ms=30000)

    @patch("paramiko.SSHClient")
    def test_alias(self, mock_ssh):
        """ Test alias """

        remote = RemoteHost("host", "user", "pem_file")
        self.assertEqual(remote.alias, "host")

        remote.alias = ""
        self.assertEqual(remote.alias, "host")

        remote.alias = None
        self.assertEqual(remote.alias, "host")

        remote.alias = "alias"
        self.assertEqual(remote.alias, "alias")

    @patch("paramiko.SSHClient")
    def test_run(self, mock_ssh):
        """Test Host.run on RemoteHost"""
        subject = RemoteHost("test_host", "test_user", "test_pem_file")

        # test string command
        subject.exec_command = MagicMock(name="exec_command")
        subject.exec_command.return_value = 0
        self.assertTrue(subject.run("cowsay Hello World", quiet=True))
        subject.exec_command.assert_called_once_with("cowsay Hello World", quiet=True)

        # test string command
        subject.exec_command = MagicMock(name="exec_command")
        subject.exec_command.return_value = 0
        self.assertTrue(subject.run("cowsay Hello World"))
        subject.exec_command.assert_called_once_with("cowsay Hello World", quiet=False)

        # Test fail
        subject.exec_command = MagicMock(name="exec_command")
        subject.exec_command.return_value = 1
        self.assertFalse(subject.run("cowsay Hello World"))
        subject.exec_command.assert_called_once_with("cowsay Hello World", quiet=False)

        # test list command success
        subject.exec_command = MagicMock(name="exec_command")
        subject.exec_command.return_value = 0
        self.assertTrue(subject.run([["cowsay", "Hello", "World"], ["cowsay", "moo"]]))
        subject.exec_command.assert_any_call(["cowsay", "Hello", "World"], quiet=False)
        subject.exec_command.assert_any_call(["cowsay", "moo"], quiet=False)

        # test list command failure
        subject.exec_command = MagicMock(name="exec_command")
        subject.exec_command.side_effect = [0, 1, 0]
        self.assertFalse(
            subject.run([["cowsay", "Hello", "World"], ["cowsay", "moo"], ["cowsay", "boo"]])
        )
        calls = [
            mock.call(["cowsay", "Hello", "World"], quiet=False),
            mock.call(["cowsay", "moo"], quiet=False),
        ]
        subject.exec_command.assert_has_calls(calls)

        # test list command failure
        subject.exec_command = MagicMock(name="exec_command")
        subject.exec_command.return_value = 0
        self.assertTrue(subject.run(["cowsay Hello World", "cowsay moo"]))
        subject.exec_command.assert_called_once_with(
            ["cowsay Hello World", "cowsay moo"], quiet=False
        )

    @nottest
    def helper_test_checkout_repos(self, source, target, commands, branch=None, verbose=True):
        """ test_checkout_repos common test code """
        local = LocalHost()

        # Test with non-existing target
        self.assertFalse(os.path.exists(target))
        with patch("dsi.common.host.mkdir_p") as mock_mkdir_p, patch(
            "dsi.common.local_host.LocalHost.exec_command"
        ) as mock_exec_command:
            local.checkout_repos(source, target, verbose=verbose, branch=branch)
            mock_mkdir_p.assert_called_with(self.parent_dir)
            if len(commands) == 1:
                mock_exec_command.assert_called_once()
                mock_exec_command.assert_called_with(commands[0])
            else:
                for command in commands:
                    mock_exec_command.assert_any_call(command)

    def test_checkout_repos(self):
        """
        Test Host.checkout_repos command
        """
        # Only testing on LocalHost since `checkout_repos` is implemented in the base class and not
        # overidden
        local = LocalHost()

        # Test with existing target that is not a git repository
        source = "git@github.com:mongodb/mongo.git"
        target = os.path.expanduser("~")
        command = ["cd", target, "&&", "git", "status"]
        with patch("dsi.common.host.mkdir_p") as mock_mkdir_p, patch(
            "dsi.common.local_host.LocalHost.exec_command"
        ) as mock_exec_command:
            self.assertRaises(UserWarning, local.checkout_repos, source, target)
            mock_mkdir_p.assert_not_called()
            mock_exec_command.assert_called_once()
            mock_exec_command.assert_called_with(command)

    def test_checkout_repos_non_existing_target(self):

        # # Test with non-existing target
        source = "https://github.com/mongodb/stitch-js-sdk.git"
        target = os.path.join(self.parent_dir, "bin.stitch-js-sdk")
        commands = [["git", "clone", "", source, target]]
        self.helper_test_checkout_repos(source, target, commands, verbose=True)

        commands = [["git", "clone", "--quiet", source, target]]
        self.helper_test_checkout_repos(source, target, commands, verbose=None)

    def test_checkout_repos_branch(self):

        # Test with specified branch
        source = "https://github.com/mongodb/stitch-js-sdk.git"
        target = os.path.join(self.parent_dir, "bin.stitch-js-sdk")
        branch = "2.x.x"
        commands = [
            ["git", "clone", "--quiet", source, target],
            ["cd", target, "&&", "git", "checkout", "--quiet", branch],
        ]
        self.helper_test_checkout_repos(source, target, commands, branch=branch, verbose=None)

    def test_checkout_repos_existing_target(self):

        # Test with existing target that is a git repository
        local = LocalHost()

        source = "https://github.com/mongodb/stitch-js-sdk.git"
        target = os.path.join(self.parent_dir, "stitch-js-sdk")
        command = ["cd", target, "&&", "git", "status"]
        with patch("dsi.common.host.os.path.isdir") as mock_isdir, patch(
            "dsi.common.host.mkdir_p"
        ) as mock_mkdir_p, patch(
            "dsi.common.local_host.LocalHost.exec_command"
        ) as mock_exec_command:
            mock_isdir.return_value = True
            mock_exec_command.return_value = 0
            local.checkout_repos(source, target)
            mock_mkdir_p.assert_not_called()
            mock_exec_command.assert_called_once()
            mock_exec_command.assert_called_with(command)


if __name__ == "__main__":
    unittest.main()
