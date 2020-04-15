"""
Unit tests for `setup_baselines.py`.
"""

import textwrap
import unittest

from dsi import setup_baselines
from test_lib.fixture_files import FixtureFiles

FIXTURE_FILES = FixtureFiles()


class BaselineUpdaterTest(setup_baselines.BaselineUpdater):
    """ Subclassed BaselineUpdater to use different baseline_config.yml file

    All tests for BaselineUpdater should use this class instead"""

    def __init__(self):
        """ init. Load different file than parent """
        super(BaselineUpdaterTest, self).__init__()
        self.config = FIXTURE_FILES.load_yaml_file("baseline_config.yml")


class TestSetupBaselines(unittest.TestCase):
    """ Test suite for setup_baselines.py"""

    def setUp(self):
        """
        Setup perfyaml for each test, and patch the file open of baseline_config.yml
        """
        self.perfyaml = FIXTURE_FILES.load_yaml_file("perf.yml")
        self.sysperfyaml = FIXTURE_FILES.load_yaml_file("system_perf.yml")

    def test_patch_sysperf_mongod_link(self):
        """
        Test patch_sysperf_mongod_link
        """
        # pylint: disable=line-too-long
        input_object = {
            "tasks": [],
            "functions": {
                "prepare environment": [
                    {
                        "command": "shell.exec",
                        "params": {
                            "script": """
                                            rm -rf ./*
                                            mkdir src
                                            mkdir work
                                            mkdir bin
                                            pwd
                                            ls"""
                        },
                    },
                    {"command": "manifest.load"},
                    {
                        "command": "git.get_project",
                        "params": {"directory": "src", "revisions": "shortened"},
                    },
                    {
                        "command": "shell.exec",
                        "params": {
                            "working_dir": "work",
                            "script": """
                                         cat > bootstrap.yml <<EOF
                                         # compositions of expansions
                                         # Use 3.4.1 for noise tests
                                         mongodb_binary_archive: "https://s3.amazonaws.com/mciuploads/dsi-v3.4/sys_perf_3.4_5e103c4f5583e2566a45d740225dc250baacfbd7/5e103c4f5583e2566a45d740225dc250baacfbd7/linux/mongod-sys_perf_3.4_5e103c4f5583e2566a45d740225dc250baacfbd7.tar.gz"
                                         EOF
                                         """,
                        },
                    },
                    {"command": "shell.exec"},
                ]
            },
        }
        output_yaml = setup_baselines.patch_sysperf_mongod_link(input_object, "test_link")
        script = output_yaml["functions"]["prepare environment"][3]["params"]["script"]
        script = textwrap.dedent(script)
        expected = textwrap.dedent(
            """
        cat > bootstrap.yml <<EOF
        # compositions of expansions
        # Use 3.4.1 for noise tests
        mongodb_binary_archive: test_link
        EOF
        """
        )
        print(expected)
        print(script)
        self.assertEqual(script, expected)

    def test_get_base_version(self):
        """
        Test get_base_version
        """

        self.assertEqual(setup_baselines.get_base_version("3.2.1"), "3.2")
        self.assertEqual(setup_baselines.get_base_version("3.2"), "3.2")
        self.assertEqual(setup_baselines.get_base_version("3.4.2"), "3.4")

    def test_patch_flags(self):
        """
        Test patch_perf_yaml_mongod_flags
        """

        updater = BaselineUpdaterTest()
        unchanged = updater.patch_perf_yaml_mongod_flags(self.perfyaml, "3.4.0")
        self.assertEqual(self.perfyaml, unchanged, "No changes to mongod flags for 3.4.0")
        modified = updater.patch_perf_yaml_mongod_flags(self.perfyaml, "3.0.12")
        reference = FIXTURE_FILES.load_yaml_file("perf.yml.modified.mongodflags.ok")
        self.assertEqual(modified, reference, "Remove inMemory and diagnostic parameters for 3.0")

    def test_patch_raise(self):
        """
        Test that patch_perf_yaml raises if given version it doesn't know
        """
        updater = BaselineUpdaterTest()
        with self.assertRaises(setup_baselines.UnsupportedBaselineError):
            updater.patch_perf_yaml(self.perfyaml, "1.6.0", "performance")

    def test_patch_sysperf_yaml(self):
        """
        Test the patch_perf_yaml method on BaselineUpdater
        """
        updater = BaselineUpdaterTest()

        modified = updater.patch_sysperf_yaml(self.sysperfyaml, "3.2.12")
        reference = FIXTURE_FILES.load_yaml_file("system_perf.yml.master.3.2.12.ok")
        self.assertEqual(modified, reference, "Patch for 3.2.12 on master")
        modified = updater.patch_sysperf_yaml(self.sysperfyaml, "3.4.2")
        reference = FIXTURE_FILES.load_yaml_file("system_perf.yml.master.3.4.2.ok")
        self.assertEqual(modified, reference, "Patch for 3.4.2 on master")

    def test_repeated_args(self):
        """ Test format_repeated_args
        """

        tasks = setup_baselines.format_repeated_args("-t", ["task1", "task2", "task3"])
        self.assertEqual(tasks, ["-t", "task1", "-t", "task2", "-t", "task3"], "format tasks")
        variants = setup_baselines.format_repeated_args("-v", ["variantA", "variantB"])
        self.assertEqual(variants, ["-v", "variantA", "-v", "variantB"], "format variants")

    def test_get_tasks(self):
        """ Test get_tasks
        """

        updater = setup_baselines.BaselineUpdater()
        # This test removes the views tasks
        tasks = updater.get_tasks(self.perfyaml, "3.2")
        reference = [
            "compile",
            "query",
            "where",
            "update",
            "insert",
            "geo",
            "misc",
            "singleThreaded",
            "singleThreaded-wt-repl-comp",
            "insert-wt-repl-comp",
            "update-wt-repl-comp",
            "misc-wt-repl-comp",
            "singleThreaded-mmap-repl-comp",
            "insert-mmap-repl-comp",
            "update-mmap-repl-comp",
            "misc-mmap-repl-comp",
            "aggregation",
        ]
        self.assertEqual(tasks, reference)
        tasks = updater.get_tasks(self.perfyaml, "3.4")
        reference = [
            "compile",
            "query",
            "views-query",
            "views-aggregation",
            "where",
            "update",
            "insert",
            "geo",
            "misc",
            "singleThreaded",
            "singleThreaded-wt-repl-comp",
            "insert-wt-repl-comp",
            "update-wt-repl-comp",
            "misc-wt-repl-comp",
            "singleThreaded-mmap-repl-comp",
            "insert-mmap-repl-comp",
            "update-mmap-repl-comp",
            "misc-mmap-repl-comp",
            "aggregation",
        ]
        self.assertEqual(tasks, reference)

    def test_get_variants(self):
        """ Test get_variants
            """

        variants = setup_baselines.get_variants(self.perfyaml)
        reference = [
            "linux-wt-standalone",
            "linux-mmap-standalone",
            "linux-wt-repl",
            "linux-mmap-repl",
            "linux-wt-repl-compare",
            "linux-mmap-repl-compare",
        ]
        self.assertEqual(variants, reference)

    def test_prepare_patch(self):
        """ Test prepare_patch

        """

        updater = setup_baselines.BaselineUpdater()
        cmd_args = updater.prepare_patch_cmd(self.perfyaml, "3.2.11", "performance")
        reference = [
            "patch",
            "-p",
            "performance",
            "-d",
            "3.2.11 baseline for project performance",
            "-y",
            "-v",
            "linux-wt-standalone",
            "-v",
            "linux-mmap-standalone",
            "-v",
            "linux-wt-repl",
            "-v",
            "linux-mmap-repl",
            "-v",
            "linux-wt-repl-compare",
            "-v",
            "linux-mmap-repl-compare",
            "-t",
            "query",
            "-t",
            "where",
            "-t",
            "update",
            "-t",
            "insert",
            "-t",
            "geo",
            "-t",
            "misc",
            "-t",
            "singleThreaded",
            "-t",
            "singleThreaded-wt-repl-comp",
            "-t",
            "insert-wt-repl-comp",
            "-t",
            "update-wt-repl-comp",
            "-t",
            "misc-wt-repl-comp",
            "-t",
            "singleThreaded-mmap-repl-comp",
            "-t",
            "insert-mmap-repl-comp",
            "-t",
            "update-mmap-repl-comp",
            "-t",
            "misc-mmap-repl-comp",
            "-t",
            "aggregation",
        ]
        # The first entry is the evergreen binary. Remove that.
        self.assertEqual(cmd_args[1:], reference, "arguments to evergreen Popen call for 3.2.11")
        cmd_args = updater.prepare_patch_cmd(self.perfyaml, "3.4.1", "performance")
        reference = [
            "patch",
            "-p",
            "performance",
            "-d",
            "3.4.1 baseline for project performance",
            "-y",
            "-v",
            "linux-wt-standalone",
            "-v",
            "linux-mmap-standalone",
            "-v",
            "linux-wt-repl",
            "-v",
            "linux-mmap-repl",
            "-v",
            "linux-wt-repl-compare",
            "-v",
            "linux-mmap-repl-compare",
            "-t",
            "query",
            "-t",
            "views-query",
            "-t",
            "views-aggregation",
            "-t",
            "where",
            "-t",
            "update",
            "-t",
            "insert",
            "-t",
            "geo",
            "-t",
            "misc",
            "-t",
            "singleThreaded",
            "-t",
            "singleThreaded-wt-repl-comp",
            "-t",
            "insert-wt-repl-comp",
            "-t",
            "update-wt-repl-comp",
            "-t",
            "misc-wt-repl-comp",
            "-t",
            "singleThreaded-mmap-repl-comp",
            "-t",
            "insert-mmap-repl-comp",
            "-t",
            "update-mmap-repl-comp",
            "-t",
            "misc-mmap-repl-comp",
            "-t",
            "aggregation",
        ]
        # The first entry is the evergreen binary. Remove that.
        self.assertEqual(cmd_args[1:], reference, "arguments to evergreen Popen call for 3.4.1")


if __name__ == "__main__":
    unittest.main()
