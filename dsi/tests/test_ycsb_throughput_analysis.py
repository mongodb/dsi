"""Unit tests for `ycsb_throughput_analysis.py`."""


import unittest
from os import path

from six.moves import range
from six.moves import zip

from dsi.libanalysis import ycsb_throughput_analysis as ycsb_throughput
from test_lib.fixture_files import FixtureFiles

FIXTURE_FILES = FixtureFiles()


def tuples_to_throughputs(time_ops_tuples):
    """Convert a list of (time, num_ops) tuples to a list of `ycsb_throughput.Throughput`s."""

    return [ycsb_throughput.Throughput(*pair) for pair in time_ops_tuples]


class TestYCSBThroughputAnalysis(unittest.TestCase):
    """Test suite."""

    def test_get_ycsb_file_paths(self):
        """Test `_get_ycsb_file_paths()`."""

        reports_dir = FIXTURE_FILES.fixture_file_path("analysis/test_ycsb_throughput_analysis")
        actual_paths = ycsb_throughput._get_ycsb_file_paths(reports_dir)
        expected_files = [
            "dir2/test_output.log",
            "dir1/test_output.log",
            "dir3/dir4/test_output.log",
            "dir3/test_output.log",
        ]
        expected_paths = [path.join(reports_dir, "ycsb-run", fname) for fname in expected_files]
        self.assertEqual(set(actual_paths), set(expected_paths))

    def test_throughputs_from_lines(self):
        """Test `_throughputs_from_lines()`."""

        lines = [
            "not a stats line",
            " totally bad line",
            " 0 sec: 0 operations;",
            " 10 sec: 1033330 operations; 103209.15 current ops/sec; [something];;;;",
            " 20 sec: 2357178 operations; 132371.56 current ops/sec; junk data",
            "not a stats line",
            " 30 sec: 3688285 operations; 133097.39 current ops/sec;",
            " 40 sec: 5021949 operations; 133353.06 current ops/sec;",
            " 50 sec: 6355297 operations; 133321.47 current ops/sec;",
        ]

        actual_throughputs = ycsb_throughput._throughputs_from_lines(lines)
        expected_throughputs = [
            (10.0, 103209.15),
            (20.0, 132371.56),
            (30.0, 133097.39),
            (40.0, 133353.06),
            (50.0, 133321.47),
        ]
        self.assertEqual(actual_throughputs, expected_throughputs)

    def test_analyze_spiky_throughput(self):
        """Test `_analyze_spiky_throughput()`."""

        def analyze(*args, **kwargs):
            """Convenience function to reduce boilerplate when calling `_analyze_throughputs()`."""

            messages = ycsb_throughput._analyze_spiky_throughput(throughputs, *args, **kwargs)
            return not messages

        throughputs = tuples_to_throughputs([(0, 20), (10, 0), (20, 0), (30, 20)])
        self.assertFalse(analyze(min_duration=10, skip_initial_seconds=-1))
        self.assertTrue(analyze(min_duration=20, skip_initial_seconds=-1))
        self.assertTrue(analyze(min_duration=30, skip_initial_seconds=-1))

        throughputs = tuples_to_throughputs([(0, 10), (10, 5), (20, 5), (30, 10)])
        self.assertFalse(analyze(max_drop=0.8, min_duration=10, skip_initial_seconds=-1))
        self.assertTrue(analyze(max_drop=0.4, min_duration=10, skip_initial_seconds=-1))

        throughputs = tuples_to_throughputs(
            [(0, 0), (5, 0), (10, 0), (20, 0), (30, 100), (40, 100)]
        )
        self.assertTrue(analyze(max_drop=0.9, min_duration=5, skip_initial_seconds=20))
        self.assertFalse(analyze(max_drop=0.9, min_duration=1, skip_initial_seconds=5))

    def test_analyze_long_term(self):
        """Test `_analyze_long_term_degradation().`"""

        def analyze(*args, **kwargs):
            """Convenience function to reduce boilerplate."""

            results = ycsb_throughput._analyze_long_term_degradation(throughputs, *args, **kwargs)
            return not results

        throughputs = tuples_to_throughputs(
            [(time, 10) for time in range(600)] + [(time, 5) for time in range(601, 20 * 60 + 3)]
        )
        self.assertFalse(analyze(), "Detects long-term throughput degradation")
        self.assertTrue(
            analyze(duration_seconds=10 * 100),
            "Ignores degradation shorter than `duration_seconds`",
        )
        self.assertTrue(analyze(max_drop=0.3), "Ignores degradation higher than `max_drop`")
        self.assertTrue(analyze(max_drop=0.4), "Ignores degradation higher than `max_drop`")
        self.assertFalse(analyze(max_drop=0.51), "Flags degradation lower than `max_drop`")

        times = list(range(10 * 79))
        ops = [100] * (10 * 60) + [0] * (10 * 19)
        throughputs = tuples_to_throughputs(list(zip(times, ops)))
        # With a 600 second period, the max average throughput is 100,
        # and the last window has an average just under 70.
        self.assertFalse(analyze())
        # With a 700 second period, the max period troughput is < 100,
        # and the last window has an average over 70
        self.assertTrue(analyze(duration_seconds=10 * 70))
