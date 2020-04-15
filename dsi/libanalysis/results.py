"""
Class for reading and writing results.json.
"""


import json
import os.path
import re

import six
import structlog

LOG = structlog.get_logger(__name__)


class ResultsFile:
    """
    Class for reading and writing results.json.
    """

    def __init__(self, config):
        """
        :param ConfigDict config: The global configuration.
        """
        self.config = config
        self.data = self.read()
        self.results_json = config["analysis"]["results_json"]["path"]

    def read(self):
        """
        Return the initial results.json as dictionary.

        Depending on what mode is configured, start with a new, empty dict, or read the existing
        file and then we add to it.
        :return: A dict with results.json contents, or empty, depending on config.
        """
        empty = {"failures": 0, "results": []}
        mode = self.config["analysis"]["results_json"]["mode"]
        if mode == "overwrite":
            return empty

        if mode == "append":
            if os.path.isfile(self.results_json):
                with open(self.results_json) as results_file:
                    LOG.info("Read results file.", file_name=self.results_json)
                    return json.load(results_file)
            else:
                return empty

        raise ValueError(
            "analysis.results_json.mode configuration is not supported.",
            allowed_modes=["overwrite", "append"],
            actual_mode=mode,
        )

    def write(self):
        """
        Write the results.json file.
        """
        num_failures = self.count_failures()
        with open(self.results_json, "w") as results_file:
            json.dump(self.data, results_file, indent=4, separators=(",", ": "))
            LOG.info("Wrote results file.", file_name=self.results_json)
        return num_failures

    def count_failures(self):
        """
        Set the 'failures' field, but don't count quarantined rules.
        """
        num_failures = 0
        quarantined_rules = self.config["analysis"]["rules"].get("quarantined_rules", [])
        for test_result in self.data["results"]:
            match_on_rule = any(
                re.match(rule_regex, test_result["test_file"]) for rule_regex in quarantined_rules
            )
            if test_result["status"] == "fail" and not match_on_rule:
                num_failures += 1
        self.data["failures"] = num_failures
        return num_failures

    def add(self, test_file, status, start=0, end=0, log_raw="", exit_code=0, **kwargs):
        """
        Add one result object.

        Example:

            {
                "status": "pass",
                "start": 1568389018.380075,
                "PreviousCompare": "pass",
                "end": 1568389219.03819,
                "test_file": "canary_client-cpuloop-1x",
                "log_raw": "\nTest: canary_client-cpuloop-1x\n   Rule   |  State   |  Compared_to  |
                Thread |  Target   | Achieved  | delta(%)  |threshold(%)\n----------+----------+----
                -----------+-------+-----------+-----------+-----------+------------\n Previous |  
                Passed  |    e2de2b2    |  max  | 1177784.71| 1751880.97|     48.74%|     20.00%|\n 
                Previous |  Passed  |    e2de2b2    |   1   |  118197.03|  122975.63|      4.04%|   
                30.00%|\n Previous |  Passed  |    e2de2b2    |   8   |  935427.27|  964329.56|     
                3.09%|     30.00%|\n Previous |  Passed  |    e2de2b2    |   4   |  471669.61|  
                484788.52|      2.78%|     30.00%|\n Previous |  Passed  |    e2de2b2    |  16   | 
                1177784.71| 1751880.97|     48.74%|     30.00%|\n",
                "exit_code": 0
            }

        :param str test_file: In DSI, this is not a file, but a unique identifier for the test or
                              other check that passed or failed.
        :param str status:    pass or fail
        :param int start:     Unix timestamp when test started.
        :param int end:       Unix timestamp when test ended.
        :param str log_raw:   Arbitrary text string.
        :param int exit_code: Exit code of the test execution. (0 for pass)
        """
        assert status in ("pass", "fail")
        if status == "pass":
            assert exit_code == 0, "exit_code must be 0 if test/check passed"
        elif status == "fail":
            assert exit_code != 0, "exit_code must be non-zero if test/check failed"
        new_result = {
            "test_file": test_file,
            "status": status,
            "start": start,
            "end": end,
            "log_raw": log_raw,
            "exit_code": exit_code,
        }
        for key, value in six.iteritems(kwargs):
            new_result[key] = value
        self.data["results"].append(new_result)
        # if status == 'fail':
        # self.data['failures'] = self.data['failures'] + 1

    def extend(self, results):
        """
        Add results to self.data directly.

        Note that DSI 1.0 code writes its own results objects and we just accept them as they are here. Think of this method as:

            self.extend([self.add(), self.add()])

        :param list results: A list of results, ready to be written.
        """
        if isinstance(results, list):
            self.data["results"].extend(results)
        elif isinstance(results, dict):
            self.data["results"].append(results)
        else:
            LOG.error("Results must be a list or dict.", results=results)
            raise ValueError("Results must be a list or dict.")
