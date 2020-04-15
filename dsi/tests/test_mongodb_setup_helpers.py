"""Tests for the mongodb_setup_helpers module"""


import unittest

from dsi.common import mongodb_setup_helpers


class TestHelperFunctions(unittest.TestCase):
    """Basic tests for helper functions in mongodb_setup"""

    def test_merge_dicts(self):
        """Test merge_dicts correctly overrides literals."""
        base = {"a": 1, "b": "string"}
        override = {"b": 2, "c": 3}
        expected_merge = {"a": 1, "b": 2, "c": 3}
        self.assertEqual(mongodb_setup_helpers.merge_dicts(base, override), expected_merge)

    def test_merge_dicts_nested(self):
        """Test merge_dicts correctly overrides dictionaries."""
        base = {"a": 1, "b": "string", "setParameters": {"a": 1, "b": "string"}}
        override = {"b": 2, "c": 3, "setParameters": {"b": 2, "c": 3}}
        expected_merge = {"a": 1, "b": 2, "c": 3, "setParameters": {"a": 1, "b": 2, "c": 3}}
        self.assertEqual(mongodb_setup_helpers.merge_dicts(base, override), expected_merge)

    def test_mongodb_auth_settings_enabled(self):
        config = {
            "mongodb_setup": {
                "authentication": {"enabled": True, "username": "username", "password": "password"}
            }
        }
        self.assertEqual(
            mongodb_setup_helpers.mongodb_auth_settings(config),
            mongodb_setup_helpers.MongoDBAuthSettings("username", "password"),
        )

    def test_mongodb_auth_settings_missing(self):
        config = {"mongodb_setup": {}}
        with self.assertRaises(KeyError):
            self.assertEqual(mongodb_setup_helpers.mongodb_auth_settings(config), None)

    def test_mongodb_auth_settings_missing_2(self):
        config = {"mongodb_setup": {"authentication": {}}}
        with self.assertRaises(KeyError):
            self.assertEqual(mongodb_setup_helpers.mongodb_auth_settings(config), None)
