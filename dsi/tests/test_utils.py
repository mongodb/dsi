"""
Unit tests for dsi/common/utils.py
"""

import os
import unittest

from mock import patch

from dsi.common import utils
from dsi.common import whereami


class TestUtils(unittest.TestCase):
    """
    Test suite for utils.py
    """

    def setUp(self):
        self.test_cred_path = os.path.join(whereami.dsi_repo_path("dsi", "tests"), "creds")
        with open(self.test_cred_path, "w") as test_cred_file:
            test_cred_file.write(
                "[default]\naws_access_key_id = "
                "test_aws_access_key1\naws_secret_access_key = "
                "test_aws_secret_key1"
            )

    def tearDown(self):
        os.remove(self.test_cred_path)

    @patch("dsi.common.utils.read_aws_credentials_file")
    @patch("dsi.common.utils.read_env_vars")
    def test_read_aws_credentials_fails(self, mock_read_env_vars, mock_read_aws_credentials_file):
        """
        Testing that read_aws_credentials fails correctly when it cannot find AWS keys
        """
        config = {}
        with self.assertRaises(AssertionError):
            utils.read_aws_credentials(config)
        mock_read_env_vars.assert_called()
        mock_read_aws_credentials_file.assert_called()
        config = {"runtime_secret": {"aws_access_key": "test_key"}}
        mock_read_env_vars.assert_called()
        mock_read_aws_credentials_file.assert_called()
        with self.assertRaises(AssertionError):
            utils.read_aws_credentials(config)
        config = {"runtime_secret": {"aws_secret_key": "test_secret"}}
        mock_read_env_vars.assert_called()
        mock_read_aws_credentials_file.assert_called()
        with self.assertRaises(AssertionError):
            utils.read_aws_credentials(config)

    @patch("os.path.expanduser")
    def test_read_aws_credentials_runtime_secret(self, mock_expanduser):
        """
        Testing that read_aws_credentials applies runtime_secret AWS keys
        """
        mock_expanduser.return_value = self.test_cred_path
        config = {
            "runtime_secret": {"aws_access_key": "test_key2", "aws_secret_key": "test_secret2"}
        }
        self.assertEqual(utils.read_aws_credentials(config), ("test_key2", "test_secret2"))

    @patch("os.path.expanduser")
    def test_read_aws_credentials_file(self, mock_expanduser):
        """
        Testing read_aws_creds method correctly modifies config
        """
        mock_expanduser.return_value = self.test_cred_path
        test_config = {}
        utils.read_aws_credentials_file(test_config)
        expected_config = {
            "aws_access_key": "test_aws_access_key1",
            "aws_secret_key": "test_aws_secret_key1",
        }
        self.assertEqual(test_config, expected_config)

    @patch("os.path.expanduser")
    def test_read_aws_creds_file_and_env_vars(self, mock_expanduser):
        """
        Testing read_aws_creds and read_env_vars simultaneously
        """
        mock_expanduser.return_value = self.test_cred_path
        test_dict = {
            "AWS_ACCESS_KEY_ID": "test_aws_access_key2",
            "AWS_SECRET_ACCESS_KEY": "test_aws_secret_key2",
        }
        test_config = {}
        with patch.dict("os.environ", test_dict):
            utils.read_aws_credentials_file(test_config)
            utils.read_env_vars(test_config)
        expected_config = {
            "aws_access_key": "test_aws_access_key2",
            "aws_secret_key": "test_aws_secret_key2",
        }
        self.assertEqual(test_config, expected_config)

    def test_read_env_vars(self):
        """
        Testing read_env_vars method correctly modifies config
        """
        expected_config = {
            "aws_access_key": "test_aws_access_key",
            "aws_secret_key": "test_aws_secret_key",
        }
        test_config = {}
        test_dict = {
            "AWS_ACCESS_KEY_ID": "test_aws_access_key",
            "AWS_SECRET_ACCESS_KEY": "test_aws_secret_key",
        }
        with patch.dict("os.environ", test_dict):
            utils.read_env_vars(test_config)
        self.assertEqual(test_config, expected_config)
