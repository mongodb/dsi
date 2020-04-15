"""
Provide abstraction over running commands on local machines, extending the base class in host.py
"""


import logging
import shutil
import subprocess
from datetime import datetime

import six

from dsi.common import host
from dsi.common import host_utils
from dsi.common.log import IOLogAdapter

LOG = logging.getLogger(__name__)
# This stream only log error or above messages
ERROR_ONLY = logging.getLogger("error_only")

INFO_ADAPTER = IOLogAdapter(LOG, logging.INFO)
WARN_ADAPTER = IOLogAdapter(LOG, logging.WARN)


class LocalHost(host.Host):
    """
    Represents a connection to the local host
    """

    def __init__(self, mongodb_auth_settings=None, use_tls=False):
        super(LocalHost, self).__init__("localhost", mongodb_auth_settings, use_tls)
        self.user = "-"

    # pylint: disable=unused-argument
    # pylint: disable=too-many-arguments
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
        Execute the command on the local host and log the output.

        For parameters/returns, see :method: `Host.exec_command`.
        """
        if quiet:
            logger = ERROR_ONLY
        else:
            logger = LOG

        if no_output_timeout_ms is not None:
            logger.error("no_output_timeout_ms %s not supported on LocalHost", no_output_timeout_ms)
        if not argv or not isinstance(argv, (list, six.string_types)):
            raise ValueError("Argument must be a nonempty list or string.")
        if stdout is None:
            stdout = INFO_ADAPTER
        if stderr is None:
            stderr = WARN_ADAPTER

        command = str(argv)
        if isinstance(argv, list):
            command = " ".join(argv)

        start = datetime.now()
        logger.debug("[localhost]$ %s", command)
        proc = subprocess.Popen(
            ["bash", "-c", command],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
        )
        is_timed_out = host_utils.create_timer(start, max_time_ms)
        if host_utils.stream_proc_logs(proc, stdout, stderr, is_timed_out):
            exit_status = proc.returncode
            if exit_status != 0:
                logger.warning(
                    "%s '%s': Failed with exit status %s", self.alias, command, exit_status
                )
        else:
            exit_status = 1
            logger.warning(
                "%s '%s': Timeout after %f seconds with exit status %s",
                self.alias,
                command,
                (datetime.now() - start).total_seconds(),
                exit_status,
            )
        return exit_status

    # pylint: disable=no-self-use
    def create_file(self, remote_path, file_contents):
        """
        Creates a file on the local host
        """
        with open(remote_path, "w") as local_file:
            local_file.write(file_contents)

    def upload_file(self, local_path, remote_path):
        """
        Copy a file to the host
        """
        if local_path == remote_path:
            LOG.warning("Uploading file locally to same path. Skipping step")
        else:
            shutil.copyfile(local_path, remote_path)
            shutil.copymode(local_path, remote_path)

    def retrieve_path(self, remote_path, local_path):
        """
        Retrieve a file from the host
        """
        if local_path == remote_path:
            LOG.warning("Retrieving file locally to same path. Skipping step")
        shutil.copyfile(remote_path, local_path)
