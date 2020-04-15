"""
RemoteHost implementation that uses SSH.
"""

import logging
from datetime import datetime

import paramiko
import six

from dsi.common import host_utils
from dsi.common import remote_host
from dsi.common.host_utils import LOG
from dsi.common.log import IOLogAdapter

LOG = logging.getLogger(__name__)
# This stream only log error or above messages
ERROR_ONLY = logging.getLogger("error_only")

INFO_ADAPTER = IOLogAdapter(LOG, logging.INFO)
WARN_ADAPTER = IOLogAdapter(LOG, logging.WARN)


# pylint: disable=too-few-public-methods
class RemoteSSHHost(remote_host.RemoteHost):
    """
    Represents a remote host that executes commands via SSH.
    """

    # pylint: disable=too-many-arguments
    # pylint: disable=too-many-locals
    def exec_command(
        self,
        argv,
        stdout=None,
        stderr=None,
        get_pty=False,
        max_time_ms=None,
        no_output_timeout_ms=None,
        quiet=False,
    ):
        """
        Execute the argv command on the remote host and log the output.

        For parameters/returns, see :method: `Host.exec_command`.
        :raises: HostException for timeouts and to wrap paramiko.SSHException
        """
        if quiet:
            logger = ERROR_ONLY
        else:
            logger = LOG

        # pylint: disable=too-many-branches
        if not argv or not isinstance(argv, (list, six.string_types)):
            raise ValueError("Argument must be a nonempty list or string.")

        if (
            max_time_ms is not None
            and no_output_timeout_ms is not None
            and no_output_timeout_ms > max_time_ms
        ):
            logger.warning(
                "Can't wait %s ms for output when max time is %s ms",
                no_output_timeout_ms,
                max_time_ms,
            )

        if stdout is None:
            stdout = INFO_ADAPTER
        if stderr is None:
            stderr = WARN_ADAPTER

        if isinstance(argv, list):
            command = " ".join(argv)
        else:
            command = argv

        logger.debug("[%s@%s]$ %s", self.user, self.hostname, command)

        # scoping
        ssh_stdout, ssh_stderr = None, None

        try:
            ssh_stdin, ssh_stdout, ssh_stderr = self._ssh.exec_command(command, get_pty=get_pty)
            ssh_stdin.channel.shutdown_write()
            ssh_stdin.close()

            exit_status = self._perform_exec(
                command, stdout, stderr, ssh_stdout, ssh_stderr, max_time_ms, no_output_timeout_ms
            )

        except paramiko.SSHException as e:
            raise host_utils.HostException(
                "failed to exec '{}' on {}@{}: '{}'".format(command, self.user, self.hostname, e)
            )
        finally:
            host_utils.close_safely(ssh_stdout)
            host_utils.close_safely(ssh_stderr)

        if exit_status != 0:
            logger.warning("%s '%s': Failed with exit status %s", self.alias, command, exit_status)
        return exit_status

    # pylint: disable=no-self-use
    # pylint: disable=too-many-arguments
    # pylint: disable=too-many-locals
    def _perform_exec(
        self, command, stdout, stderr, ssh_stdout, ssh_stderr, max_time_ms, no_output_timeout_ms
    ):
        """
        For parameters/returns, see :method: `Host.exec_command`.

        :return: exit_status int 0 or None implies success
        :raises: HostException for timeouts.
        """
        total_operation_start = datetime.now()
        total_operation_is_timed_out = host_utils.create_timer(total_operation_start, max_time_ms)
        no_output_timed_out = host_utils.create_timer(datetime.now(), no_output_timeout_ms)

        # The channel settimeout causes reads to throw 'socket.timeout' if data does not arrive
        # within that time. This is not necessarily an error, it allows us to implement
        # max time ms without having to resort to threading.
        ssh_stdout.channel.settimeout(0.1)

        # Stream the output of the command to the log
        while (
            not total_operation_is_timed_out()
            and not no_output_timed_out()
            and not ssh_stdout.channel.exit_status_ready()
        ):
            any_lines = host_utils.stream_lines(ssh_stdout, stdout)
            if any_lines:
                no_output_timed_out = host_utils.create_timer(datetime.now(), no_output_timeout_ms)

        # At this point we have either timed out or the command has finished. The code makes
        # a best effort to stream any remaining logs but the 'for line in ..' calls will
        # only block once for a max of 100 millis.
        #
        # Log the rest of stdout and stderr
        host_utils.stream_lines(ssh_stdout, stdout)
        host_utils.stream_lines(ssh_stderr, stderr)

        if ssh_stdout.channel.exit_status_ready():
            exit_status = ssh_stdout.channel.recv_exit_status()
        else:
            time_taken = (datetime.now() - total_operation_start).total_seconds()
            if no_output_timed_out():
                no_output = no_output_timeout_ms / host_utils.ONE_SECOND_MILLIS
                msg = (
                    "No Output in {} s (see test_control.timeouts.no_output_ms). {} s elapsed "
                    "on {} for '{}'".format(no_output, time_taken, self.alias, command)
                )
            else:
                max_time = max_time_ms / host_utils.ONE_SECOND_MILLIS
                msg = "{} exceeded {} allowable seconds on {} for '{}'".format(
                    time_taken, max_time, self.alias, command
                )
            raise host_utils.HostException(msg)

        return exit_status
