"""
Unit test for infrastructure_teardown.py
"""


import logging
import os
import unittest

from mock import patch, call, MagicMock
from testfixtures import LogCapture

from dsi.common import whereami
from dsi import infrastructure_teardown


class TestInfrastructureTeardown(unittest.TestCase):
    """ Test suite for infrastructure_teardown.py """

    @patch("dsi.infrastructure_teardown.glob.glob")
    @patch("dsi.infrastructure_teardown.os")
    @patch("dsi.infrastructure_teardown.find_terraform")
    def test_destroy_resources_no_cluster_json(self, mock_find_terraform, mock_os, mock_glob):
        """ Test infrastructure_teardown.destroy_resources when there is no cluster.json file """
        mock_os.path.dirname.return_value = "teardown/script/path"
        mock_os.getcwd.return_value = "previous/directory"
        mock_os.path.isfile.return_value = False
        mock_glob.return_value = True
        mock_find_terraform.return_value = "test/path/terraform"

        with LogCapture(level=logging.CRITICAL) as critical:
            with self.assertRaises(UserWarning):
                infrastructure_teardown.destroy_resources()

            critical.check(
                (
                    "dsi.infrastructure_teardown",
                    "CRITICAL",
                    "In infrastructure_teardown.py and cluster.json does not exist. Giving up.",
                )
            )
        mock_glob.assert_called_with(os.path.join(whereami.dsi_repo_path("dsi"), "provisioned.*"))
        chdir_calls = [call(whereami.dsi_repo_path("dsi")), call("previous/directory")]
        mock_os.chdir.assert_has_calls(chdir_calls)
        mock_os.path.isfile.assert_called_with("cluster.json")

    @patch("dsi.common.atlas_setup.AtlasSetup")
    def test_destroy_atlas_resources(self, mock_atlas_setup):
        mock_atlas = MagicMock(name="atlas", autospec=True)
        mock_atlas_setup.return_value = mock_atlas

        infrastructure_teardown.destroy_atlas_resources()

        mock_atlas_setup.assert_called()
        mock_atlas.destroy.assert_called()


if __name__ == "__main__":
    unittest.main()
