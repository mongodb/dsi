"""Unit tests for `log_analysis.py`."""


import unittest
from os import path

from dsi.libanalysis import log_analysis
from test_lib.fixture_files import FixtureFiles

FIXTURE_FILES = FixtureFiles()


class TestLogAnalysis(unittest.TestCase):
    """Test suite."""

    def test_get_log_file_paths(self):
        """Test `_get_bad_log_lines()`."""

        log_dir = FIXTURE_FILES.fixture_file_path("analysis", "test_log_analysis")
        expected_paths = set(
            [
                path.join(log_dir, "log_subdir1/mongod.log"),
                path.join(log_dir, "log_subdir2/log_subsubdir/mongod.log"),
            ]
        )
        actual_paths = set(log_analysis._get_log_file_paths(log_dir))
        self.assertEqual(expected_paths, actual_paths)
