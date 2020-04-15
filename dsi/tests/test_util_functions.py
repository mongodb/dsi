"""Unit tests for utility functions in analysis/util.py. Run using nosetests."""


import datetime
import unittest

from dsi.libanalysis import util


class TestUtilFunctions(unittest.TestCase):
    """Test suite."""

    def test_num_or_str_to_date(self):
        """Test `num_or_str_to_date()`."""

        self.assertIsInstance(util.num_or_str_to_date(1), datetime.datetime)
        parsed_date = util.num_or_str_to_date("2016-07-14T03:25:00.000+0000")
        self.assertIsInstance(parsed_date, datetime.datetime)

    def test_get_test_times(self):
        """Test `get_test_times()`."""

        def assert_instancesof_datetime(tuples):
            """
            Assert that all of the items in a list of tuples are instanced of
            `datetime.datetime`.
            """
            for pair in tuples:
                for item in pair:
                    self.assertIsInstance(item, datetime.datetime)

        perf_json = {
            "results": [],
            "start": "2016-07-14T03:25:00.000+0000",
            "end": "2016-07-14T03:24:00.000+0000",
        }
        times = util.get_test_times(perf_json)
        self.assertEqual(len(times), 1)
        assert_instancesof_datetime(times)
        perf_json = {
            "results": [
                {"start": 1, "end": 2},
                {"start": 3, "end": 4},
                {"start": 5, "end": "2016-07-14T03:24:00.000+0000"},
            ]
        }
        times = util.get_test_times(perf_json)
        self.assertEqual(len(times), 3)
        assert_instancesof_datetime(times)
