"""Tests for dsi/common/command_runner.py"""


import os
import shutil
import unittest

import mock
from mock import patch, Mock

from dsi.common import command_runner
from dsi.common import host_utils
from dsi.common import whereami
from dsi.common.command_runner import (
    EXCEPTION_BEHAVIOR,
    run_upon_error,
    run_pre_post_commands,
    prepare_reports_dir,
)
from dsi.common.config import ConfigDict
from dsi.common.models.host_info import HostInfo
from dsi.common.utils import mkdir_p, touch
from test_lib.fixture_files import FixtureFiles

FIXTURE_FILES = FixtureFiles()


class CommandRunnerTestCase(unittest.TestCase):
    """ Unit Tests for Host Utils library """

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
        self.reports_container = os.path.join(FIXTURE_FILES.fixture_file_path(), "container")
        self.reports_path = os.path.join(self.reports_container, "reports_tests")

        mkdir_p(self.reports_path)

    def tearDown(self):
        """ Restore working directory """
        shutil.rmtree(self.reports_container)

        os.chdir(self.old_dir)

        self._delete_fixtures()

    @patch("dsi.common.command_runner._run_host_command_map")
    def test_make_host_runner_str(self, mock_run_host_command_map):
        """ Test run RemoteHost.make_host_runner with str"""
        with patch("dsi.common.host_factory.make_host") as mock_make_host:
            mock_target_host = Mock()
            mock_make_host.return_value = mock_target_host

            dummy_host_info = HostInfo("host_info")

            command_runner.make_host_runner(dummy_host_info, "command", "test_id")
            mock_make_host.assert_called_once_with(dummy_host_info, None, None)
            mock_target_host.run.assert_called_once_with("command")
            mock_target_host.close.assert_called_once()

    @patch("dsi.common.command_runner._run_host_command_map")
    def test_make_host_runner_map(self, mock_run_host_command_map):
        """ Test run Remotecommand_runner.make_host_runner with map"""

        with patch("dsi.common.host_factory.make_host") as mock_make_host:
            command = {}
            mock_target_host = Mock()
            mock_make_host.return_value = mock_target_host

            dummy_host_info = HostInfo("host_name")

            command_runner.make_host_runner(dummy_host_info, command, "test_id")

            mock_make_host.assert_called_once_with(dummy_host_info, None, None)

            mock_run_host_command_map.assert_called_once_with(mock_target_host, command, "test_id")
            mock_target_host.close.assert_called_once()

    def test_run_host_commands(self):
        """Test 2-commands common.command_runner.run_host_commands invocation"""
        with patch("dsi.common.host_factory.RemoteSSHHost") as mongod:
            commands = [
                {"on_workload_client": {"upload_files": [{"source": "src1", "target": "dest1"}]}},
                {"on_workload_client": {"upload_files": [{"source": "src2", "target": "dest2"}]}},
            ]
            command_runner.run_host_commands(commands, self.config, "test_id")
            self.assertEqual(mongod.call_count, 2)

    def test_run_host_command_map(self):
        """ Test run command map not known """

        with self.assertRaises(UserWarning):
            with patch("dsi.common.remote_host.RemoteHost") as mongod:
                command = {"garbage": {"remote_path": "mongos.log"}}
                command_runner._run_host_command_map(mongod, command, "test_id")

    def __run_host_command_map_ex(self, command, run_return_value=False, exec_return_value=None):
        with patch("dsi.common.remote_host.RemoteHost") as mongod:
            if run_return_value is not None:
                mongod.run.return_value = run_return_value
            else:
                mongod.exec_mongo_command.return_value = exec_return_value
            command_runner._run_host_command_map(mongod, command, "test_id")

    def test__exec_ex(self):
        """ Test run command map excpetion """

        # test upload_files
        with self.assertRaisesRegex(host_utils.HostException, r"^\(1, .*cowsay moo"):
            command = {"exec": "cowsay moo"}
            self.__run_host_command_map_ex(command)

    def test__exec_mongo_shell_ex(self):
        """ Test run command map excpetion """

        with self.assertRaisesRegex(host_utils.HostException, r"^\(1, .*this is a script"):
            command = {
                "exec_mongo_shell": {
                    "script": "this is a script",
                    "connection_string": "connection string",
                }
            }
            self.__run_host_command_map_ex(command, run_return_value=None, exec_return_value=1)

    def test_upload_repo_files(self):
        """ Test run command map upload_repo_files """
        root = whereami.dsi_repo_path() + os.sep

        # test upload_repo_files
        with patch("dsi.common.remote_host.RemoteHost") as mongod:
            command = {"upload_repo_files": [{"target": "remote_path", "source": "mongos.log"}]}
            command_runner._run_host_command_map(mongod, command, "test_id")
            mongod.upload_file.assert_called_once_with(root + "mongos.log", "remote_path")

        with patch("dsi.common.remote_host.RemoteHost") as mongod:
            command = {
                "upload_repo_files": [
                    {"target": "remote_path", "source": "mongos.log"},
                    {"target": "to", "source": "from"},
                ]
            }
            command_runner._run_host_command_map(mongod, command, "test_id")
            calls = [mock.call(root + "mongos.log", "remote_path"), mock.call(root + "from", "to")]
            mongod.upload_file.assert_has_calls(calls, any_order=True)

    def test_upload_files(self):
        """ Test run command map upload_files """

        # test upload_files
        with patch("dsi.common.remote_ssh_host.RemoteSSHHost") as mongod:
            command = {"upload_files": [{"target": "remote_path", "source": "mongos.log"}]}
            command_runner._run_host_command_map(mongod, command, "test_id")
            mongod.upload_file.assert_called_once_with("mongos.log", "remote_path")

        with patch("dsi.common.remote_ssh_host.RemoteSSHHost") as mongod:
            command = {
                "upload_files": [
                    {"source": "mongos.log", "target": "remote_path"},
                    {"source": "to", "target": "from"},
                ]
            }
            command_runner._run_host_command_map(mongod, command, "test_id")
            calls = [mock.call("mongos.log", "remote_path"), mock.call("to", "from")]
            mongod.upload_file.assert_has_calls(calls, any_order=True)

    def test_retrieve_files(self):
        """ Test run command map retrieve_files """

        # retrieve_files tests
        with patch("dsi.common.remote_host.RemoteHost") as mongod:
            mock_retrieve_file = Mock()
            mongod.retrieve_path = mock_retrieve_file

            command = {"retrieve_files": [{"source": "remote_path", "target": "mongos.log"}]}
            mongod.alias = "host"
            command_runner._run_host_command_map(mongod, command, "test_id")
            mock_retrieve_file.assert_any_call("remote_path", "reports/test_id/host/mongos.log")

        # retrieve_files tests
        with patch("dsi.common.remote_host.RemoteHost") as mongod:
            mock_retrieve_file = Mock()
            mongod.retrieve_path = mock_retrieve_file

            command = {"retrieve_files": [{"source": "remote_path", "target": "mongos.log"}]}
            mongod.alias = "host"
            command_runner._run_host_command_map(mongod, command, "test_id")
            mock_retrieve_file.assert_any_call("remote_path", "reports/test_id/host/mongos.log")

        with patch("dsi.common.remote_host.RemoteHost") as mongod:
            mock_retrieve_file = Mock()
            mongod.retrieve_path = mock_retrieve_file

            command = {"retrieve_files": [{"source": "remote_path", "target": "local_path"}]}
            mongod.alias = "host"
            command_runner._run_host_command_map(mongod, command, "test_id")
            mock_retrieve_file.assert_any_call("remote_path", "reports/test_id/host/local_path")

        with patch("dsi.common.remote_host.RemoteHost") as mongod:
            mock_retrieve_file = Mock()
            mongod.retrieve_path = mock_retrieve_file

            mongod.alias = "mongod.0"
            command_runner._run_host_command_map(mongod, command, "test_id")
            mock_retrieve_file.assert_any_call("remote_path", "reports/test_id/mongod.0/local_path")

        with patch("dsi.common.remote_host.RemoteHost") as mongod:
            mock_retrieve_file = Mock()
            mongod.retrieve_path = mock_retrieve_file

            command = {"retrieve_files": [{"source": "remote_path", "target": "./local_path"}]}
            mongod.alias = "mongos.0"
            command_runner._run_host_command_map(mongod, command, "test_id")
            mock_retrieve_file.assert_any_call("remote_path", "reports/test_id/mongos.0/local_path")

    def test_exec(self):
        """ Test run command map exec """

        # test exec
        with patch("dsi.common.remote_host.RemoteHost") as mongod:
            command = {"exec": "this is a command"}
            mongod.run.return_value = True
            command_runner._run_host_command_map(mongod, command, "test_id")
            mongod.run.assert_called_once_with("this is a command")

    def test_exec_mongo_shell(self):
        """ Test run command map exec mongo shell """

        # test exec_mongo_shell
        with patch("dsi.common.remote_host.RemoteHost") as mongod:
            command = {
                "exec_mongo_shell": {
                    "script": "this is a script",
                    "connection_string": "connection string",
                }
            }
            mongod.exec_mongo_command.return_value = 0
            command_runner._run_host_command_map(mongod, command, "test_id")
            mongod.exec_mongo_command.assert_called_once_with(
                "this is a script", connection_string="connection string"
            )

        with patch("dsi.common.remote_host.RemoteHost") as mongod:
            command = {"exec_mongo_shell": {"script": "this is a script"}}
            mongod.exec_mongo_command.return_value = 0
            command_runner._run_host_command_map(mongod, command, "test_id")
            mongod.exec_mongo_command.assert_called_once_with(
                "this is a script", connection_string=""
            )

    def test_run_upon_error(self):
        """ test run_upon_error """

        @mock.patch("dsi.common.command_runner.prepare_reports_dir")
        @mock.patch("dsi.common.command_runner.run_pre_post_commands")
        def _test_run_upon_error(behave, mock_run_pre_post_commands, mock_prepare_reports_dir):

            config = {"mongodb_setup": "setup"}
            if behave:
                run_upon_error("mongodb_setup", [], config)
                expected = EXCEPTION_BEHAVIOR.EXIT
            else:
                run_upon_error("mongodb_setup", [], config, EXCEPTION_BEHAVIOR.CONTINUE)
                expected = EXCEPTION_BEHAVIOR.CONTINUE

            mock_prepare_reports_dir.assert_called_once()
            mock_run_pre_post_commands.assert_called_with(
                "upon_error", [], config, expected, "upon_error/mongodb_setup"
            )

        _test_run_upon_error(True)
        _test_run_upon_error(False)

    @patch("dsi.common.command_runner.run_host_command")
    def test_run_pre_post(self, mock_run_host_command):
        """Test test_control.run_pre_post_commands()"""
        command_dicts = [self.config["test_control"], self.config["mongodb_setup"]]
        run_pre_post_commands("post_test", command_dicts, self.config, EXCEPTION_BEHAVIOR.EXIT)

        # expected_args = ['on_workload_client', 'on_all_servers', 'on_mongod', 'on_configsvr']
        expected_args = ["on_mongod", "on_all_hosts", "on_all_servers", "on_mongod", "on_configsvr"]
        observed_args = []
        for args in mock_run_host_command.call_args_list:
            observed_args.append(args[0][0])
        self.assertEqual(observed_args, expected_args)

    def test_prepare_reports_dir(self):
        """Test test_control.run_test where the exec command returns non-zero"""

        previous_directory = os.getcwd()
        reports_dir = os.path.join(self.reports_path, "reports")
        reports_tarball = os.path.join(self.reports_container, "reports.tgz")

        def _test_prepare_reports_dir():
            try:
                os.chdir(self.reports_path)
                prepare_reports_dir(reports_dir=reports_dir)
            finally:
                os.chdir(previous_directory)

            self.assertFalse(os.path.exists(reports_tarball))
            self.assertTrue(os.path.exists(reports_dir))
            self.assertTrue(os.path.islink(reports_dir))

        _test_prepare_reports_dir()

        touch(reports_tarball)
        _test_prepare_reports_dir()

        os.remove(reports_dir)
        mkdir_p(reports_dir)
        self.assertRaises(OSError, _test_prepare_reports_dir)


if __name__ == "__main__":
    unittest.main()
