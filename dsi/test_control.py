#!/usr/bin/env python3.7
""" Test runner in DSI Framework """

import glob
import logging
import os
import shutil
import subprocess
import sys
import time

import argparse
import yaml
from nose.tools import nottest

from dsi.common import cedar, canaries
from dsi.common import command_runner
from dsi.common import log
from dsi.common.command_runner import run_pre_post_commands, EXCEPTION_BEHAVIOR, prepare_reports_dir
from dsi.common.config import ConfigDict
from dsi.common.exit_status import EXIT_STATUS_OK
from dsi.common.host_utils import extract_hosts, setup_ssh_agent
from dsi.common.jstests import run_validate
from dsi.common.workload_output_parser import parse_test_results, get_supported_parser_types
from dsi.testcontrollib import test_runner

LOG = logging.getLogger(__name__)


def print_perf_json(filename="perf.json"):
    """
    Read perf.json into the log file
    """
    if os.path.isfile(filename):
        with open(filename) as perf_file:
            for line in perf_file:
                LOG.info(line.rstrip())


def copy_to_reports(reports_dir="reports", perf_json="perf.json"):
    """
    Copy perf.json and all yml files under reports/.
    This is useful when running test_control.py many times with different configurations.
    You want to save config and results for all of them.
    """
    if os.path.isfile(perf_json):
        LOG.debug("Copying %s to %s", perf_json, reports_dir)
        shutil.copy(perf_json, reports_dir)
    for yaml_file in glob.glob("*.yml"):
        LOG.debug("Copying %s to %s", yaml_file, reports_dir)
        shutil.copy(yaml_file, reports_dir)


def generate_config_file(test, local_dir, client_host):
    """
    Generate configuration files from the test run, save them in the report directory, and upload
    them to the client host

    :param ConfigDict test: The configuration for the test
    :param str local_dir: The local directory where the configuration file should be stored
    :param Host client_host: The client host to which the configuration file will be uploaded
    """
    try:
        filepath = os.path.join(local_dir, test["config_filename"])
        workload_config = test["workload_config"]
        with open(filepath, "w") as workloads_file:
            if isinstance(workload_config, (ConfigDict, dict)):
                # Can't assign into config dict. Need an actual dictionary
                workload_config_dict = (
                    workload_config.as_dict()
                    if isinstance(workload_config, ConfigDict)
                    else workload_config
                )
                if "scale_factor" in workload_config_dict and isinstance(
                    workload_config_dict["scale_factor"], str
                ):
                    # pylint: disable=eval-used
                    workload_config_dict["scale_factor"] = eval(
                        workload_config_dict["scale_factor"]
                    )
                workloads_file.write(yaml.dump(workload_config_dict))
            elif isinstance(workload_config, str):
                workloads_file.write(workload_config)
        client_host.upload_file(filepath, test["config_filename"])
    except KeyError:
        LOG.warning("No workload config in test control")


def copy_timeseries(config):
    """ copy the files required for timeseries analysis from
    their legacy mission-control locations to the new locations used by host.py.

    :param dict(ConfigDict) config: The system configuration

    """
    hosts = extract_hosts("all_servers", config)
    for root, _, files in os.walk("./reports"):
        for name in files:
            # The following generator find the first host with an ip that matches
            # the filename. The (.. for in if in ) generator will return 0 or more
            # matches.
            #
            # In the non matching case, next would throw StopIteration . The
            # None final param ensures that something 'Falsey' is returned instead.
            host = next((host for host in hosts if name.endswith(host.public_ip)), None)
            if host:
                source = os.path.join(root, name)
                alias = "{category}.{offset}".format(category=host.category, offset=host.offset)

                destination = "{}-{}".format(
                    os.path.basename(source).split("--")[0], os.path.basename(root)
                )
                destination = os.path.join("reports", alias, destination)
                shutil.copyfile(source, destination)


@nottest
def run_test(test, config):
    """
    Run one test. This creates a Host object, runs the command, and saves the output to a file.

    :param test ConfigDict: The ConfigDict object for the test to run
    :param config ConfigDict: The top level ConfigDict
    """
    runner = test_runner.get_test_runner(test, config["test_control"])
    client_host = command_runner.make_workload_runner_host(config)

    # Generate and upload the test's configuration file if there is one.
    generate_config_file(test, runner.report_dir, client_host)

    status = runner.run(client_host)

    client_host.close()

    # Store exit status for dsi/analysis.py
    config["test_control"]["out"]["exit_codes"][test["id"]] = {
        "status": status.status,
        "message": status.message,
    }
    if status.status != EXIT_STATUS_OK:
        raise subprocess.CalledProcessError(status.status, test["id"], output=status.message)

    return status


class TestStatus:
    """Status of this script."""

    FAILED = "failed"
    SUCCESS = "succeeded"
    ERROR = "failed with unknown error"


# pylint: disable=too-many-branches,too-many-statements,too-many-nested-blocks,too-many-locals
@nottest
def run_tests(config):
    """Main logic to run tests

    :return: True if all tests failed or an error occurred.
             No more tests are run when an error is encountered.
    """
    config["test_control"]["out"] = {"exit_codes": {}}
    test_control_config = config["test_control"]
    mongodb_setup_config = config["mongodb_setup"]

    setup_ssh_agent(config)
    prepare_reports_dir()

    validate_config(config)
    run_pre_post_commands(
        "pre_task", [mongodb_setup_config, test_control_config], config, EXCEPTION_BEHAVIOR.EXIT
    )

    if "test_delay_seconds" in test_control_config:
        test_delay_seconds = test_control_config["test_delay_seconds"]
    else:
        test_delay_seconds = 0

    num_tests_run = 0
    num_tests_failed = 0

    # cedar reporting
    report = cedar.Report(config.get("runtime"))

    # Default the status to ERROR to catch unexpected failures.
    # If a tests succeeds, the status is explicitly set to SUCCESS.
    cur_test_status = TestStatus.ERROR

    try:
        if os.path.exists("perf.json"):
            os.remove("perf.json")
            LOG.warning("Found old perf.json file. Overwriting.")

        tests = test_control_config["run"]
        tests.extend(canaries.get_canaries(config))

        for test in tests:
            LOG.info("running test %s", test)
            timer = {}
            try:
                # Only run between_tests after the first test.
                if num_tests_run > 0:
                    run_pre_post_commands(
                        "between_tests",
                        [mongodb_setup_config, test_control_config],
                        config,
                        EXCEPTION_BEHAVIOR.RERAISE,
                    )
                run_pre_post_commands(
                    "pre_test",
                    [mongodb_setup_config, test_control_config, test],
                    config,
                    EXCEPTION_BEHAVIOR.RERAISE,
                    test["id"],
                )

                if test_delay_seconds:
                    LOG.info(
                        "Sleeping for %s seconds before test %s", test_delay_seconds, test["id"]
                    )
                    time.sleep(test_delay_seconds)

                LOG.info("Starting test %s", test["id"])
                timer["start"] = time.time()
                # Run the actual test
                run_test(test, config)
            except subprocess.CalledProcessError:
                LOG.error("test %s failed.", test["id"], exc_info=1)
                cur_test_status = TestStatus.FAILED
            except:  # pylint: disable=bare-except
                LOG.error("Unexpected failure in test %s.", test["id"], exc_info=1)
                cur_test_status = TestStatus.ERROR
            else:
                cur_test_status = TestStatus.SUCCESS

            num_tests_run += 1
            timer["end"] = time.time()

            try:
                if "skip_validate" not in test or not test["skip_validate"]:
                    run_validate(config, test["id"])
                run_pre_post_commands(
                    "post_test",
                    [test, test_control_config, mongodb_setup_config],
                    config,
                    EXCEPTION_BEHAVIOR.CONTINUE,
                    test["id"],
                )
            except:  # pylint: disable=bare-except
                # The post test activities failing implies the test failing.
                LOG.error("Post-test activities failed after test %s.", test["id"], exc_info=1)

                # Don't "downgrade" from ERROR to FAILED.
                if cur_test_status != TestStatus.ERROR:
                    cur_test_status = TestStatus.FAILED

            if cur_test_status == TestStatus.FAILED:
                num_tests_failed += 1
                LOG.warning("Unsuccessful test run for test %s. Parsing results now", test["id"])
            elif cur_test_status == TestStatus.ERROR:
                LOG.warning("Unknown error in test %s, exiting early.", test["id"])
                break
            else:
                LOG.info("Successful test run for test %s. Parsing results now", test["id"])

            _, cedar_tests = parse_test_results(test, config, timer)
            for cedar_test in cedar_tests:
                report.add_test(cedar_test)
    except Exception as e:  # pylint: disable=broad-except
        LOG.error("Unexcepted exception: %s", repr(e), exc_info=1)
    finally:
        # Save exit codes for analysis.py
        config.save()
        run_pre_post_commands(
            "post_task",
            [test_control_config, mongodb_setup_config],
            config,
            EXCEPTION_BEHAVIOR.CONTINUE,
        )
        perf_json = config["test_control"]["perf_json"]["path"]
        copy_to_reports(reports_dir="reports", perf_json=perf_json)
        # Print perf.json to screen
        print_perf_json(filename=perf_json)
        # Cedar
        cedar.send(report, config)

    LOG.info("%s of %s tests exited with an error.", num_tests_failed, num_tests_run)

    # Return True if all tests failed or if the last test errored.
    return (num_tests_run == num_tests_failed) or (cur_test_status == TestStatus.ERROR)


def validate_config(config):
    """
    Validate that the given config only includes test types that are supported by a parser.

    The motivation for this method is that result parsing happens at the end of a test, when time
    and money was already spent running the test. If a parser is not found to process the test
    result, they will not be recorded to Evergreen and a user will have to manually search for them
    from the log file. (It's also possible nobody will notice some results are missing. To fail
    early, test_control.py can call this method up front, to validate that all test types are
    supported.

    :param ConfigDict config: A full ConfigDict
    """
    for test in config["test_control"]["run"]:
        if not test["type"] in get_supported_parser_types():
            raise NotImplementedError("No parser exists for test type {}".format(test["type"]))


def main(argv):
    """ Main function. Parse command line options, and run tests.

    :returns: int the exit status to return to the caller (0 for OK)
    """
    parser = argparse.ArgumentParser(description="DSI Test runner")

    parser.add_argument("-d", "--debug", action="store_true", help="enable debug output")
    parser.add_argument("--log-file", help="path to log file")
    args = parser.parse_args(argv)
    log.setup_logging(args.debug, args.log_file)

    config = ConfigDict("test_control")
    config.load()

    error = run_tests(config)
    return 1 if error else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
