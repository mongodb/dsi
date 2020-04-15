#!/usr/bin/env python3.7

"""
Setup hosts for running various kinds of workload types
"""


import logging
import sys

import argparse

from dsi.common import command_runner, canaries
from dsi.common import host_utils
from dsi.common.config import ConfigDict
from dsi.common.log import setup_logging

LOG = logging.getLogger(__name__)


class WorkloadSetupRunner:
    """
    Responsible for invoking workload_setup.yml commands before test_control
    """

    def __init__(self, config):
        """
        Constructor.

        :param config: The system configuration
        """
        self.config = config

    def test_types(self):
        """
        Indicates which test types we have in test_control.

        :return: Test-types for which we need to run the associated workload_setup blocks
        :rtype: set(string)
        """
        return {run["type"] for run in self.config["test_control"]["run"]}

    def setup_workloads(self):
        """
        Perform setup for all the required workload types
        """
        host_utils.setup_ssh_agent(self.config)
        types = list(self.test_types())
        if canaries.should_run(self.config) is True:
            types.extend(canaries.CANARY_TYPES)
        types.sort()
        for test_type in types:
            self.run_setup_for_test_type(test_type)

    def run_setup_for_test_type(self, test_type):
        """
        Run setup for a particular test type.

        :param string test_type: Workload_setup key listing commands to run
        """
        LOG.info("Starting workload_setup for test_type %s", test_type)
        steps = self.config["workload_setup"][test_type]
        command_runner.run_host_commands(steps, self.config, "workload_setup")


# pylint: disable=dangerous-default-value
def main(argv=sys.argv[1:]):
    """
    Parse args and call workload_setup.yml operations
    """
    parser = argparse.ArgumentParser(description="Workload Setup")

    parser.add_argument("-d", "--debug", action="store_true", help="enable debug output")
    parser.add_argument("--log-file", help="path to log file")

    args = parser.parse_args(argv)
    setup_logging(args.debug, args.log_file)

    config = ConfigDict("workload_setup")
    config.load()

    setup = WorkloadSetupRunner(config)
    setup.setup_workloads()


if __name__ == "__main__":
    main()
