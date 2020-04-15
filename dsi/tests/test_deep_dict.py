"""Unit tests for util/multi_analysis.py"""


import unittest

from dsi.common import deep_dict


class TestDeepDict(unittest.TestCase):
    """
    Test the deep_dict utility functions.
    """

    def test_deep_dict_iterate(self):
        """deep_dict.iterate()"""
        data = {
            "a": {"aa": {"aaa": 1, "aab": 2}, "ab": {"aba": 3, "abb": 4}},
            "b": {"ba": {"baa": 5, "bab": 6}, "bb": {"bba": 7, "bbb": 8}},
        }
        expected = [
            (["a", "aa", "aaa"], 1),
            (["a", "aa", "aab"], 2),
            (["a", "ab", "aba"], 3),
            (["a", "ab", "abb"], 4),
            (["b", "ba", "baa"], 5),
            (["b", "ba", "bab"], 6),
            (["b", "bb", "bba"], 7),
            (["b", "bb", "bbb"], 8),
        ]

        self.assertEqual(deep_dict.iterate(data), expected)

    def test_deep_dict_get(self):
        """deep_dict.get_value()"""
        data = {
            "a": {"aa": {"aaa": 1, "aab": 2}, "ab": {"aba": 3, "abb": 4}},
            "b": {"ba": {"baa": 5, "bab": 6}, "bb": {"bba": 7, "bbb": 8}},
        }

        self.assertEqual(deep_dict.get_value(data, ["a", "aa", "aab"]), 2)

    def test_deep_dict_set(self):
        """deep_dict.set_value()"""
        data = {
            "a": {"aa": {"aaa": 1, "aab": 2}, "ab": {"aba": 3, "abb": 4}},
            "b": {"ba": {"baa": 5, "bab": 6}, "bb": {"bba": 7, "bbb": 8}},
        }
        deep_dict.set_value(data, ["a", "aa", "aab"], 999)
        self.assertEqual(deep_dict.get_value(data, ["a", "aa", "aab"]), 999)

    def test_deep_dict_del(self):
        """deep_dict.del_value()"""
        data = {
            "a": {"aa": {"aaa": 1, "aab": 2}, "ab": {"aba": 3, "abb": 4}},
            "b": {"ba": {"baa": 5, "bab": 6}, "bb": {"bba": 7, "bbb": 8}},
        }
        expected = {
            "a": {"aa": {"aaa": 1}, "ab": {"aba": 3, "abb": 4}},
            "b": {"ba": {"baa": 5, "bab": 6}, "bb": {"bba": 7, "bbb": 8}},
        }

        deep_dict.del_value(data, ["a", "aa", "aab"])
        self.assertEqual(data, expected)

        with self.assertRaises(KeyError):
            deep_dict.del_value(data, ["a", "foo"])


if __name__ == "__main__":
    unittest.main()
