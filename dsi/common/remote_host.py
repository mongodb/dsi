"""
Provide abstraction over running commands on remote machines, extending the base class in host.py
"""

import logging
import os
import shutil
import socket
import sys
import tempfile
from contextlib import closing
from stat import S_ISDIR

import paramiko

from dsi.common import host_utils
from dsi.common.host import Host

LOG = logging.getLogger(__name__)
# This stream only log error or above messages
ERROR_ONLY = logging.getLogger("error_only")


class RemoteHost(Host):
    """
    Represents a remote host
    """

    # pylint: disable=too-many-arguments
    def __init__(self, hostname, username, pem_file, mongodb_auth_settings=None, use_tls=False):
        """
        :param hostname: hostname
        :param username: username
        :param pem_file: ssh pem file
        """
        super(RemoteHost, self).__init__(hostname, mongodb_auth_settings, use_tls)
        LOG.debug("hostname: %s, username: %s, pem_file: %s", hostname, username, pem_file)
        try:
            ssh, ftp = self.connected_ssh(hostname, username, pem_file)
            self._ssh = ssh
            self.ftp = ftp
            self.user = username
        except (paramiko.SSHException, socket.error):
            sys.exit(1)

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
        Execute the argv command on the remote host and log the output.

        For parameters/returns, see :method: `Host.exec_command`.
        :raises: HostException for timeouts and to wrap paramiko.SSHException
        """
        raise NotImplementedError()

    def create_file(self, remote_path, file_contents):
        """
        Creates a file on the remote host
        """
        remote_file = self.ftp.file(remote_path, "w")
        with closing(remote_file):
            remote_file.write(file_contents)
            remote_file.flush()

    def upload_file(self, local_path, remote_path):
        """
        Copy a file or directory to the host.
        Uploading large files or a directory with lots of files may be slow as we don't do any
        compression.

        :raises: HostException on error
        """
        if os.path.isdir(local_path):
            self._upload_dir(local_path, remote_path)
        else:
            self._upload_single_file(local_path, remote_path)

    def _upload_dir(self, local_path, remote_path):
        """
        Upload a directory, local->remote.
        Internally works by creating a tarball and uploading and unpacking that.

        :param local_path: Local directory to upload
        :param remote_path: Destination directory. Must already exist.
        :raises: HostException on error
        """
        temp_dir = tempfile.mkdtemp()
        try:
            self.__upload_dir_unsafe(local_path, remote_path, temp_dir)
        finally:
            shutil.rmtree(temp_dir)

    def __upload_dir_unsafe(self, local_path, remote_path, temp_dir):
        """
        Upload a directory, local->remote, using a temporary tarball to store an intermediary
        tarball. If any exceptions during tar-ing or uploading, this won't clean up the temporary
        directory.

        :param local_path: Local directory to upload
        :param remote_path: Destination directory. Must already exist.
        :param temp_dir: Temporary directory to store intermediary tarball
        :raises: HostException on error
        """
        tarball_name = "{}.tar".format(os.path.basename(remote_path))
        remote_parent_dir = os.path.dirname(remote_path)
        remote_tarball_path = os.path.join(remote_parent_dir, tarball_name)

        tarball_path = shutil.make_archive(
            os.path.join(temp_dir, tarball_name), "tar", local_path, "."
        )

        # Make way and upload it
        cmd = ["mkdir", "-p", remote_path]
        exit_status = self.exec_command(cmd)
        host_utils.raise_if_not_ok(exit_status, cmd)

        try:
            # should raise an exception on error
            self._upload_single_file(tarball_path, remote_tarball_path)
        except Exception as e:  # pylint: disable=broad-except
            host_utils.reraise_as_host_exception(e)

        # Untar it. Have to rely on shell because tarfile doesn't operate remotely.
        cmd = ["tar", "xf", remote_tarball_path, "-C", remote_path]
        exit_status = self.exec_command(cmd)
        host_utils.raise_if_not_ok(exit_status, cmd)

        # Cleanup remote
        self.exec_command(["rm", remote_tarball_path])

    def _upload_single_file(self, local_path, remote_path):
        """
        Upload single file, local->remote. Must be a single file (not a directory). For type-aware
        transfer, see upload_file.

        :param local_path: Local file to upload
        :param remote_path: Local file destination
        """
        self.ftp.put(local_path, remote_path)

        # Get standard permissions mask e.g. 0755
        source_permissions = os.stat(local_path).st_mode & 0o0777
        self.ftp.chmod(remote_path, source_permissions)

    def remote_exists(self, remote_path):
        """
        Test whether a remote path exists, returns False if it doesn't exist or on error.

        :param str remote_path: The remote path
        """
        try:
            self.ftp.stat(remote_path)
        except (IOError, paramiko.SFTPError, os.error):
            return False
        return True

    def remote_isdir(self, remote_path):
        """
        Test whether a remote path exists and is a directory, returns False if it doesn't exist or
        on error.

        :param str remote_path: The remote path
        """
        try:
            stat = self.ftp.stat(remote_path)
        except os.error:
            return False
        return S_ISDIR(stat.st_mode)

    def _retrieve_file(self, remote_file, local_file):
        """
        Retrieve a single remote file. The local directories will be created, if required.

        :param str local_file: The local filename, it must be a filename.
        :param str remote_file: The remote file location, it must be a filename.
        """
        LOG.debug("_retrieve_files: file '%s:%s' ", self.alias, remote_file)
        local_dir = os.path.dirname(local_file)
        local_dir = os.path.normpath(local_dir)
        if not os.path.exists(local_dir):
            os.makedirs(local_dir)
        self.ftp.get(remote_file, os.path.normpath(local_file))

    def retrieve_path(self, remote_path, local_path):
        """
        Retrieve a path from a remote server. If the remote_path is a directory, then the contents
        of the directory are downloaded recursively. If not then the single file will be downloaded
        to the local path.

        Any path elements in the local path will only be created if and when a file is downloaded.
        As a result, an empty directory tree will not be created locally.

        :param str local_path: The path (file or directory) to download to. This can contain
        relative paths, these paths will only be normalized at the last possible moment.
        :param str remote_path: The remote path, this can be a file or directory location. The path
        will be normalized immediately.
        """
        if not self.remote_exists(remote_path):
            LOG.debug("retrieve_files '%s:%s' does not exist.", self.alias, remote_path)
            return

        if self.remote_isdir(remote_path):
            LOG.debug("retrieve_files: directory '%s:%s'", self.alias, remote_path)

            for filename in self.ftp.listdir(remote_path):
                remote = os.path.join(remote_path, filename)

                local_file = os.path.join(local_path, filename)
                local_file = os.path.normpath(local_file)

                self.retrieve_path(remote, local_file)
        else:
            self._retrieve_file(remote_path, local_path)

    def close(self):
        """
        Close the ssh connection
        """
        self._ssh.close()
        self.ftp.close()

    @staticmethod
    def connected_ssh(host, user, pem_file):
        """
        Create a connected paramiko ssh client and ftp connection
        or raise if cannot connect.

        :param host: hostname to connect to
        :param user: username to use
        :param pem_file: ssh pem file for connection
        :return: paramiko (SSHClient, SFTPClient) tuple
        """
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.client.AutoAddPolicy())
        try:
            ssh.connect(host, username=user, key_filename=pem_file)
            ftp = ssh.open_sftp()
            # Paramiko will send connection metadata every 58 seconds.
            ssh.get_transport().set_keepalive(58)
            # Setup authentication forwarding. See
            # https://stackoverflow.com/questions/23666600/ssh-key-forwarding-using-python-paramiko
            session = ssh.get_transport().open_session()
            paramiko.agent.AgentRequestHandler(session)
            LOG.info("Successfully connected to %s", host)
        except (paramiko.SSHException, socket.error) as err:
            LOG.exception("Failed to connect to %s@%s", user, host)
            raise err
        return ssh, ftp
