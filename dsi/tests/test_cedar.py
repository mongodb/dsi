"""
Unit tests for 'cedar.py'.
"""

import copy
import json
import os
import unittest

from mock import patch, MagicMock, call

from dsi.common import cedar


class TestCedar(unittest.TestCase):
    BASE_EXPECT = {
        "bucket": {
            "api_key": "",
            "api_secret": "",
            "api_token": "",
            "name": "",
            "prefix": "",
            "region": "",
        },
        "execution_number": 1,
        "mainline": True,
        "project": "Genny",
        "task_id": "2C9TU0UAQ1NBCNG6K15P",
        "task_name": "some_genny_test",
        "tests": [
            {
                "artifacts": [],
                "completed_at": "1972-12-17T22:04:39+00:00",
                "created_at": "2091-08-29T17:46:14+00:00",
                "info": {"args": {}, "tags": [], "test_name": "test34", "trial": 0},
                "metrics": [],
                "sub_tests": [],
            }
        ],
        "variant": "linux-standalone",
        "version": "revHEAD",
        "order": 2,
    }

    BASE_RUNTIME = {
        "build_variant": "linux-standalone",
        "execution": 1,
        "is_patch": False,
        "project": "Genny",
        "task_id": "2C9TU0UAQ1NBCNG6K15P",
        "task_name": "some_genny_test",
        "version_id": "revHEAD",
        "order": "2",
    }

    @staticmethod
    def expected(other=None):
        if other is None:
            other = {}
        out = copy.deepcopy(TestCedar.BASE_EXPECT)
        out.update(other)
        return out

    @staticmethod
    def base_report(other=None):
        if other is None:
            other = {}
        runtime = copy.deepcopy(TestCedar.BASE_RUNTIME)
        runtime.update(other)
        return cedar.Report(runtime)

    def test_simple_serialize(self):
        report = self.base_report()
        cedar_test = cedar.CedarTest("test34", 3839247974, 93477879)
        report.add_test(cedar_test)

        actual = report.as_dict()
        expect = self.expected()
        self.assertDictEqual(actual, expect)

    def test_no_runtime_still_writes_file(self):
        report = cedar.Report(runtime={})
        cedar_test = cedar.CedarTest("test34", 3839247974, 93477879)
        report.add_test(cedar_test)

        try:
            report.write_report()
            with open("cedar_report.json", "r") as written:
                written = json.load(written)
            expect = json.loads(
                "".join(
                    [
                        "{\n",
                        '    "project": null, \n',
                        '    "tests": [\n',
                        "        {\n",
                        '            "info": {\n',
                        '                "trial": 0, \n',
                        '                "tags": [], \n',
                        '                "args": {}, \n',
                        '                "test_name": "test34"\n',
                        "            }, \n",
                        '            "artifacts": [], \n',
                        '            "created_at": "2091-08-29T17:46:14+00:00", \n',
                        '            "metrics": [], \n',
                        '            "completed_at": "1972-12-17T22:04:39+00:00", \n',
                        '            "sub_tests": []\n',
                        "        }\n",
                        "    ], \n",
                        '    "version": null, \n',
                        '    "task_id": null, \n',
                        '    "task_name": null, \n',
                        '    "bucket": {\n',
                        '        "name": "", \n',
                        '        "api_secret": "", \n',
                        '        "region": "", \n',
                        '        "prefix": "", \n',
                        '        "api_token": "", \n',
                        '        "api_key": ""\n',
                        "    }, \n",
                        '    "variant": null, \n',
                        '    "mainline": false, \n',
                        '"order": null, \n    "execution_number": null\n',
                        "}",
                    ]
                )
            )
            self.assertDictEqual(expect, written)
        finally:
            if os.path.exists("cedar_report.json"):
                os.remove("cedar_report.json")

    def test_with_metrics(self):
        report = self.base_report()

        test = cedar.CedarTest("test12", 3839247974, 93477879)

        test.add_metric("ops", "PERCENTILE_P99", 300, True)
        test.add_tag("one-tag")
        test.add_tag("two-tag")
        test.add_tag("one-tag")  # dupes get removed (set)

        test.set_thread_level(300)
        test.set_argument("foo", 300)

        # overwrites
        test.set_thread_level(150)
        test.set_argument("foo", 150)

        report.add_test(test)

        actual = report.as_dict()

        expect = self.expected(
            {
                "tests": [
                    {
                        "artifacts": [],
                        "completed_at": "1972-12-17T22:04:39+00:00",
                        "created_at": "2091-08-29T17:46:14+00:00",
                        "info": {
                            "args": {"foo": 150, "thread_level": 150},
                            "tags": ["one-tag", "two-tag"],
                            "test_name": "test12",
                            "trial": 0,
                        },
                        "metrics": [
                            {
                                "name": "ops",
                                "type": "PERCENTILE_P99",
                                "user_submitted": True,
                                "value": 300,
                            }
                        ],
                        "sub_tests": [],
                    }
                ]
            }
        )
        self.assertDictEqual(actual, expect)


class TestRunCuratorAndFriends(unittest.TestCase):
    CONFIG = {"runtime_secret": {"perf_jira_user": "test-user", "perf_jira_pw": "test-pwd"}}

    @staticmethod
    def rm_if_exists(path):
        if os.path.exists(path):
            os.remove(path)

    def tearDown(self):
        self.cleanup()

    def setUp(self):
        self.cleanup()

    def cleanup(self):
        TestRunCuratorAndFriends.rm_if_exists("cedar.ca.pem")
        TestRunCuratorAndFriends.rm_if_exists("cedar.user.crt")
        TestRunCuratorAndFriends.rm_if_exists("cedar.user.key")

    @patch("requests.get")
    def test_calls_correct_url(self, mock_get):
        retriever = cedar.CedarRetriever(TestRunCuratorAndFriends.CONFIG)
        mock_get().content = b"mock_text"

        self.assertEqual(retriever.root_ca(), "cedar.ca.pem")
        self.assertEqual(retriever.user_cert(), "cedar.user.crt")
        self.assertEqual(retriever.user_key(), "cedar.user.key")

        mock_get.assert_has_calls(
            [
                call(),
                call("https://cedar.mongodb.com/rest/v1/admin/ca"),
                call().raise_for_status(),
                call(
                    "https://cedar.mongodb.com/rest/v1/admin/users/certificate",
                    data='{"username": "test-user", "password": "test-pwd"}',
                ),
                call().raise_for_status(),
                call(
                    "https://cedar.mongodb.com/rest/v1/admin/users/certificate/key",
                    data='{"username": "test-user", "password": "test-pwd"}',
                ),
                call().raise_for_status(),
            ]
        )
        mock_get().assert_has_calls([call.raise_for_status()])

        # reset and do it again
        mock_get.reset_mock()

        self.assertEqual(retriever.root_ca(), "cedar.ca.pem")
        self.assertEqual(retriever.user_cert(), "cedar.user.crt")
        self.assertEqual(retriever.user_key(), "cedar.user.key")

        mock_get.assert_not_called()

    def test_shell_curator_runner_command_no_bootstrap(self):
        mock_host = MagicMock()
        mock_retriever = MagicMock()
        top_config = copy.deepcopy(TestRunCuratorAndFriends.CONFIG)

        mock_retriever.user_cert.return_value = "mock-cert"
        mock_retriever.user_key.return_value = "mock-cert"
        mock_retriever.root_ca.return_value = "mock-cert"
        mock_retriever.fetch_curator.return_value = "./some-fancy-curator"

        runner = cedar.CuratorRunner(top_config, mock_host, mock_retriever)
        runner.run_curator()

        mock_host.run.assert_has_calls(
            [
                call(
                    [
                        "cd",
                        ".",
                        ";",
                        "./some-fancy-curator",
                        "poplar",
                        "send",
                        "--service",
                        "cedar.mongodb.com:7070",
                        "--cert",
                        "mock-cert",
                        "--key",
                        "mock-cert",
                        "--ca",
                        "mock-cert",
                        "--path",
                        "cedar_report.json",
                    ]
                )
            ]
        )

    def test_shell_curator_runner_command_change_directory(self):
        mock_host = MagicMock()
        mock_retriever = MagicMock()
        top_config = copy.deepcopy(TestRunCuratorAndFriends.CONFIG)

        mock_retriever.user_cert.return_value = "mock-cert"
        mock_retriever.user_key.return_value = "mock-cert"
        mock_retriever.root_ca.return_value = "mock-cert"
        mock_retriever.fetch_curator.return_value = "./some-fancy-curator"

        runner = cedar.CuratorRunner(top_config, mock_host, mock_retriever)
        runner.run_curator("fakedir1/fakedir2/cedar_report.json")

        mock_host.run.assert_has_calls(
            [
                call(
                    [
                        "cd",
                        "fakedir1/fakedir2",
                        ";",
                        "./../../some-fancy-curator",
                        "poplar",
                        "send",
                        "--service",
                        "cedar.mongodb.com:7070",
                        "--cert",
                        "../../mock-cert",
                        "--key",
                        "../../mock-cert",
                        "--ca",
                        "../../mock-cert",
                        "--path",
                        "cedar_report.json",
                    ]
                )
            ]
        )
