"""Download and install mongodb_binary_archive on all nodes."""


import logging
import os
import re
from functools import partial
from uuid import uuid4

# pylint: disable=too-few-public-methods
from dsi.common import host_factory
from dsi.common import host_utils
from dsi.common.thread_runner import run_threads

LOG = logging.getLogger(__name__)


def temp_file(path="mongodb.tgz", sanitize=lambda s: re.sub(r"[^A-Za-z0-9_\-.]", "", s)):
    """ create a temp file name based using the path as a suffix.
     The basename portion of the path will be sanitized and appended to a random UUID.
     If no path is provided then a name is generated using a default path. Worst case, the code will
     only return a random UUID.

     :param str path: The resource location, it can be a uri a full or a relative path
     :param lambda sanitize: a lambda to sanitize the path by removing unacceptable chars.
     The default lambda removes all chars not matching alphanumerics, '-','_' and '.'.

     :returns str a temp file based on this path
    """
    return "{}{}".format(str(uuid4()), sanitize(os.path.basename(path)))


class DownloadMongodb:
    """Download and install mongodb_binary_archive on all nodes."""

    def __init__(self, config):

        self.config = config
        self.mongodb_binary_archive = config["mongodb_setup"].get("mongodb_binary_archive", "")

        # If mongodb_binary_archive is set in runtime, use it instead. Previously we only did that
        # if the mongodb_binary_archive was "", but we have since added a useable default value.
        # This second if statement is necessary for backwards compatibility after changes
        # introducted in PERF-1044. It may be removed after all verions of system_perf.yml,
        # longevity.yml specify the mongodb_binary_archive in bootstrap.yml instead of runtime.yml.

        if "runtime" in list(config.keys()):
            self.mongodb_binary_archive = config["runtime"].get(
                "mongodb_binary_archive", self.mongodb_binary_archive
            )
        LOG.info("Download url is %s", self.mongodb_binary_archive)

        self.hosts = []
        for host_info in host_utils.extract_hosts("all_hosts", self.config):
            self.hosts.append(host_factory.make_host(host_info))

        if self.mongodb_binary_archive:
            LOG.debug("DownloadMongodb initialized with url: %s", self.mongodb_binary_archive)

    def download_and_extract(self):
        """Download self.mongodb_binary_archive, extract it, and create some symlinks.

        :return: True if no mongodb_binary_archive was provided or all the commands completed
                      successfully on all servers.
        """
        if not self.mongodb_binary_archive:
            LOG.warning(
                "DownloadMongodb: download_and_extract() was called, "
                "but mongodb_binary_archive isn't defined."
            )
            return True
        to_download = []
        for host in self.hosts:
            commands = self._remote_commands(host)
            to_download.append(partial(host.run, commands))

        return all(run_threads(to_download, daemon=True))

    def _remote_commands(self, host):
        mongo_dir = self.config["mongodb_setup"]["mongo_dir"]
        tmp_file = os.path.join(mongo_dir, temp_file(self.mongodb_binary_archive))
        return [
            ["echo", "Downloading {} to {}.".format(self.mongodb_binary_archive, host.hostname)],
            ["rm", "-rf", mongo_dir],
            ["rm", "-rf", "bin"],
            ["rm", "-rf", "jstests"],
            ["mkdir", mongo_dir],
            ["curl", "--retry", "10", "-fsS", self.mongodb_binary_archive, "-o", tmp_file],
            ["tar", "-C", mongo_dir, "-zxf", tmp_file],
            ["rm", "-f", tmp_file],
            ["cd", ".."],
            ["mv", mongo_dir + "/*/*", mongo_dir],
            ["mkdir", "-p", "bin"],
            ["ln", "-s", "${PWD}/" + mongo_dir + "/bin/*", "bin/"],
            ["ln", "-s", mongo_dir + "/jstests", "jstests"],
            ["bin/mongo", "--version"],
            [mongo_dir + "/bin/mongod", "--version"],
        ]
