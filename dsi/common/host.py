"""
Provide abstraction over running commands on remote or local machines
"""


import logging
import os
import signal
import time
from datetime import datetime

# pylint doesn't know about the `# type:` comments
import typing as typ  # pylint: disable=unused-import
import pymongo.uri_parser

from dsi.common import host_utils
from dsi.common.log import IOLogAdapter
from dsi.common.utils import mkdir_p

LOG = logging.getLogger(__name__)
# This stream only log error or above messages
ERROR_ONLY = logging.getLogger("error_only")

INFO_ADAPTER = IOLogAdapter(LOG, logging.INFO)
WARN_ADAPTER = IOLogAdapter(LOG, logging.WARN)


class Host:
    """
    Base class for hosts
    """

    def __init__(self, hostname, mongodb_auth_settings=None, use_tls=False):
        self.user = ""
        self._alias = None
        self.hostname = hostname
        self.mongodb_auth_settings = mongodb_auth_settings
        self.use_tls = use_tls

    @property
    def alias(self):
        """
        Property getter.

        :rtype: The alias or the host if alias is not set
        """
        if not self._alias:
            return self.hostname
        return self._alias

    @alias.setter
    def alias(self, alias):
        self._alias = alias

    # pylint: disable=too-many-arguments
    def exec_command(
        self,
        argv,  # type: typ.Union[typ.List[str], str]
        stdout=None,
        stderr=None,
        get_pty=False,
        max_time_ms=None,  # type: int
        no_output_timeout_ms=None,  # type: int
        quiet=False,  # type: int
    ):
        # type: (...) -> typ.Optional[int]
        """
        Execute the command and log the output.

        :param argv: The command to run
        :type argv: str, list
        :param IO stdout: Standard out from the command is written to this IO. If None is supplied
        then the INFO_ADAPTER will be used.
        :param IO stderr: Standard err from the command is written to this IO on error. If None is
        supplied then the WARN_ADAPTER will be used.
        :param bool get_pty: Only valid for remote commands. If pty is set to True, then the shell
        command is executed in a pseudo terminal. As a result, the commands will be killed if the
        host is closed.
        :param max_time_ms: the time limit in milliseconds for processing this operation.
                            Defaults to None (no timeout).
        :type max_time_ms: int, float or None.
        :param no_output_timeout_ms: the amount of time the command is allowed to go without
        any output on stdout. Not all host implementations support this - namely only
        RemoteHost at the moment
        :type no_output_timeout_ms: int, float, or None
        :param bool quiet: don't log failure if this is set to True. Defaults to False.

        :return: int or None (the exit status) 0 or None implies success anything else is an error.
        :raises: HostException for timeouts or implementation specific issues.
        """
        raise NotImplementedError()

    def run(self, argvs, quiet=False):
        # type: (typ.Union[typ.List[str], str], bool) -> bool
        """
        Runs a command or list of commands.

        :param argvs: The string to execute, or one argument vector or list of argv's [file, arg]
        :type argvs: str, list
        :param bool quiet: don't log failures if set to True. Defaults to False.

        :return: True if all the command succeeded. This method returns a boolean (rather than
        raising an exception) because this allows the caller to determine if a failure is
        expected or accepted. For example 'pgrep mongod' can fail if no mongod is running. This
        is not an error / exceptional.
        Note: exceptions may be raised by the lower layer, see :method: `Host.exec_command`.
        """
        if not argvs or not isinstance(argvs, (list, str)):
            raise ValueError("Argument must be a nonempty list or string.")

        # Log just the first line of what we are about to execute
        command_prefix = str(argvs)[:50]
        if command_prefix != str(argvs):
            command_prefix = command_prefix + "  <cut>"
        command_prefix = command_prefix.replace("\n", "\\n")
        LOG.info("    [%s@%s]$ %s", self.user, self.hostname, command_prefix)

        if isinstance(argvs, str):
            return self.exec_command(argvs, quiet=quiet) == 0

        if not isinstance(argvs[0], list):
            argvs = [argvs]

        return all(self.exec_command(argv, quiet=quiet) == 0 for argv in argvs)

    def _validate_connection_string(self, connection_string):
        """
        Validates that self.mongodb_auth_settings matches what is specified in the connection string
        if auth credentials are present in both places.

        :param str connection_string: Connection information regarding a MongoDB instance.

        :rtype: (bool, str)
        :return: A pair with the first element indicating whether the username and password were
        found in the connection string and the second element representing a valid MongoDB
        connection URI.

        :raises: ValueError for invalid connection strings.
        """

        if not connection_string:
            # command_runner.py only forwards the 'connection_string' argument so we permit using
            # the empty string to represent using the default value.
            connection_string = "mongodb://localhost:27017"

        if not connection_string.startswith(("mongodb://", "mongodb+srv://")):
            # Some callers omit the mongodb:// scheme so we add it ourselves to make
            # pymongo.uri_parser.parse_uri() happy.
            connection_string = "mongodb://" + connection_string

        # The changes from SERVER-32164 made it possible for the mongo shell to receive both the
        # --username/--password command line options and for "username:password@" to appear in the
        # connection string. Until we stop supporting MongoDB 3.4, we need to avoid specifying the
        # command line options if the auth settings are already present in the connection string. We
        # reimplement the check here to verify that both sets of usernames and passwords match.
        parsed_options = pymongo.uri_parser.parse_uri(connection_string)
        if parsed_options.get("username") and parsed_options.get("password"):
            if self.mongodb_auth_settings:
                if self.mongodb_auth_settings.mongo_user != parsed_options.get("username"):
                    raise ValueError(
                        "Username '{}' in mongodb_auth_settings doesn't match username '{}' in"
                        " connection string".format(
                            self.mongodb_auth_settings.mongo_user, parsed_options.get("username")
                        )
                    )
                if self.mongodb_auth_settings.mongo_password != parsed_options.get("password"):
                    raise ValueError(
                        "Password '{}' in mongodb_auth_settings doesn't match password '{}' in"
                        " connection string".format(
                            self.mongodb_auth_settings.mongo_password,
                            parsed_options.get("password"),
                        )
                    )
            return (True, connection_string)

        if parsed_options.get("username") or parsed_options.get("password"):
            raise ValueError(
                "Must specify both username and password in connection string, or neither"
            )

        return (False, connection_string)

    def exec_mongo_command(
        self,
        script,
        remote_file_name="script.js",
        connection_string="",
        stdout=None,
        stderr=None,
        max_time_ms=None,
        quiet=False,
    ):
        """
        Executes script in the mongo on the connection string. Returns the status code of executing
        the script.

        :param str script: The javascript to be run
        :param str remote_file_name: Name and path of file to create with script contents
        :param str connection_string: Connection information of mongo instance to run script on
        :param max_time_ms: The time limit in milliseconds for processing this operations, defaults
        to None (no timeout)
        :type max_time_ms: int, float, None
        :param bool quiet: don't log failures if set to True. Defaults to False.
        """
        argv = ["bin/mongo", "--quiet"]

        (has_auth_settings, connection_string) = self._validate_connection_string(connection_string)

        if self.mongodb_auth_settings and not has_auth_settings:
            argv.extend(
                [
                    "-u",
                    self.mongodb_auth_settings.mongo_user,
                    "-p",
                    self.mongodb_auth_settings.mongo_password,
                    "--authenticationDatabase",
                    "admin",
                ]
            )

        # --sslAllowInvalidHostnames is necessary when we use ip addresses and localhost.
        # TODO: Change all mongodb_setup code to use the hostnames instead.
        if self.use_tls:
            argv.extend(["--ssl", "--sslAllowInvalidHostnames"])

        # connection_string can contain ampersands, escape them.
        # Note that quoting doesn't work because gRPC is not a shell and treats quotes
        # around strings as just literal quote characters.
        connection_string = connection_string.replace("&", r"\&")

        argv.extend([connection_string, remote_file_name])

        self.create_file(remote_file_name, script)
        # TODO: Capture this output and redirect into LOG.debug()
        # self.run(['cat', remote_file_name])

        status_code = self.exec_command(
            argv, stdout=stdout, stderr=stderr, max_time_ms=max_time_ms, quiet=quiet
        )
        return status_code

    def kill_remote_procs(
        self,
        name,
        signal_number=int(signal.SIGKILL),
        delay_ms=host_utils.ONE_SECOND_MILLIS,
        max_time_ms=host_utils.TEN_MINUTE_MILLIS,
    ):
        """
        Kills all processes on the host matching name pattern.

        :param str name: The process name pattern. This pattern only matches on the process name.
        :param int signal_number: The signal to send, defaults to SIGKILL(9). It should be a valid
        signal.
        :param delay_ms: The milliseconds to sleep for before checking if the processes valid
        shutdown. Defaults to 1 second (in millis), it should be greater than 0.
        :type delay_ms: int, float
        :param max_time_ms: The time limit in milliseconds for processing this operation, defaults
        to None (no timeout)
        :type max_time_ms: int, float, None
        """
        signal_number = "-" + str(signal_number)
        delay_seconds = delay_ms / host_utils.ONE_SECOND_MILLIS
        if max_time_ms == 0:
            max_time_ms = delay_ms

        is_timed_out = host_utils.create_timer(datetime.now(), max_time_ms)

        while not is_timed_out():
            self.run(["pkill", signal_number, name], quiet=True)
            if not self.run(["pgrep", name], quiet=True):
                return True
            time.sleep(delay_seconds)

        return False

    def kill_mongo_procs(
        self, signal_number=int(signal.SIGKILL), max_time_ms=30 * host_utils.ONE_SECOND_MILLIS
    ):
        """
        Kills all processes matching the patterm 'mongo' (includes 'mongo', 'mongos', 'mongod') on
        the host by sending signal_number every second until there are no matching processes or the
        timeout has elapsed.

        :param int signal_number: The signal to send, defaults to SIGKILL(9). It must be greater
        than 0 and a valid signal.
        :param max_time_ms: The time limit in milliseconds for processing this operation, defaults
        to None (no timeout)
        :type max_time_ms: int, float, None
        """
        return self.kill_remote_procs("mongo", signal_number, max_time_ms=max_time_ms)

    def create_file(self, remote_path, file_contents):
        """
        Creates a file on the remote host
        """
        raise NotImplementedError()

    # Note: Try to keep arguments for all these methods in a (source, destination) order
    def upload_file(self, local_path, remote_path):
        """
        Copy a file to the host
        """
        raise NotImplementedError()

    def retrieve_path(self, remote_path, local_path):
        """
        Retrieve a file from the host
        """
        raise NotImplementedError()

    def checkout_repos(self, source, target, branch=None, verbose=False):
        """
        Clone repository from GitHub into target directory.

        :param str source: Link to GitHub repository
        :param str target: Path to target directory
        :param branch: Specific branch to clone, if None clones default branch.
        :types branch: str, None
        :param bool verbose: Use the --quiet flag for clone and checkout if verbose is False.
        Defaults to False.
        """
        quiet_arg = "" if verbose else "--quiet"
        if not os.path.isdir(target):
            LOG.info("checkout_repos target directory %s does not exist", target)
            mkdir_p(os.path.dirname(target))
            self.exec_command(["git", "clone", quiet_arg, source, target])
            if branch is not None:
                self.exec_command(["cd", target, "&&", "git", "checkout", quiet_arg, branch])
        elif self.exec_command(["cd", target, "&&", "git", "status"]) != 0:
            raise UserWarning("{} exists and is not a git repository".format(target))
        else:
            LOG.info("checkout_repos target directory %s exists and is a git repository", target)

    def close(self):
        """
        Cleanup any connections
        """
