"""
analysis.py plugin: Check exit codes from tests.

Note: This is the DSI 2.0 version of this file. common/ has the DSI 1.0 version of doing the same.
"""


import structlog

from dsi.common import canaries

LOG = structlog.get_logger(__name__)

EXIT_STATUS_OK = 0
""" This code indicates that the command did not return an error """

EXIT_STATUS_ERR = 1
""" This code indicates that the command returned an error, although it is not specific """


def exit(config, results):
    """
    analysis.py plugin: Check exit statuses of all test executions.

    :param ConfigDict config: The global config.
    :param ResultsFile results: Object to add results to.
    """
    LOG.info("Checking exit codes.")
    run = config["test_control"]["run"]
    run.extend(canaries.get_canaries(config))
    exit_codes = config["test_control"]["out"]["exit_codes"]
    # We want to check that all tests actually ran. So start by iterating over test_control.run
    for test in run:
        # Then check exit_codes in test_control.out for all of them
        exit = exit_codes.get(test["id"])
        if exit is None:
            message = "No exit code found in test_control.out.exit_codes for test. Did it not run?"
            # Not using LOG.error() because there's no error in THIS code, even if some test result
            # is missing.
            LOG.warning(message, test_id=test["id"])
            results.add(test["id"], "fail", exit_code=EXIT_STATUS_ERR, log_raw=message)
        else:
            passfail = "pass" if exit["status"] == 0 else "fail"
            LOG.debug("Found exit_code for test", test_id=test["id"], exit_code=exit["status"])
            results.add(test["id"], passfail, exit_code=exit["status"], log_raw=exit["message"])
