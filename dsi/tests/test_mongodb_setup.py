"""Tests for the mongodb_setup module"""

import copy
import unittest

import mock

from dsi import mongodb_setup
from dsi.common import host as common_host
from dsi.common import mongodb_cluster

# Mock the remote host module.
mongodb_setup.RemoteHost = mock.MagicMock()

DEFAULT_CONFIG = {
    "infrastructure_provisioning": {
        "tfvars": {"ssh_user": "ec2-user", "ssh_key_file": "~/.ssh/user_ssh_key.pem"},
        "numactl_prefix": "numactl test",
        "out": {"workload_client": [{"public_ip": "1.2.3.4", "private_ip": "5.6.7.8"}]},
    },
    "mongodb_setup": {
        "shutdown_options": {"force": True, "timeoutSecs": 5},
        "meta": None,
        "mongo_dir": "test_dir",
        "mongod_config_file": {},
        "journal_dir": "/data/journal",
        "topology": [
            {
                "cluster_type": "standalone",
                "id": "myid1",
                "public_ip": "1.2.3.4",
                "private_ip": "10.2.0.1",
                "config_file": {
                    "net": {"port": 9999, "bindIp": "0.0.0.0"},
                    "storage": {"dbPath": "data/dbs", "engine": "wiredTiger"},
                    "systemLog": {"destination": "file", "path": "mongod.log"},
                },
            }
        ],
        "network_delays": {"clusters": [{"default": {"delay_ms": 0, "jitter_ms": 0}, "edges": []}]},
        "authentication": {"enabled": True, "username": "username", "password": "password"},
    },
    "test_control": {},
    "runtime_secret": {"atlas_api_user": "mock_atlas_api_user", "atlas_api_secret": "s3cret"},
}


class TestMongodbSetup(unittest.TestCase):
    """MongodbSetup tests"""

    def setUp(self):
        """Common options"""
        self.config = copy.deepcopy(DEFAULT_CONFIG)

    def test_timeouts(self):
        """Test shutdown / sigterm timeouts"""
        setup = mongodb_setup.MongodbSetup(self.config)
        self.assertEqual(setup.shutdown_ms, 540000)
        self.assertEqual(setup.sigterm_ms, 60000)

        self.config["mongodb_setup"]["timeouts"] = {
            "shutdown_ms": "shutdown",
            "sigterm_ms": "sigterm",
        }
        setup = mongodb_setup.MongodbSetup(self.config)
        self.assertEqual(setup.shutdown_ms, "shutdown")
        self.assertEqual(setup.sigterm_ms, "sigterm")

    @mock.patch.object(common_host, "Host", autospec=True)
    def test_start1(self, host):
        """Starting ignores shutdown fails """
        setup = mongodb_setup.MongodbSetup(config=self.config)
        setup.host = host
        setup.downloader = mock.MagicMock()

        host.run = mock.MagicMock()
        mongodb_cluster.MongoNode.wait_until_up = mock.MagicMock()
        setup.destroy = mock.MagicMock(name="destroy")
        setup.shutdown = mock.MagicMock(name="shutdown")
        setup.shutdown.return_value = True
        setup.downloader = mock.MagicMock()

        with mock.patch("dsi.mongodb_setup.run_threads") as mock_run_threads:
            mock_run_threads.return_value = [True]
            self.assertTrue(setup.restart())
            setup.destroy.assert_called_once_with(60000)
            setup.shutdown.assert_called_once_with(540000, True)
            setup.downloader.download_and_extract.assert_not_called()
            mock_run_threads.assert_called_once()

    def test_start(self):
        """ test start"""

        @mock.patch("dsi.mongodb_setup.run_pre_post_commands")
        def _test_start(mock_run_pre_post_commands, download_status=False, pre_cluster_start=False):
            test_config = copy.deepcopy(self.config)
            if pre_cluster_start:
                test_config["mongodb_setup"]["pre_cluster_start"] = [
                    {"on_all_hosts": {"retrieve_files": [{"source": "foo", "target": "bar"}]}}
                ]

            setup = mongodb_setup.MongodbSetup(config=test_config)
            setup.downloader = mock.MagicMock()
            setup.downloader.download_and_extract = mock.MagicMock(name="downloader")

            setup._start = mock.MagicMock(name="_start")
            setup.destroy = mock.MagicMock(name="destroy")
            # shutdown should never be called in this path
            setup.shutdown = mock.MagicMock(name="shutdown")
            setup.downloader.download_and_extract.return_value = download_status

            if not download_status:
                self.assertEqual(setup.start(), False)
                setup._start.assert_not_called()
            else:
                self.assertEqual(setup.start(), True)
                setup._start.assert_called_once()

            setup.destroy.assert_called_once_with(60000)
            setup.shutdown.assert_not_called()
            setup.downloader.download_and_extract.assert_called_once()

        _test_start()
        _test_start(download_status=True)

    def test_restart(self):
        """ test start"""

        def _test_restart(shutdown=True):
            setup = mongodb_setup.MongodbSetup(config=self.config)

            setup._start = mock.MagicMock(name="_start")
            setup._start.return_value = "start clusters"

            setup.destroy = mock.MagicMock(name="destroy")
            setup.destroy.return_value = shutdown
            setup.shutdown = mock.MagicMock(name="shutdown")
            setup.shutdown.return_value = shutdown

            if not shutdown:
                self.assertEqual(setup.restart(), False)
                setup._start.assert_not_called()
            else:
                self.assertEqual(setup.restart(), "start clusters")
                setup._start.assert_called_once_with(
                    is_restart=True, restart_clean_db_dir=None, restart_clean_logs=None
                )
            setup.destroy.assert_called_once_with(60000)
            setup.shutdown.assert_called_once_with(540000, True)

        _test_restart()
        _test_restart(shutdown=False)

    def test_restart_auth_enabled(self):
        """ Test restart when auth is enabled. Make sure shutdown is called with auth enabled. """
        setup = mongodb_setup.MongodbSetup(config=self.config)

        setup._start = mock.MagicMock(name="_start")
        setup._start.return_value = "start clusters"

        setup.destroy = mock.MagicMock(name="destroy")
        setup.shutdown = mock.MagicMock(name="shutdown")
        setup.restart()
        setup.shutdown.assert_called_once_with(setup.shutdown_ms, True)

    def _test__start(self, run_threads, success=True):
        setup = mongodb_setup.MongodbSetup(config=self.config)
        setup.downloader = mock.MagicMock()
        setup.downloader.download_and_extract.return_value = False
        mongodb_cluster.MongoNode.wait_until_up = mock.MagicMock()
        setup.destroy = mock.MagicMock(name="destroy")
        setup.shutdown = mock.MagicMock(name="shutdown")
        setup.shutdown.return_value = False

        with mock.patch("dsi.mongodb_setup.run_threads") as mock_run_threads, mock.patch(
            "dsi.mongodb_setup.partial"
        ) as mock_partial, mock.patch("dsi.common.mongodb_cluster.MongoNode.run_mongo_shell"):
            mock_run_threads.return_value = run_threads
            mock_partial.return_value = "threads"

            self.assertEqual(setup._start(), success)
            calls = [
                mock.call(
                    setup.start_cluster,
                    cluster=setup.clusters[0],
                    is_restart=False,
                    restart_clean_db_dir=None,
                    restart_clean_logs=None,
                    enable_auth=False,
                )
            ]
            mock_partial.assert_has_calls(calls)
            setup.destroy.assert_not_called()
            if success:
                setup.shutdown.assert_has_calls([mock.call(540000)])  # shutdown for setup
            else:
                setup.shutdown.assert_has_calls(
                    [mock.call(540000), mock.call(540000), mock.call(540000)]
                )
            setup.downloader.download_and_extract.assert_not_called()
            mock_run_threads.assert_has_calls([mock.call(["threads"], daemon=True)])

    def test__start_1(self):
        self._test__start([True])

    def test__start_2(self):
        self._test__start([True])

    def test__start_3(self):
        self._test__start([True, True])

    def test__start_4(self):
        self._test__start([True, False], success=False)

    def test__start_with_auth1(self):
        """ Test _start with auth enabled for is_restart=False """
        setup = mongodb_setup.MongodbSetup(config=self.config)

        mock_add_default_users = mock.MagicMock(name="add_default_users")
        mock_shutdown = mock.MagicMock(name="shutdown")
        setup.add_default_users = mock_add_default_users
        setup.shutdown = mock_shutdown
        with mock.patch("dsi.mongodb_setup.run_threads") as mock_run_threads, mock.patch(
            "dsi.mongodb_setup.partial"
        ) as mock_partial:
            mock_run_threads.return_value = [True, True]
            mock_partial.return_value = "threads"
            self.assertEqual(setup._start(), True)
            mock_shutdown.assert_has_calls([mock.call(setup.shutdown_ms)])
            mock_partial.assert_has_calls(
                [
                    mock.call(
                        setup.start_cluster,
                        cluster=setup.clusters[0],
                        is_restart=False,
                        restart_clean_db_dir=None,
                        restart_clean_logs=None,
                        enable_auth=False,
                    ),
                    mock.call(
                        setup.start_cluster,
                        cluster=setup.clusters[0],
                        is_restart=True,
                        restart_clean_db_dir=False,
                        restart_clean_logs=False,
                        enable_auth=True,
                    ),
                ]
            )
        mock_add_default_users.assert_called_once()

    def test__start_with_auth2(self):
        """ Test _start with auth enabled for is_restart=True, and clean_db_dir=True"""
        setup = mongodb_setup.MongodbSetup(config=self.config)

        mock_add_default_users = mock.MagicMock(name="add_default_users")
        mock_shutdown = mock.MagicMock(name="shutdown")
        setup.add_default_users = mock_add_default_users
        setup.shutdown = mock_shutdown
        with mock.patch("dsi.mongodb_setup.run_threads") as mock_run_threads, mock.patch(
            "dsi.mongodb_setup.partial"
        ) as mock_partial:
            mock_run_threads.return_value = [True, True]
            mock_partial.return_value = "threads"
            self.assertEqual(
                setup._start(is_restart=True, restart_clean_db_dir=True, restart_clean_logs=True),
                True,
            )
            mock_shutdown.assert_has_calls([mock.call(setup.shutdown_ms)])
            mock_partial.assert_has_calls(
                [
                    mock.call(
                        setup.start_cluster,
                        cluster=setup.clusters[0],
                        is_restart=True,
                        restart_clean_db_dir=True,
                        restart_clean_logs=True,
                        enable_auth=False,
                    ),
                    mock.call(
                        setup.start_cluster,
                        cluster=setup.clusters[0],
                        is_restart=True,
                        restart_clean_db_dir=False,
                        restart_clean_logs=False,
                        enable_auth=True,
                    ),
                ]
            )
        mock_add_default_users.assert_called_once()

    def test__start_with_auth3(self):
        """ Test _start with auth enabled for is_restart=True and clean_db_dir=False."""
        setup = mongodb_setup.MongodbSetup(config=self.config)

        mock_add_default_users = mock.MagicMock(name="add_default_users")
        mock_shutdown = mock.MagicMock(name="shutdown")
        setup.add_default_users = mock_add_default_users
        setup.shutdown = mock_shutdown
        with mock.patch("dsi.mongodb_setup.run_threads") as mock_run_threads, mock.patch(
            "dsi.mongodb_setup.partial"
        ) as mock_partial:
            mock_run_threads.return_value = [True, True]
            mock_partial.return_value = "threads"
            self.assertEqual(
                setup._start(is_restart=True, restart_clean_db_dir=False, restart_clean_logs=True),
                True,
            )
            setup.shutdown.assert_not_called()
            mock_partial.assert_has_calls(
                [
                    mock.call(
                        setup.start_cluster,
                        cluster=setup.clusters[0],
                        is_restart=True,
                        restart_clean_db_dir=False,
                        restart_clean_logs=True,
                        enable_auth=True,
                    )
                ]
            )
        mock_add_default_users.assert_not_called()

    def test_add_default_users(self):
        """
        Test MongodbSetup.add_default_users.
        """
        setup = mongodb_setup.MongodbSetup(config=self.config)
        mock_cluster1 = mock.MagicMock(name="cluster1")
        mock_cluster2 = mock.MagicMock(name="cluster2")
        setup.clusters = [mock_cluster1, mock_cluster2]
        setup.add_default_users()
        for cluster in setup.clusters:
            cluster.add_default_users.assert_called_once()

    def test_shutdown(self):
        """Test MongodbSetup.shutdown """

        setup = mongodb_setup.MongodbSetup(config=self.config)
        mock_cluster1 = mock.MagicMock(name="cluster1")
        mock_cluster2 = mock.MagicMock(name="cluster2")
        setup.clusters = [mock_cluster1, mock_cluster2]
        with mock.patch("dsi.mongodb_setup.run_threads") as mock_run_threads, mock.patch(
            "dsi.mongodb_setup.partial"
        ) as mock_partial:

            mock_run_threads.return_value = [True]
            self.assertTrue(setup.shutdown(1))
            mock_partial.assert_has_calls(
                [
                    mock.call(mock_cluster1.shutdown, 1, None),
                    mock.call(mock_cluster2.shutdown, 1, None),
                ]
            )

    def test_destroy(self):
        """Test MongodbSetup.destroy"""

        setup = mongodb_setup.MongodbSetup(config=self.config)
        mock_cluster1 = mock.MagicMock(name="cluster1")
        mock_cluster2 = mock.MagicMock(name="cluster2")
        setup.clusters = [mock_cluster1, mock_cluster2]
        with mock.patch("dsi.mongodb_setup.run_threads") as mock_run_threads, mock.patch(
            "dsi.mongodb_setup.partial"
        ) as mock_partial:

            mock_run_threads.return_value = [True]
            self.assertTrue(setup.destroy(1))
            mock_partial.assert_has_calls(
                [mock.call(mock_cluster1.destroy, 1), mock.call(mock_cluster2.destroy, 1)]
            )

    def test_start_cluster(self):
        """ test start and correctly handles run on error"""

        @mock.patch("sys.exit")
        @mock.patch("dsi.mongodb_setup.run_upon_error")
        def _test_start_cluster(success, mock_run_upon_error, mock_exit):

            mongo = mock.MagicMock(name="mongo")
            config = {"mongodb_setup": "value"}
            mongo.start.return_value = success
            mongodb_setup.start_cluster(mongo, config)
            if not success:
                mock_run_upon_error.assert_called_once()
                mock_run_upon_error.assert_called_with("mongodb_setup", ["value"], config)
                mock_exit.assert_called_with(1)
            else:
                mock_run_upon_error.assert_not_called()
                mock_exit.assert_not_called()

        _test_start_cluster(True)  # success
        _test_start_cluster(False)  # failure


if __name__ == "__main__":
    unittest.main()
