"""
Unit test for atlas_setup.py
"""

import copy
import logging
import os
import unittest

from mock import patch, MagicMock, ANY
from testfixtures import LogCapture

import test_lib.structlog_for_test as structlog_for_test
from dsi.common import atlas_setup
from dsi.tests.test_config import load_config_dict
from test_lib.fixture_files import FixtureFiles
from test_lib.io_utils import in_dir

FIXTURE_FILES = FixtureFiles()


class TestAtlasSetup(unittest.TestCase):
    def _cleanup(self):
        for file_path in self.out_files:
            if os.path.exists(file_path):
                os.remove(file_path)

    def setUp(self):
        self.config = None
        self.out_files = []
        self.out_files.append(
            os.path.join(FIXTURE_FILES.fixture_file_path("atlas-config"), "mongodb_setup.out.yml")
        )
        self.out_files.append(
            os.path.join(FIXTURE_FILES.fixture_file_path("atlas-config"), "coverage.xml")
        )
        self.out_files.append(
            os.path.join(
                FIXTURE_FILES.fixture_file_path("atlas-config-custom-build"),
                "mongodb_setup.out.yml",
            )
        )
        self.out_files.append(
            os.path.join(
                FIXTURE_FILES.fixture_file_path("atlas-config-custom-build"), "coverage.xml"
            )
        )
        self._cleanup()
        structlog_for_test.setup_logging()

    def tearDown(self):
        self._cleanup()

    def test_start(self):
        expected_url = (
            "https://cloud-dev.mongodb.com/api/atlas/v1.0/MOCK/URL/groups/test_group_id/clusters"
        )
        with in_dir(FIXTURE_FILES.fixture_file_path("atlas-config")):
            self.config = load_config_dict("mongodb_setup")
            self._test_start(expected_url)

    @patch("dsi.common.atlas_client.AtlasClient.create_custom_build")
    def test_start_custom_build(self, mock_create_custom_build):
        expected_url = (
            "https://cloud.mongodb.com/api/private/MOCK/URL/nds/groups/test_group_id/clusters"
        )
        with in_dir(FIXTURE_FILES.fixture_file_path("atlas-config-custom-build")):
            self.config = load_config_dict("mongodb_setup")
            self._test_start(expected_url)
        mock_create_custom_build.assert_called()

    @patch("dsi.common.atlas_client.AtlasClient.get_one_cluster")
    @patch("dsi.common.atlas_setup.AtlasSetup._generate_unique_name")
    @patch("dsi.common.atlas_setup.AtlasSetup._get_primary")
    @patch("requests.post")
    def _test_start(
        self, expected_url, mock_post, mock_get_primary, mock_generate, mock_get_one_cluster
    ):
        mock_generate.return_value = "mock_unique_name"
        response = MagicMock(name="requests.response", autospec=True)
        response.json.return_value = {"name": "mock_unique_name"}
        mock_post.return_value = response
        mock_get_primary.return_value = ("mock_primary_host", 27017)

        mock_http_return_value = {
            "stateName": "IDLE",
            "name": "mock_unique_name",
            "mongoURI": "mongodb://mock_mongo_uri:27017",
            "mongoURIWithOptions": "mongodb://mock_mongo_uri:27017/?ssl=true&authSource=admin",
            "mongoURIUpdated": "2018-11-27T12:24:17Z",
        }
        mock_get_one_cluster.return_value = mock_http_return_value
        expected_out = copy.deepcopy(mock_http_return_value)
        expected_out.update(
            {
                "hosts": "mock_mongo_uri:27017",
                "mongodb_url": "mock_mongo_uri:27017/?ssl=true&authSource=admin",
                "hostname": "mock_primary_host",
                "port": 27017,
            }
        )

        atlas = atlas_setup.AtlasSetup(self.config)
        atlas.start()
        mock_post.assert_called_with(expected_url, auth=ANY, json=ANY)
        self.assertDictEqual(
            self.config["mongodb_setup"]["out"]["atlas"]["clusters"][0].as_dict(), expected_out
        )
        self.assertEqual(len(self.config["mongodb_setup"]["out"]["atlas"]["clusters"]), 1)

    def test_start_when_cluster_exists(self):
        with in_dir(FIXTURE_FILES.fixture_file_path("atlas-config")):
            config = load_config_dict("mongodb_setup")
            # Inject a fake cluster into mongodb_setup.out
            config["mongodb_setup"]["out"] = {}
            config["mongodb_setup"]["out"]["atlas"] = {}
            config["mongodb_setup"]["out"]["atlas"]["clusters"] = [
                {"name": "some_other_unique_name", "stateName": "IDLE"}
            ]
            atlas = atlas_setup.AtlasSetup(config)
            with self.assertRaises(RuntimeError):
                with LogCapture(level=logging.ERROR) as log_error:
                    self.assertFalse(atlas.start())
                    log_error.check(
                        (
                            "common.atlas_setup",
                            "ERROR",
                            "[error    ] Clusters already exist in mongodb_setup.out.atlas.clusters. [common.atlas_setup] ",
                        ),
                        (
                            "common.atlas_setup",
                            "ERROR",
                            "[error    ] Please shutdown existing clusters first with infrastructure_teardown.py. [common.atlas_setup] ",
                        ),
                    )

    @patch("dsi.common.atlas_client.AtlasClient.get_one_cluster")
    @patch("dsi.common.atlas_setup.AtlasSetup._generate_unique_name")
    @patch("requests.delete")
    def test_destroy(self, mock_delete, mock_generate, mock_get_one_cluster):
        with in_dir(FIXTURE_FILES.fixture_file_path("atlas-config")):
            config = load_config_dict("mongodb_setup")
            # Inject a fake cluster into mongodb_setup.out
            config["mongodb_setup"]["out"] = {}
            config["mongodb_setup"]["out"]["atlas"] = {}
            config["mongodb_setup"]["out"]["atlas"]["clusters"] = [
                {"name": "some_other_unique_name", "stateName": "IDLE"}
            ]
            atlas = atlas_setup.AtlasSetup(config)
            atlas.destroy()
        mock_delete.assert_called_with(
            "https://cloud-dev.mongodb.com/api/atlas/v1.0/MOCK/URL/groups/test_group_id/clusters/some_other_unique_name",
            auth=ANY,
        )
        self.assertEqual(config["mongodb_setup"]["out"]["atlas"]["clusters"], [])

    def test_unique_name(self):
        atlas_cluster = {"clusterType": "REPLSET", "providerSettings": {"instanceSizeName": "M99"}}
        with in_dir(FIXTURE_FILES.fixture_file_path("atlas-config")):
            config = load_config_dict("mongodb_setup")
            atlas = atlas_setup.AtlasSetup(config)
            name = atlas._generate_unique_name(atlas_cluster)
        # Generated name looks like: dsi-M99-abcdefg
        # (The last part is random, but fixed length.)
        self.assertRegex(name, "dsi-M99-")
        self.assertEqual(len(name), 15)

    @patch("time.sleep")
    @patch("dsi.common.atlas_client.AtlasClient.download_logs")
    @patch("dsi.common.atlas_client.AtlasClient.get_log_collection_job")
    @patch("dsi.common.atlas_client.AtlasClient.create_log_collection_job")
    def test_log_collection(self, mock_create, mock_get, mock_download, mock_sleep):
        mock_create.return_value = "12345abcdef"
        mock_get.side_effect = [{"status": "FOO"}, {"status": "SUCCESS"}]
        with in_dir(FIXTURE_FILES.fixture_file_path("atlas-config")):
            config = load_config_dict("mongodb_setup")
            # Inject a fake cluster into mongodb_setup.out
            config["mongodb_setup"]["out"] = {}
            config["mongodb_setup"]["out"]["atlas"] = {}
            config["mongodb_setup"]["out"]["atlas"]["clusters"] = [
                {"name": "mock_cluster_name", "clusterType": "REPLSET", "stateName": "IDLE"}
            ]
            atlas = atlas_setup.AtlasSetup(config)
            atlas.download_logs("post_task")
            mock_download.assert_called_with(
                "12345abcdef", "reports/post_task/mock_cluster_name.tgz"
            )
        mock_sleep.assert_called()
