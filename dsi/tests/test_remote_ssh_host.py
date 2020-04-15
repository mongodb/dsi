import socket
import time
import unittest
from io import StringIO

import mock
import paramiko
from mock import patch, ANY, MagicMock, Mock

from dsi.common import host_utils
from dsi.common import remote_host
from dsi.common import remote_ssh_host
from dsi.common.mongodb_setup_helpers import MongoDBAuthSettings
from test_lib.comparator_utils import ANY_IN_STRING


def sleepy_streamer(sleep_time_sec, outval):
    """
    :param sleep_time_sec: how long in seconds to sleep
    :param outval: forced return value
    :return: a function that sleeps for `sleep_time_sec` seconds and returns `outval`
    """

    def out(_1, _2):
        time.sleep(sleep_time_sec)
        return outval

    return out


class RemoteSSHHostTestCase(unittest.TestCase):
    def test_remote_exec_command_default_streams(self):
        """ test remote exec uses the correct default info and err streams """
        self.helper_remote_exec_command_streams()

    def test_exec_mongo_warn(self):
        """ test remote exec uses the correct custom info and err streams """
        self.helper_remote_exec_command_streams(out=StringIO(), err=StringIO())

    @patch("paramiko.SSHClient")
    def helper_remote_exec_command(
        self,
        mock_ssh,
        command="cowsay Hello World",
        expected="cowsay Hello World",
        return_value=0,
        exit_status=0,
        out=StringIO(),
        err=StringIO(),
    ):
        """ test common code with """
        remote = remote_ssh_host.RemoteSSHHost("test_host", "test_user", "test_pem_file")

        ssh_instance = mock_ssh.return_value
        stdin = Mock(name="stdin")

        # magic mock for iterable support
        stdout = mock.MagicMock(name="stdout")
        stdout.__iter__.return_value = ""

        stderr = mock.MagicMock(name="stderr")
        stdout.__iter__.return_value = ""
        ssh_instance.exec_command.return_value = [stdin, stdout, stderr]

        remote._perform_exec = mock.MagicMock(name="_perform_exec")
        remote._perform_exec.return_value = exit_status

        self.assertEqual(remote.exec_command(command, out, err), return_value)
        ssh_instance.exec_command.assert_called_once_with(expected, get_pty=False)
        stdin.channel.shutdown_write.assert_called_once()

        stdin.close.assert_called()
        stdout.close.assert_called()
        stderr.close.assert_called()

    def helper_remote_exec_command_ex(self, params, exception=ValueError):
        """Test RemoteHost.exec_command"""
        # Exceptions
        with patch("paramiko.SSHClient"):
            remote = remote_ssh_host.RemoteSSHHost("test_host", "test_user", "test_pem_file")
            self.assertRaises(exception, remote.exec_command, params)

    def test_remote_exec_command_ex_str(self):
        """Test RemoteHost.exec_command exceptions '' param """
        self.helper_remote_exec_command_ex("")

    def test_remote_exec_command_ex_array(self):
        """Test RemoteHost.exec_command exceptions [] param  """
        self.helper_remote_exec_command_ex(params=[])

    def test_remote_exec_command_ex_none(self):
        """Test RemoteHost.exec_command exceptions None  param  """
        self.helper_remote_exec_command_ex(params=None)

    def test_remote_exec_command_ex_zero(self):
        """Test RemoteHost.exec_command exceptions 0  param   """
        self.helper_remote_exec_command_ex(params=0)

    def test_remote_exec_command(self):
        """Test RemoteHost.exec_command"""
        self.helper_remote_exec_command()

    def test_remote_exec_command_no_warn(self):
        """Test RemoteHost.exec_command no warnings on success"""

        mock_logger = MagicMock(name="LOG")
        remote_ssh_host.LOG.warning = mock_logger
        self.helper_remote_exec_command(command=["cowsay", "Hello", "World"])
        mock_logger.assert_not_called()

    def test_remote_exec_command_warning_on_falure(self):
        """Test RemoteHost.exec_command warning on failure"""

        mock_logger = MagicMock(name="LOG")
        remote_ssh_host.LOG.warning = mock_logger
        self.helper_remote_exec_command(return_value=1, exit_status=1)

        mock_logger.assert_called_once_with(ANY_IN_STRING("with exit status"), ANY, ANY, ANY)

    @staticmethod
    def helper_remote_exec_command_streams(out=None, err=None):
        """Test RemoteHost.exec_command steam out """

        with patch("paramiko.SSHClient") as mock_ssh:
            # Test a command as list
            remote = remote_ssh_host.RemoteSSHHost("test_host", "test_user", "test_pem_file")

            ssh_instance = mock_ssh.return_value
            stdin = Mock(name="stdin")

            # magic mock for iterable support
            stdout = mock.MagicMock(name="stdout")
            stdout.__iter__.return_value = ["1", "2", "3", "", "3", "2", "1"]
            stdout.channel.recv_exit_status.return_value = [True, False]

            stderr = mock.MagicMock(name="stderr")
            stderr.__iter__.return_value = ["First", "Second", "Third"]

            ssh_instance.exec_command.return_value = [stdin, stdout, stderr]

            stdout.channel.exit_status_ready.return_value = True

            remote._perform_exec = mock.MagicMock(name="_perform_exec")
            remote._perform_exec.return_value = 0

            remote.exec_command(
                "command",
                out,
                err,
                max_time_ms="max_time_ms",
                no_output_timeout_ms="no_output_timeout_ms",
            )
            ssh_instance.exec_command.assert_called_once_with("command", get_pty=False)
            stdin.channel.shutdown_write.assert_called_once()
            stdin.close.assert_called()
            stdout.close.assert_called()
            stderr.close.assert_called()

            if out is None:
                expected_out = remote_ssh_host.INFO_ADAPTER
            else:
                expected_out = out

            if err is None:
                expected_err = remote_ssh_host.WARN_ADAPTER
            else:
                expected_err = err

            remote._perform_exec.assert_called_once_with(
                "command",
                expected_out,
                expected_err,
                stdout,
                stderr,
                "max_time_ms",
                "no_output_timeout_ms",
            )

    def helper_exec_mongo_command(
        self,
        connection_string="mongodb://test_connection_string",
        mongodb_auth_settings=None,
        expect_auth_command_line=True,
    ):
        """ Test run RemoteHost.exec_mongo_command """

        # We define an extra function for setting up the mocked values in order to make the
        # 'connection_string' and 'mongodb_auth_settings' parameters optional.
        @patch("dsi.common.remote_host.RemoteHost.exec_command")
        @patch("dsi.common.remote_host.RemoteHost.create_file")
        @patch("paramiko.SSHClient")
        def run_test(mock_ssh, mock_create_file, mock_exec_command):
            _ = mock_ssh

            mock_exec_command.return_value = 0
            test_file = "test_file"
            test_user = "test_user"
            test_pem_file = "test_pem_file"
            test_host = "test_host"
            test_script = "test_script"
            expected_argv = ["bin/mongo", "--quiet"]
            if mongodb_auth_settings is not None and expect_auth_command_line:
                expected_argv.extend(
                    ["-u", "username", "-p", "password", "--authenticationDatabase", "admin"]
                )
            expected_argv.extend([connection_string, test_file])
            remote = remote_host.RemoteHost(
                test_host, test_user, test_pem_file, mongodb_auth_settings
            )
            status_code = remote.exec_mongo_command(test_script, test_file, connection_string)
            self.assertEqual(0, status_code)
            mock_create_file.assert_called_with(test_file, test_script)
            mock_exec_command.assert_called_with(
                expected_argv, stdout=None, stderr=None, max_time_ms=None, quiet=False
            )

        run_test()

    def test_exec_mongo_command_no_auth(self):
        self.helper_exec_mongo_command()

    def test_exec_mongo_command_with_auth_settings(self):
        self.helper_exec_mongo_command(
            mongodb_auth_settings=MongoDBAuthSettings("username", "password")
        )

    def test_exec_mongo_command_with_auth_connection_string(self):
        self.helper_exec_mongo_command(
            connection_string="mongodb://username:password@test_connection_string"
        )

        self.assertRaisesRegex(
            ValueError,
            "Must specify both username and password",
            self.helper_exec_mongo_command,
            connection_string="mongodb://username@test_connection_string",
        )

    def test_exec_mongo_command_with_auth_settings_and_connection_string(self):
        self.helper_exec_mongo_command(
            connection_string="mongodb://username:password@test_connection_string",
            mongodb_auth_settings=MongoDBAuthSettings("username", "password"),
            expect_auth_command_line=False,
        )

        self.assertRaisesRegex(
            ValueError,
            "Username.*doesn't match",
            self.helper_exec_mongo_command,
            connection_string="mongodb://username:password@test_connection_string",
            mongodb_auth_settings=MongoDBAuthSettings("username2", "password"),
        )

        self.assertRaisesRegex(
            ValueError,
            "Password.*doesn't match",
            self.helper_exec_mongo_command,
            connection_string="mongodb://username:password@test_connection_string",
            mongodb_auth_settings=MongoDBAuthSettings("username", "password2"),
        )

    # normally wouldn't test internal method, but the collaboration with other
    # objects is complicated within host.exec_command and leads to the core logic
    # being hard to isolate on its own.
    def when_perform_exec(self, case):
        """
        :param case: contains given/then conditions for behavior of _perform_exec

        Example:

            'given': {
                # params given to _perform_exec
                'command': 'cowsay HellowWorld',
                'max_timeout_ms': 750,
                'no_output_timeout_ms': 20,
                # mock _stream behavior
                'ssh_interrupt_after_ms': 5,
                'with_output': False,
                # (was exist status ready, actual exit status)
                'and_exit_status': (True, 0),
            },
            'then': {
                # asserted output of _perform_exec
                'exit_status': 0,
                'did_timeout': False,
                'time_taken_seconds': ANY
            }
        """
        given = case["given"]
        then = case.get("then", None)

        def new_mock(name):
            return MagicMock(autospec=True, name=name)

        (stdout, stderr, ssh_stdout, ssh_stderr) = (
            new_mock("stdout"),
            new_mock("stderr"),
            new_mock("ssh_stdout"),
            new_mock("ssh_stderr"),
        )

        ssh_stdout.channel.exit_status_ready.return_value = given["and_exit_status"][0]
        ssh_stdout.channel.recv_exit_status.return_value = given["and_exit_status"][1]

        stream_before = host_utils.stream_lines
        with patch("paramiko.SSHClient", autospec=True):
            try:
                # monkey-patch here because @patch doesn't let us (easily) change
                # the actual behavior of the method, just set canned return values and
                # assert interactions. We actually want _stream() to sleep as well
                host_utils.stream_lines = sleepy_streamer(
                    float(given["ssh_interrupt_after_ms"]) / 1000, given["with_output"]
                )

                remote = remote_ssh_host.RemoteSSHHost("test_host", "test_user", "test_pem_file")
                exit_status = remote._perform_exec(
                    given["command"],
                    stdout,
                    stderr,
                    ssh_stdout,
                    ssh_stderr,
                    given["max_timeout_ms"],
                    given["no_output_timeout_ms"],
                )

                if then:
                    self.assertEqual(then, {"exit_status": exit_status})
            finally:
                host_utils.stream_lines = stream_before

    def test_perform_exec_no_timeout(self):
        """test_perform_exec_no_timeout"""
        self.when_perform_exec(
            {
                "given": {
                    "command": "cowsay Hello World",
                    "max_timeout_ms": 100,
                    "no_output_timeout_ms": 20,
                    "ssh_interrupt_after_ms": 5,
                    "with_output": False,
                    "and_exit_status": (True, 0),
                },
                "then": {"exit_status": 0},
            }
        )

    def test_perform_exec_no_output(self):
        """
        This one times out because of the
        False in and_exit_status[0].
        The ssh never finishes and doesn't produce
        output, so it's a timeout.
        """

        with self.assertRaisesRegex(host_utils.HostException, r"^No Output"):
            self.when_perform_exec(
                {
                    "given": {
                        "command": "cowsay Hello World",
                        "max_timeout_ms": 100,
                        "no_output_timeout_ms": 20,
                        "ssh_interrupt_after_ms": 5,
                        "with_output": False,
                        "and_exit_status": (False, 10),
                    }
                }
            )

    def test_perform_exec_max_timeout(self):
        """
        This one times out because of the
        False in and_exit_status[0].
        The ssh never finishes and doesn't produce
        output, so it's a timeout.
        """

        with self.assertRaisesRegex(
            host_utils.HostException, r"exceeded [0-9\.]+ allowable seconds on"
        ):
            self.when_perform_exec(
                {
                    "given": {
                        "command": "cowsay Hello World",
                        "max_timeout_ms": 200,
                        "no_output_timeout_ms": 1000000,
                        "ssh_interrupt_after_ms": 5,
                        "with_output": True,
                        "and_exit_status": (False, 10),
                    }
                }
            )

    def test_perform_exec_ready(self):
        """test_perform_exec_ready"""
        self.when_perform_exec(
            {
                "given": {
                    "command": "cowsay Hello World",
                    "max_timeout_ms": 100,
                    "no_output_timeout_ms": 20,
                    "ssh_interrupt_after_ms": 5,
                    "with_output": False,
                    "and_exit_status": (True, 2),
                },
                "then": {"exit_status": 2},
            }
        )

    def test_perform_exec_total_timeout_no_output(self):
        """test_perform_exec_total_timeout_no_output"""
        with self.assertRaisesRegex(host_utils.HostException, r"^No Output"):
            self.when_perform_exec(
                {
                    "given": {
                        "command": "cowsay Hello World",
                        "max_timeout_ms": 20,
                        "no_output_timeout_ms": 10,
                        "ssh_interrupt_after_ms": 5,
                        "with_output": False,
                        "and_exit_status": (False, 0),
                    }
                }
            )

    def test_perform_exec_immediate_fail(self):
        """test_perform_exec_total_timeout_no_output"""
        self.when_perform_exec(
            {
                "given": {
                    "command": "cowsay Hello World",
                    "max_timeout_ms": 20,
                    "no_output_timeout_ms": 10,
                    "ssh_interrupt_after_ms": 1,
                    "with_output": True,
                    "and_exit_status": (True, 127),
                },
                "then": {"exit_status": 127},
            }
        )

    def test_remote_host_ssh_ex(self):
        """Test RemoteHost constructor ssh exception handling"""
        self.assertRaises(SystemExit, self.helper_remote_host_ssh_ex, paramiko.SSHException())

    def test_remote_host_sock_ex(self):
        """Test RemoteHost constructor socket exception handling"""
        self.assertRaises(SystemExit, self.helper_remote_host_ssh_ex, socket.error())

    def test_remote_host_ex(self):
        """Test RemoteHost constructor exception handling"""
        self.assertRaises(Exception, self.helper_remote_host_ssh_ex)

    @staticmethod
    def helper_remote_host_ssh_ex(exception=Exception()):
        """Test RemoteHost constructor ssh exception handling"""
        with patch("paramiko.SSHClient") as mock_paramiko:
            mock_ssh = MagicMock(name="connection")
            mock_paramiko.return_value = mock_ssh

            mock_ssh.connect.side_effect = exception
            remote_ssh_host.RemoteSSHHost("test_host", "test_user", "test_pem_file")


if __name__ == "__main__":
    unittest.main()
