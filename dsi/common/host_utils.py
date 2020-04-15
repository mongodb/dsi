"""
Utilities shared by different types of host objects
"""

import io
import itertools
import logging
import os
import select
import signal
import socket
import subprocess
from datetime import datetime
from functools import partial

from dsi.common.exit_status import EXIT_STATUS_OK
from dsi.common.log import IOLogAdapter
from dsi.common.models.host_info import HostInfo

ONE_SECOND_MILLIS = 1000.0
ONE_MINUTE_MILLIS = 60 * ONE_SECOND_MILLIS
TEN_MINUTE_MILLIS = 10 * ONE_MINUTE_MILLIS

LOG = logging.getLogger(__name__)
# This stream only log error or above messages
ERROR_ONLY = logging.getLogger("error_only")

INFO_ADAPTER = IOLogAdapter(LOG, logging.INFO)
WARN_ADAPTER = IOLogAdapter(LOG, logging.WARN)


class HostException(Exception):
    """ Raise for exec command timeouts and use it to wraps ssh exceptions. """


def setup_ssh_agent(config):
    """
    Setup the ssh-agent, and update our environment for it.

    :param ConfigDict config: The system configuration
    """
    ssh_agent_info = subprocess.check_output(["ssh-agent", "-s"], encoding="utf-8")
    # This expansion updates our environment by parsing the info from the previous line. It splits
    # the data into lines, and then for any line of the form "key=value", adds {key: value} to the
    # environment.
    os.environ.update(
        dict(
            (a.strip(), b.strip())
            for a, b in [line.split("=") for line in ssh_agent_info.split(";") if "=" in line]
        )
    )
    (_, ssh_key_file) = ssh_user_and_key_file(config)
    subprocess.check_call(["ssh-add", ssh_key_file])


# https://stackoverflow.com/questions/23064636/python-subprocess-popen-blocks-with-shell-and-pipe
def restore_signals():
    """
    Restore signals in the child process or the process block forever
    """
    signals = ("SIGPIPE", "SIGXFZ", "SIGXFSZ")
    for sig in signals:
        if hasattr(signal, sig):
            signal.signal(getattr(signal, sig), signal.SIG_DFL)


def close_safely(stream):
    """
    Close the stream.

    :param object stream: The stream instance or None
    """
    if stream is not None:
        stream.close()


def raise_if_not_ok(status, message):
    """ raise a HostExceptipn if status is not EXIT_STATUS_OK."""
    assert isinstance(status, (int, float)), "success must be int or float"
    if status != EXIT_STATUS_OK:
        raise HostException(status, message)


def raise_if_not_success(success, message):
    """ raise a HostExceptipn if success is False."""
    assert isinstance(success, bool), "success must be boolean"
    if success is False:
        raise HostException(1, message)


def reraise_as_host_exception(exception):
    """ wrap a exception as a HostException."""
    if isinstance(exception, subprocess.CalledProcessError):
        status = exception.returncode  # pylint: disable=no-member
        message = exception.output  # pylint: disable=no-member
    else:
        status = 1
        message = repr(exception)
    raise HostException(status, message)


def _extract_hosts(category, config):
    """
    Extract a list of public IP addresses for hosts based off of the category.
    Valid categories are mongod, mongos, configsvr, and workload_client.

    :param str category: The category to use (mongod, mongod, ...)
    :param ConfigDict config: The system configuration
    :rtype: list of HostInfo objects
    """
    if category in config["infrastructure_provisioning"]["out"]:
        ssh_user, ssh_key_file = ssh_user_and_key_file(config)
        return [
            HostInfo(
                public_ip=host_info["public_ip"],
                private_ip=host_info["private_ip"],
                ssh_user=ssh_user,
                ssh_key_file=ssh_key_file,
                category=category,
                offset=i,
            )
            for i, host_info in enumerate(config["infrastructure_provisioning"]["out"][category])
        ]
    return list()


def extract_hosts(key, config):
    """
    Extract a list of public IP addresses for hosts based off of the key. Valid keys are mongod,
    mongos, configsvr, workload_client, as well as the helpers all_hosts and all_servers.

    :param ConfigDict config: The system configuration
    """

    if key == "localhost":
        # `offset` is arbitrary for localhost, for other hosts, it represents the index of a node.
        return [
            HostInfo(public_ip="localhost", private_ip="localhost", category="localhost", offset=0)
        ]
    if key == "all_servers":
        return list(
            itertools.chain.from_iterable(
                (_extract_hosts(key, config) for key in ["mongod", "mongos", "configsvr"])
            )
        )
    if key == "all_hosts":
        return list(
            itertools.chain.from_iterable(
                (
                    _extract_hosts(key, config)
                    for key in ["mongod", "mongos", "configsvr", "workload_client"]
                )
            )
        )
    return _extract_hosts(key, config)


def never_timeout():
    """
    Function that never times out
    """
    return False


def check_timed_out(start, max_time_ms):
    """
    Check if max time ms has passed.

    :param datetime start: The start time
    :param max_time_ms: The max allowable time to run for or None for no timeout
    :type max_time_ms: int, float, None
    """
    delta = (datetime.now() - start).total_seconds() * ONE_SECOND_MILLIS
    return delta > max_time_ms


def create_timer(start, max_time_ms):
    """
    Create a watchdog timeout function.

    :param datetime start: The start time
    :param max_time_ms: The time limit in milliseconds for processing this operation, defaults to
    None (no timeout)
    :type max_time_ms: int, float, None
    :rtype: function that returns True when max_time_ms has elapsed
    """
    if max_time_ms is None:
        is_timed_out = never_timeout
    else:
        is_timed_out = partial(check_timed_out, start, max_time_ms)
    return is_timed_out


# pylint: disable=too-many-arguments
def stream_proc_logs(
    proc: subprocess.Popen, out: io.TextIOWrapper, err: io.TextIOWrapper, is_timedout, timeout_s=0.5
):
    """
    Stream proc.stdout and proc.stderr to out and err.

    :param subprocess proc: The process to stream the logs for
    :param IO out: The proc.stdout stream destination
    :param IO err: The proc.stderr stream destination
    :param function is_timedout: Determine if the max allowable amount of time has elapsed
    :param float timeout_s: Select waits for up to a max of this amount of seconds
    """
    try:
        # Stream standard out
        while True:
            if is_timedout():
                return False
            ready, _, _ = select.select((proc.stdout, proc.stderr), (), (), timeout_s)

            if proc.stdout in ready:
                line = proc.stdout.readline()
                if line:
                    out.write(line)
                elif proc.returncode is not None:
                    # The program has exited, and we have read everything written to stdout
                    ready.remove(proc.stdout)

            if proc.stderr in ready:
                line = proc.stderr.readline()
                if line:
                    err.write(line)
                elif proc.returncode is not None:
                    # The program has exited, and we have read everything written to stderr
                    ready.remove(proc.stderr)

            if proc.poll() is not None and not ready:
                break
    # Closed stream
    except ValueError:
        pass
    return True


def stream_lines(source, destination):
    """
    Stream lines from source to destination. Silently hand socket.timeouts.

    :param IO source: Reads lines from this stream
    :param IO destination: Writes lines to this stream
    """
    any_lines = False
    try:
        for line in source:
            destination.write(line)
            any_lines = True
    except socket.timeout:
        pass
    return any_lines


def ssh_user_and_key_file(config):
    """
    Get ssh user and key file from the config.

    :param ConfigDict config: the config dictionary.
    :return: 2-tuple of strings for the ssh user and ssh key file.
    """
    ssh_user = config["infrastructure_provisioning"]["tfvars"]["ssh_user"]
    ssh_key_file = config["infrastructure_provisioning"]["tfvars"]["ssh_key_file"]
    ssh_key_file = os.path.expanduser(ssh_key_file)
    return ssh_user, ssh_key_file
