"""
Unit test for atlas_client.py
"""


import os
import unittest

import requests
from mock import patch, MagicMock

from dsi.common import atlas_client
from test_lib.fixture_files import FixtureFiles

FIXTURE_FILES = FixtureFiles()


class TestAtlasClient(unittest.TestCase):
    def setUp(self):
        self.api = {
            "root": "https://cloud-dev.mongodb.com/api/atlas/v1.0/MOCK/URL",
            "private": "https://cloud.mongodb.com/api/private/MOCK/URL",
            "group_id": "mock_group_id",
        }
        self.api_credentials = {"public_key": "mock_user", "private_key": "mock_key"}
        self.auth = requests.auth.HTTPDigestAuth("mock_user", "mock_key")
        self.atlas_client = atlas_client.AtlasClient(self.api, self.api_credentials)

        self.custom_build = {
            "trueName": "4.2.0-rc1-45-g84519c5",
            "gitVersion": "84519c5dcffde5e59a007a19be32d943b32e908e",
            "architecture": "amd64",
            "modules": ["enterprise"],
            "platform": "linux",
            "flavor": "rhel",
            "minOsVersion": "7.0",
            "maxOsVersion": "8.0",
            "url": "https://s3.amazonaws.com/mciuploads/foo.tgz",
        }

        self.download_file = os.path.join(
            FIXTURE_FILES.fixture_file_path("atlas-config"), "mock_download_file.tgz"
        )
        self._cleanup()

    def tearDown(self):
        self._cleanup()

    def _cleanup(self):
        if os.path.exists(self.download_file):
            os.remove(self.download_file)

    @patch("requests.post")
    def test_create_cluster(self, mock_post):
        self.atlas_client.create_cluster({"mock_cluster": "omitting_config"})
        mock_post.assert_called_with(
            self.api["root"] + "/groups/mock_group_id/clusters",
            auth=self.auth,
            json={"mock_cluster": "omitting_config"},
        )

    @patch("requests.delete")
    def test_delete_cluster(self, mock_delete):
        self.atlas_client.delete_cluster("test_cluster_name")
        mock_delete.assert_called_with(
            self.api["root"] + "/groups/mock_group_id/clusters/test_cluster_name", auth=self.auth
        )

    @patch("requests.get")
    def test_get_one_cluster(self, mock_get):
        self.atlas_client.get_one_cluster("test_cluster_name")
        mock_get.assert_called_with(
            self.api["root"] + "/groups/mock_group_id/clusters/test_cluster_name", auth=self.auth
        )

    @patch("time.sleep")
    @patch("dsi.common.atlas_client.AtlasClient.get_one_cluster")
    def test_await_idle(self, mock_get_one_cluster, mock_time):
        state_names = [{"stateName": "CREATING"}, {"stateName": "CREATING"}, {"stateName": "IDLE"}]
        # Note: When given an iterable, side_effect returns one element for each call.
        mock_get_one_cluster.side_effect = state_names

        self.atlas_client.await_idle("test_cluster_name")
        mock_get_one_cluster.assert_called_with("test_cluster_name")
        mock_time.assert_called()

    @patch("time.sleep")
    @patch("dsi.common.atlas_client.AtlasClient.get_one_cluster")
    def test_await_state_timeout(self, mock_get_one_cluster, mock_time):
        mock_get_one_cluster.side_effect = [{"stateName": "CREATING"}]

        with self.assertRaises(atlas_client.AtlasTimeout):
            self.atlas_client.await_state("test_cluster_name", "IDLE", -1)
        mock_get_one_cluster.assert_called_with("test_cluster_name")
        mock_time.assert_called()

    @patch("dsi.common.atlas_client.shutil.copyfileobj")
    @patch("dsi.common.atlas_client.mkdir_p")
    @patch("requests.get")
    @patch("requests.post")
    def test_log_collection(self, mock_post, mock_get, mock_mkdir_p, mock_copy):
        mock_response = MagicMock()
        mock_response.json.return_value = {"id": "12345abcdef"}
        mock_post.return_value = mock_response

        job_id = self.atlas_client.create_log_collection_job({"mock_cluster": "omitting_config"})
        mock_post.assert_called_with(
            self.api["root"] + "/groups/mock_group_id/logCollectionJobs",
            auth=self.auth,
            json={"mock_cluster": "omitting_config"},
        )
        self.assertEqual(job_id, "12345abcdef")

        self.atlas_client.download_logs(job_id, self.download_file)
        mock_get.assert_called_with(
            self.api["root"] + "/groups/mock_group_id/logCollectionJobs/12345abcdef/download",
            auth=self.auth,
            stream=True,
        )
        mock_mkdir_p.assert_called_with(os.path.dirname(self.download_file))

    @patch("time.sleep")
    @patch("dsi.common.atlas_client.AtlasClient.get_log_collection_job")
    def test_await_log_job(self, mock_get, mock_time):
        mock_get.side_effect = [{"status": "FOO"}, {"status": "SUCCESS"}]

        self.atlas_client.await_log_job("test_job_id")
        mock_get.assert_called_with("test_job_id")
        mock_time.assert_called()

    @patch("requests.post")
    def test_create_custom_build(self, mock_post):
        self.atlas_client.create_custom_build(self.custom_build)
        mock_post.assert_called_with(
            self.api["private"] + "/nds/customMongoDbBuild", auth=self.auth, json=self.custom_build
        )

    @patch("requests.get")
    def test_get_custom_build(self, mock_get):
        self.atlas_client.get_custom_build("test_true_name")
        mock_get.assert_called_with(
            self.api["private"] + "/nds/customMongoDbBuild/test_true_name", auth=self.auth
        )

    @patch("requests.post")
    def test_create_custom_cluster(self, mock_post):
        self.atlas_client.create_cluster({"mock_cluster": "omitting_config"})
        mock_post.assert_called_with(
            self.api["root"] + "/groups/mock_group_id/clusters",
            auth=self.auth,
            json={"mock_cluster": "omitting_config"},
        )
