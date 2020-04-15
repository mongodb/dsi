"""
Unit tests for analysis.py, the main analysis entry point.
"""


import os
import unittest

from dsi import analysis
from test_lib.fixture_files import FixtureFiles

FIXTURE_FILES = FixtureFiles()


class TestAnalysis(unittest.TestCase):
    def setUp(self):
        self.results_json = os.path.join(
            FIXTURE_FILES.repo_root_file_path(), "results.test_analysis.json"
        )
        self.config = {
            "analysis": {
                "checks": ["dummy"],
                "results_json": {"mode": "overwrite", "path": self.results_json},
                "rules": {},
            }
        }

    def tearDown(self):
        if os.path.exists(self.results_json):
            os.remove(self.results_json)

    def test_results_analyzer(self):
        analyzer = analysis.ResultsAnalyzer(self.config)
        self.assertEqual(analyzer.analyze_all(), 0)
        self.assertEqual(analyzer.failures, 0)
        expected_results = {
            "failures": 0,
            "results": [
                {
                    "end": 2,
                    "exit_code": 0,
                    "log_raw": "Arbitrary text string",
                    "start": 1,
                    "status": "pass",
                    "test_file": "dummy",
                }
            ],
        }
        self.assertEqual(analyzer.results.data, expected_results)

    def test_results_analyzer_failure(self):
        self.config["_test_failures"] = 2
        analyzer = analysis.ResultsAnalyzer(self.config)
        self.assertEqual(analyzer.analyze_all(), self.config["_test_failures"])
        self.assertEqual(analyzer.failures, self.config["_test_failures"])
        self.maxDiff = None  # pylint: disable=invalid-name
        expected_results = {
            "failures": 2,
            "results": [
                {
                    "status": "pass",
                    "end": 2,
                    "log_raw": "Arbitrary text string",
                    "exit_code": 0,
                    "start": 1,
                    "test_file": "dummy",
                },
                {
                    "status": "fail",
                    "end": 4,
                    "log_raw": "This test failed",
                    "exit_code": 1,
                    "start": 3,
                    "test_file": "dummy_fail.1",
                },
                {
                    "status": "fail",
                    "end": 4,
                    "log_raw": "This test failed",
                    "exit_code": 2,
                    "start": 3,
                    "test_file": "dummy_fail.2",
                },
            ],
        }
        self.assertEqual(analyzer.results.data, expected_results)
