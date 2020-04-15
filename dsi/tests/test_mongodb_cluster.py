"""Tests for the mongodb_setup module"""


import os
import os.path
import unittest

import mock
from mock import MagicMock, patch

from dsi.common import mongodb_cluster
from dsi.common import mongodb_setup_helpers
from dsi.common.mongo_config import NodeTopologyConfig, ReplTopologyConfig, ShardedTopologyConfig
from dsi.delay import DelayGraph
from test_lib.comparator_utils import ANY_IN_STRING

# Mock the remote host module.
mongodb_cluster.RemoteHost = mock.MagicMock()

MONGOD_OPTS = {
    "public_ip": "1.2.3.4",
    "private_ip": "10.2.0.1",
    "config_file": {
        "net": {"port": 9999, "bindIp": "0.0.0.0"},
        "systemLog": {"destination": "file", "path": "mongod.log"},
        "storage": {"dbPath": "data/dbs"},
    },
    "rs_conf_member": {},
}

DELAY_CONFIG = {
    "network_delays": {"clusters": [{"default": {"delay_ms": 0, "jitter_ms": 0}, "edges": []}]}
}

DEFAULT_CONFIG = {
    "infrastructure_provisioning": {
        "tfvars": {"ssh_user": "ec2-user", "ssh_key_file": "~/.ssh/user_ssh_key.pem"},
        "numactl_prefix": "numactl test",
        "out": [],
    },
    "mongodb_setup": {
        "mongo_dir": "/usr/",
        "mongod_config_file": {},
        "shutdown_options": {"force": True, "timeoutSecs": 5},
        "journal_dir": "/data/journal",
        "meta": {},
        "authentication": {"enabled": True, "username": "username", "password": "password"},
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
    },
    "test_control": {},
}


class TestMongoNode(unittest.TestCase):
    """MongoNode tests"""

    def setUp(self):
        """Create a MongoNode instance to use throughout tests."""
        topology = mongodb_setup_helpers.copy_obj(MONGOD_OPTS)
        self.topology = topology
        self.config = DEFAULT_CONFIG
        self.delay_graph = MagicMock()
        node_topology = NodeTopologyConfig(self.topology, self.config, self.delay_graph)
        self.mongo_node = mongodb_cluster.MongoNode(node_topology)
        mock_host = mock.MagicMock(name="host")
        self.mongo_node._host = mock_host

    def test_establish_delays(self):
        self.mongo_node.establish_delays()
        self.delay_graph.get_node.assert_called_once_with("10.2.0.1")
        self.delay_graph.get_node.return_value.establish_delays.assert_called_once()

    def test_run_mongo_shell(self):
        """Test hostport format"""

        mock_host = self.mongo_node.host
        mock_host.exec_mongo_command.return_value = 0
        self.assertTrue(self.mongo_node.run_mongo_shell("js command"))
        mock_host.exec_mongo_command.assert_called_once_with(
            "js command",
            remote_file_name="/tmp/mongo_port_9999.js",
            connection_string="localhost:9999",
            max_time_ms=None,
        )

        mock_host = mock.MagicMock(name="host")
        mock_dump_mongo_log = mock.MagicMock(name="dump_mongo_log")
        self.mongo_node._host = mock_host
        self.mongo_node.dump_mongo_log = mock_dump_mongo_log
        mock_host.exec_mongo_command.return_value = 1

        self.assertFalse(self.mongo_node.run_mongo_shell("js command", max_time_ms=1))
        mock_dump_mongo_log.assert_called_once()
        mock_host.exec_mongo_command.assert_called_once_with(
            "js command",
            remote_file_name="/tmp/mongo_port_9999.js",
            connection_string="localhost:9999",
            max_time_ms=1,
        )

    def test_hostport(self):
        """Test hostport format"""
        self.assertEqual(self.mongo_node.hostport_private(), "10.2.0.1:9999")

    def test_logdir(self):
        """Default log dir is empty"""
        self.assertEqual(self.mongo_node.mongo_config.logdir, "")

    def _commands_run_during_setup_host(self, restart_clean_db_dir=None, restart_clean_logs=None):
        """Returns list of (args,kwargs) tuples representing calls to `host.run`
        made during invocation of setup_host with the given setup_host_args."""
        host = mock.MagicMock()
        host.run.return_value = "<Expected>"
        self.mongo_node._host = host

        return_value = self.mongo_node.setup_host(
            restart_clean_db_dir=restart_clean_db_dir, restart_clean_logs=restart_clean_logs
        )
        calls = [args for (method, args, _) in host.method_calls if method == "run"]

        self.assertIs(len(calls), 1, "Only one call to host.run()")
        # calls is list of run method calls; calls[0] is (args,kwargs) tuple
        # https://docs.python.org/3/library/unittest.mock.html#calls-as-tuples
        return return_value, calls[0][0]

    def test_setup_host_defaults(self):
        """We issue the important `rm` commands when setup_host is called with default parameters"""
        return_value, commands_issued = self._commands_run_during_setup_host()
        self.assertEqual(
            return_value,
            "<Expected>",
            "Calling run() doesn't return None. " + "It returns what the host delegate returns.",
        )

        required = [
            ["rm", "-rf", a]
            for a in [
                "*.log",
                "core.*",
                "data/dbs/diagnostic.data/*",
                "diagnostic.data",
                "data/dbs",
                "/data/journal",
            ]
        ]
        for req in required:
            self.assertTrue(
                req in commands_issued,
                "Should have issued command %s in %s" % (req, commands_issued),
            )

    def test_rm_commands_no_cleanup(self):
        """We don't issue any rm commands if we give False for clean_* params"""
        _, commands_issued = self._commands_run_during_setup_host(
            restart_clean_db_dir=False, restart_clean_logs=False
        )
        for command in commands_issued:
            self.assertNotIn("rm", command, "No rm commands in setup_host without clean_* args")

    def _test_setup_commands(self, generate_setup_commands_args, expected):
        """Runs _generate_setup_commands with given args
        and asserts the output == expected. If not, prints it out in a form
        that you can copy/paste into an 'expected' var"""
        actual = mongodb_cluster.MongoNode._generate_setup_commands(generate_setup_commands_args)
        self.assertEqual(actual, expected, msg=",\n".join([str(x) for x in actual]))

    def test_ssh_key(self):
        """Test ~/.ssh/user_aws_key.pem"""
        ssh_key_file = self.config["infrastructure_provisioning"]["tfvars"]["ssh_key_file"]
        expected_ssh_key_file = os.path.expanduser(ssh_key_file)

        topology = self.config["mongodb_setup"]["topology"][0]
        delay_graph = DelayGraph(topology, DELAY_CONFIG["network_delays"]["clusters"][0])
        node_topology = NodeTopologyConfig(topology, self.config, delay_graph)
        node = mongodb_cluster.MongoNode(node_topology)
        actual_user = node.net_config.ssh_user
        actual_key = node.net_config.ssh_key_file
        self.assertEqual(actual_key, expected_ssh_key_file)
        self.assertEqual(actual_user, "ec2-user")

    # below tests want to be named
    #     test_generate_setup_commands_*
    # by pylint doesn't like the method names
    #
    # Below we test each combination of clean_db_dir, clean_logs, and use_journal_mnt
    # to be True and False with ttt indicating that all are True, ttf indicating
    # that all are true except for use_journal_mount which is False, etc.

    def test_gen_setup_commands_ttt(self):
        """Proper output for _generate_setup_commands with
        clean_db_dir = True
        clean_logs = True
        use_journal_mnt = True
        is_mongos = True
        """
        self._test_setup_commands(
            {
                "clean_db_dir": True,
                "clean_logs": True,
                "use_journal_mnt": True,
                "is_mongos": True,
                "dbdir": "some dir with spaces",
                "journal_dir": "$journal_dir",  # intentionally ugly
                "logdir": "/ log/di r//",
            },
            [
                ["rm", "-rf", "/ log/di r//*.log"],
                ["rm", "-rf", "/ log/di r//core.*"],
                ["mkdir", "-p", "/ log/di r//"],
                ["mkdir", "-p", "some dir with spaces/diagnostic.data"],
                ["rm", "-rf", "/ log/di r//diagnostic.data"],
                ["mv", "some dir with spaces/diagnostic.data", "/ log/di r//"],
                ["rm", "-rf", "some dir with spaces"],
                ["rm", "-rf", "$journal_dir"],
                ["mkdir", "-p", "some dir with spaces"],
                ["mv", "/ log/di r//diagnostic.data", "some dir with spaces"],
                ["mkdir", "-p", "$journal_dir"],
                ["ln", "-s", "$journal_dir", "some dir with spaces/journal"],
            ],
        )

    def test_gen_setup_commands_ttf_t(self):
        """Proper output for _generate_setup_commands with
        clean_db_dir = True
        clean_logs = True
        use_journal_mnt = False
        is_mongos = True
        """
        self._test_setup_commands(
            {
                "clean_db_dir": True,
                "clean_logs": True,
                "use_journal_mnt": False,
                "is_mongos": True,
                "dbdir": "dbdir",
                "journal_dir": "journaldir",
                "logdir": "logdir",
            },
            [
                ["rm", "-rf", "logdir/*.log"],
                ["rm", "-rf", "logdir/core.*"],
                ["mkdir", "-p", "logdir"],
                ["mkdir", "-p", "dbdir/diagnostic.data"],
                ["rm", "-rf", "logdir/diagnostic.data"],
                ["mv", "dbdir/diagnostic.data", "logdir"],
                ["rm", "-rf", "dbdir"],
                ["mkdir", "-p", "dbdir"],
                ["mv", "logdir/diagnostic.data", "dbdir"],
            ],
        )

    def test_gen_setup_commands_ttf_f(self):
        """Proper output for _generate_setup_commands with
        clean_db_dir = True
        clean_logs = True
        use_journal_mnt = False
        is_mongos = False
        """
        self._test_setup_commands(
            {
                "clean_db_dir": True,
                "clean_logs": True,
                "use_journal_mnt": False,
                "is_mongos": False,
                "dbdir": "dbdir",
                "journal_dir": "journaldir",
                "logdir": "logdir",
            },
            [
                ["rm", "-rf", "logdir/*.log"],
                ["rm", "-rf", "logdir/core.*"],
                ["rm", "-rf", "dbdir/diagnostic.data/*"],
                ["mkdir", "-p", "logdir"],
                ["mkdir", "-p", "dbdir/diagnostic.data"],
                ["rm", "-rf", "logdir/diagnostic.data"],
                ["mv", "dbdir/diagnostic.data", "logdir"],
                ["rm", "-rf", "dbdir"],
                ["mkdir", "-p", "dbdir"],
                ["mv", "logdir/diagnostic.data", "dbdir"],
            ],
        )

    def test_gen_setup_commands_tft(self):
        """Proper output for _generate_setup_commands with
        clean_db_dir = True
        clean_logs = False
        use_journal_mnt = True
        is_mongos = True
        """
        self._test_setup_commands(
            {
                "clean_db_dir": True,
                "clean_logs": False,
                "use_journal_mnt": True,
                "is_mongos": True,
                "dbdir": "dbdir",
                "journal_dir": "journaldir",
                "logdir": "logdir",
            },
            [
                ["mkdir", "-p", "logdir"],
                ["mkdir", "-p", "dbdir/diagnostic.data"],
                ["rm", "-rf", "logdir/diagnostic.data"],
                ["mv", "dbdir/diagnostic.data", "logdir"],
                ["rm", "-rf", "dbdir"],
                ["rm", "-rf", "journaldir"],
                ["mkdir", "-p", "dbdir"],
                ["mv", "logdir/diagnostic.data", "dbdir"],
                ["mkdir", "-p", "journaldir"],
                ["ln", "-s", "journaldir", "dbdir/journal"],
            ],
        )

    def test_gen_setup_commands_tff(self):
        """Proper output for _generate_setup_commands with
        clean_db_dir = True
        clean_logs = False
        use_journal_mnt = False
        is_mongos = True
        """
        self._test_setup_commands(
            {
                "clean_db_dir": True,
                "clean_logs": False,
                "use_journal_mnt": False,
                "is_mongos": True,
                "dbdir": "dbdir",
                "journal_dir": "journaldir",
                "logdir": "logdir",
            },
            [
                ["mkdir", "-p", "logdir"],
                ["mkdir", "-p", "dbdir/diagnostic.data"],
                ["rm", "-rf", "logdir/diagnostic.data"],
                ["mv", "dbdir/diagnostic.data", "logdir"],
                ["rm", "-rf", "dbdir"],
                ["mkdir", "-p", "dbdir"],
                ["mv", "logdir/diagnostic.data", "dbdir"],
            ],
        )

    def test_gen_setup_commands_ftt(self):
        """Proper output for _generate_setup_commands with
        clean_db_dir = False
        clean_logs = True
        use_journal_mnt = True
        is_mongos = True
        """
        self._test_setup_commands(
            {
                "clean_db_dir": False,
                "clean_logs": True,
                "use_journal_mnt": True,
                "is_mongos": True,
                "dbdir": "dbdir",
                "journal_dir": "journaldir",
                "logdir": "logdir",
            },
            [
                ["rm", "-rf", "logdir/*.log"],
                ["rm", "-rf", "logdir/core.*"],
                ["mkdir", "-p", "logdir"],
            ],
        )

    def test_gen_setup_commands_ftf(self):
        """Proper output for _generate_setup_commands with
        clean_db_dir = False
        clean_logs = True
        use_journal_mnt = False
        is_mongos = True
        """
        self._test_setup_commands(
            {
                "clean_db_dir": False,
                "clean_logs": True,
                "use_journal_mnt": False,
                "is_mongos": True,
                "dbdir": "dbdir",
                "journal_dir": "journaldir",
                "logdir": "logdir",
            },
            [
                ["rm", "-rf", "logdir/*.log"],
                ["rm", "-rf", "logdir/core.*"],
                ["mkdir", "-p", "logdir"],
            ],
        )

    def test_gen_setup_commands_fft(self):
        """Proper output for _generate_setup_commands with
        clean_db_dir = False
        clean_logs = False
        use_journal_mnt = True
        is_mongos = True
        """
        self._test_setup_commands(
            {
                "clean_db_dir": False,
                "clean_logs": False,
                "use_journal_mnt": True,
                "is_mongos": True,
                "dbdir": "dbdir",
                "journal_dir": "journaldir",
                "logdir": "logdir",
            },
            [["mkdir", "-p", "logdir"]],
        )

    def test_gen_setup_commands_fff(self):
        """Proper output for _generate_setup_commands with
        clean_db_dir = False
        clean_logs = False
        use_journal_mnt = False
        is_mongos = True
        """
        self._test_setup_commands(
            {
                "clean_db_dir": False,
                "clean_logs": False,
                "use_journal_mnt": False,
                "is_mongos": True,
                "dbdir": "dbdir",
                "journal_dir": "journaldir",
                "logdir": "logdir",
            },
            [["mkdir", "-p", "logdir"]],
        )

    def launch_cmd_helper(self, modified, enable_auth):
        """Test launch command uses proper config file."""

        if modified:
            config = mongodb_setup_helpers.copy_obj(DEFAULT_CONFIG)
            config["infrastructure_provisioning"][
                "numactl_prefix"
            ] = "numactl --interleave=all --cpunodebind=1"
            delay_graph = DelayGraph(
                config["mongodb_setup"]["topology"][0],
                DELAY_CONFIG["network_delays"]["clusters"][0],
            )
            node_topology = NodeTopologyConfig(self.topology, config, delay_graph)
            node = mongodb_cluster.MongoNode(node_topology)
            node._host = mock.MagicMock(name="host")
            numa_prefix = config["infrastructure_provisioning"]["numactl_prefix"]
        else:
            node = self.mongo_node
            numa_prefix = DEFAULT_CONFIG["infrastructure_provisioning"]["numactl_prefix"]

        expected_full_command = numa_prefix.split(" ") + [
            "/usr/bin/mongod",
            "--config",
            "/tmp/mongo_port_9999.conf",
        ]
        # if enable_auth:
        #    expected_full_command += " --clusterAuthMode x509"
        self.assertEqual(node.launch_cmd(enable_auth=enable_auth), expected_full_command)

    def test_launch_cmd_default_auth_disabled(self):
        self.launch_cmd_helper(False, False)

    def test_launch_cmd_default_auth_enabled(self):
        self.launch_cmd_helper(False, True)

    def test_launch_cmd_modified_auth_disabled(self):
        self.launch_cmd_helper(True, False)

    def test_launch_cmd_modified_auth_enabled(self):
        self.launch_cmd_helper(True, True)

    def test_shutdown(self):
        """
        Test shutdown.
        """
        mock_logger = mock.MagicMock(name="LOG")
        mongodb_cluster.LOG.warning = mock_logger
        self.mongo_node.mongo_config.shutdown_options = "{}"
        self.mongo_node.run_mongo_shell = mock.MagicMock(name="run_mongo_shell")
        self.mongo_node.host.run = mock.MagicMock(name="run")
        self.mongo_node.host.run.return_value = False
        self.assertTrue(self.mongo_node.shutdown(1))
        self.mongo_node.run_mongo_shell.assert_called_once_with(
            'db.getSiblingDB("admin").shutdownServer({})', max_time_ms=1, dump_on_error=True
        )
        self.mongo_node.host.run.assert_called_once_with(["pgrep -l", "mongo"])
        mock_logger.assert_not_called()

    def test_shutdown_options(self):
        """
        Test failed shutdown with options.
        """
        mock_logger = mock.MagicMock(name="LOG")
        mongodb_cluster.LOG.warning = mock_logger
        self.mongo_node.mongo_config.shutdown_options = "options"
        self.mongo_node.run_mongo_shell = mock.MagicMock(name="run_mongo_shell")
        self.mongo_node._host.run = mock.MagicMock(name="run")
        self.mongo_node._host.run.return_value = True
        # Use a lower `retry` to speed up the test.
        self.assertFalse(self.mongo_node.shutdown(1, retries=1))
        self.mongo_node.run_mongo_shell.assert_called_with(
            'db.getSiblingDB("admin").shutdownServer(options)', max_time_ms=1, dump_on_error=True
        )
        self.mongo_node.host.run.assert_called_with(["pgrep -l", "mongo"])
        mock_logger.assert_called_with(ANY_IN_STRING("did not shutdown yet"), mock.ANY, mock.ANY)

    @patch("dsi.common.mongodb_cluster.time.sleep")
    def test_shutdown_mongo_shell_exception(self, mock_sleep):
        """
        Test shutdown with exeception from `run_mongo_shell`.
        """
        self.mongo_node.run_mongo_shell = mock.MagicMock(name="run_mongo_shell")
        self.mongo_node.host.run = mock.MagicMock(name="run")
        self.mongo_node.run_mongo_shell.side_effect = Exception()
        self.assertFalse(self.mongo_node.shutdown(1))
        self.assertEqual(self.mongo_node.host.run.call_count, 20)
        self.assertEqual(mock_sleep.call_count, 20)

    def test_destroy(self):
        """Test destroy."""

        self.mongo_node.host.kill_mongo_procs = mock.MagicMock(name="kill_mongo_procs")
        self.mongo_node.host.run = mock.MagicMock(name="run")
        self.mongo_node.host.kill_mongo_procs.return_value = True
        self.assertTrue(self.mongo_node.destroy(1))
        calls = [mock.call(signal_number=15, max_time_ms=1), mock.call()]
        self.mongo_node.host.kill_mongo_procs.assert_has_calls(calls)
        self.mongo_node.host.run.assert_called_once_with(["rm", "-rf", "data/dbs/mongod.lock"])

        self.mongo_node.host.kill_mongo_procs = mock.MagicMock(name="kill_mongo_procs")
        self.mongo_node.host.run = mock.MagicMock(name="run")
        self.mongo_node.host.kill_mongo_procs.return_value = False
        self.mongo_node.mongo_config.dbdir = None
        self.assertFalse(self.mongo_node.destroy(2))
        calls = [mock.call(signal_number=15, max_time_ms=2), mock.call()]
        self.mongo_node.host.kill_mongo_procs.assert_has_calls(calls)
        self.mongo_node.host.run.assert_not_called()

        self.mongo_node.host.kill_mongo_procs = mock.MagicMock(name="kill_mongo_procs")
        self.mongo_node.host.kill_mongo_procs.side_effect = [Exception(), True]
        self.mongo_node.host.run = mock.MagicMock(name="run")

        with self.assertRaises(Exception):
            self.mongo_node.destroy(2)
        calls = [mock.call(signal_number=15, max_time_ms=2), mock.call()]
        self.mongo_node.host.kill_mongo_procs.assert_has_calls(calls)

    def test_add_default_users(self):
        """
        Test that add_default_users adds users on the correct clusters for a mongo node.
        """
        mock_add_user = MagicMock(name="add_user")
        mongodb_cluster.mongodb_setup_helpers.add_user = mock_add_user
        self.mongo_node.add_default_users()
        mock_add_user.assert_called_once_with(self.mongo_node, self.mongo_node.auth_settings)


class TestReplSet(unittest.TestCase):
    """ReplSet tests"""

    def setUp(self):
        self.repl_set_opts = {
            "cluster_type": "replset",
            "name": "rs",
            "mongod": [
                mongodb_setup_helpers.copy_obj(MONGOD_OPTS),
                mongodb_setup_helpers.copy_obj(MONGOD_OPTS),
            ],
        }
        self.config = DEFAULT_CONFIG
        self.delay_graph = MagicMock()
        repl_topology = ReplTopologyConfig(
            topology=self.repl_set_opts, root_config=self.config, delay_graph=self.delay_graph
        )
        self.replset = mongodb_cluster.ReplSet(repl_topology)

    def test_establish_delays(self):
        with mock.patch("dsi.common.mongodb_cluster.run_threads") as mock_run_threads:
            self.replset.establish_delays()
            mock_run_threads.assert_called_once()

    def test_shutdown(self):
        """Test shutdown."""
        with mock.patch("dsi.common.mongodb_cluster.run_threads") as mock_run_threads, mock.patch(
            "dsi.common.mongodb_cluster.partial"
        ) as mock_partial:
            mock_run_threads.return_value = [True]
            self.assertTrue(self.replset.shutdown(1))
            mock_partial.assert_has_calls(
                [
                    mock.call(self.replset.nodes[0].shutdown, 1, None),
                    mock.call(self.replset.nodes[1].shutdown, 1, None),
                ]
            )

        with mock.patch("dsi.common.mongodb_cluster.run_threads") as mock_run_threads, mock.patch(
            "dsi.common.mongodb_cluster.partial"
        ) as mock_partial:
            mock_run_threads.return_value = [True, False]
            self.assertFalse(self.replset.shutdown(2))
            mock_partial.assert_has_calls(
                [mock.call(mock.ANY, 2, None), mock.call(mock.ANY, 2, None)]
            )

    def test_destroy(self):
        """Test destroy."""
        with mock.patch("dsi.common.mongodb_cluster.run_threads") as mock_run_threads, mock.patch(
            "dsi.common.mongodb_cluster.partial"
        ) as mock_partial:
            mock_run_threads.return_value = [True]
            self.replset.destroy(1)
            mock_partial.assert_has_calls(
                [
                    mock.call(self.replset.nodes[0].destroy, 1),
                    mock.call(self.replset.nodes[1].destroy, 1),
                ]
            )

        with mock.patch("dsi.common.mongodb_cluster.run_threads") as mock_run_threads, mock.patch(
            "dsi.common.mongodb_cluster.partial"
        ) as mock_partial:
            mock_run_threads.return_value = [True, False]
            self.replset.destroy(2)
            mock_partial.assert_has_calls([mock.call(mock.ANY, 2), mock.call(mock.ANY, 2)])

    def test_highest_priority_node(self):
        """Test priority handling."""
        repl_set_opts = {
            "cluster_type": "replset",
            "name": "rs",
            "mongod": [
                mongodb_setup_helpers.copy_obj(MONGOD_OPTS),
                mongodb_setup_helpers.copy_obj(MONGOD_OPTS),
                mongodb_setup_helpers.copy_obj(MONGOD_OPTS),
                mongodb_setup_helpers.copy_obj(MONGOD_OPTS),
            ],
        }

        # All default priorities repl_topology = ReplTopologyConfig(repl_set_opts, root_config=DEFAULT_CONFIG, delay_graph=delay_graph)
        delay_graph = DelayGraph(repl_set_opts, DELAY_CONFIG["network_delays"]["clusters"][0])
        repl_topology = ReplTopologyConfig(
            repl_set_opts, root_config=DEFAULT_CONFIG, delay_graph=delay_graph
        )
        replset = mongodb_cluster.ReplSet(repl_topology)
        replset._set_explicit_priorities()
        self.assertEqual(replset.highest_priority_node(), replset.nodes[0])
        self.assertEqual(replset.topology_config.rs_conf_members[0]["priority"], 2)
        self.assertEqual(replset.topology_config.rs_conf_members[1]["priority"], 1)
        self.assertEqual(replset.topology_config.rs_conf_members[2]["priority"], 1)
        self.assertEqual(replset.topology_config.rs_conf_members[3]["priority"], 1)

        # Set one priority, others default
        repl_set_opts["mongod"][1]["rs_conf_member"]["priority"] = 5
        repl_topology = ReplTopologyConfig(
            repl_set_opts, root_config=DEFAULT_CONFIG, delay_graph=delay_graph
        )
        replset = mongodb_cluster.ReplSet(repl_topology)

        replset._set_explicit_priorities()
        self.assertEqual(replset.highest_priority_node(), replset.nodes[1])
        self.assertEqual(replset.topology_config.rs_conf_members[0]["priority"], 2)
        self.assertEqual(replset.topology_config.rs_conf_members[1]["priority"], 5)
        self.assertEqual(replset.topology_config.rs_conf_members[2]["priority"], 1)
        self.assertEqual(replset.topology_config.rs_conf_members[3]["priority"], 1)

        # Set all priorities explicitly in rs_conf_member
        repl_set_opts["mongod"][0]["rs_conf_member"]["priority"] = 1
        repl_set_opts["mongod"][1]["rs_conf_member"]["priority"] = 2
        repl_set_opts["mongod"][2]["rs_conf_member"]["priority"] = 3
        repl_set_opts["mongod"][3]["rs_conf_member"]["priority"] = 5
        repl_topology = ReplTopologyConfig(
            repl_set_opts, root_config=DEFAULT_CONFIG, delay_graph=delay_graph
        )
        replset = mongodb_cluster.ReplSet(repl_topology)

        replset._set_explicit_priorities()
        self.assertEqual(replset.highest_priority_node(), replset.nodes[3])
        self.assertEqual(replset.topology_config.rs_conf_members[0]["priority"], 1)
        self.assertEqual(replset.topology_config.rs_conf_members[1]["priority"], 2)
        self.assertEqual(replset.topology_config.rs_conf_members[2]["priority"], 3)
        self.assertEqual(replset.topology_config.rs_conf_members[3]["priority"], 5)

    def test_add_default_users(self):
        """
        Test that add_default_users adds users on the correct nodes in a replset.
        """
        mock_add_user = MagicMock(name="add_user")
        mongodb_cluster.mongodb_setup_helpers.add_user = mock_add_user
        self.replset.add_default_users()
        mock_add_user.assert_called_once_with(
            self.replset, self.replset.auth_settings, write_concern=len(self.replset.nodes)
        )


class TestShardedCluster(unittest.TestCase):
    """ReplSet tests"""

    def setUp(self):
        self.cluster_opts = {
            "cluster_type": "sharded_cluster",
            "disable_balancer": False,
            "configsvr_type": "csrs",
            "mongos": [mongodb_setup_helpers.copy_obj(MONGOD_OPTS)],
            "configsvr": [mongodb_setup_helpers.copy_obj(MONGOD_OPTS)],
            "shard": [
                {
                    "id": "shard",
                    "cluster_type": "replset",
                    "mongod": [
                        mongodb_setup_helpers.copy_obj(MONGOD_OPTS),
                        mongodb_setup_helpers.copy_obj(MONGOD_OPTS),
                    ],
                }
            ],
        }
        self.config = DEFAULT_CONFIG
        delay_graph = DelayGraph(self.cluster_opts, DELAY_CONFIG["network_delays"]["clusters"][0])
        sharded_topology = ShardedTopologyConfig(self.cluster_opts, self.config, delay_graph)
        self.cluster = mongodb_cluster.ShardedCluster(sharded_topology)

    def test_establish_delays(self):
        with mock.patch("dsi.common.mongodb_cluster.run_threads") as mock_run_threads:
            self.cluster.establish_delays()
            mock_run_threads.assert_called_once()

    def test_shutdown(self):
        """Test shutdown."""
        with mock.patch("dsi.common.mongodb_cluster.run_threads") as mock_run_threads, mock.patch(
            "dsi.common.mongodb_cluster.partial"
        ) as mock_partial:
            mock_run_threads.return_value = [True]
            self.assertTrue(self.cluster.shutdown(1))
            mock_partial.assert_has_calls(
                [
                    mock.call(self.cluster.shards[0].shutdown, 1, None),
                    mock.call(self.cluster.config_svr.shutdown, 1, None),
                    mock.call(self.cluster.mongoses[0].shutdown, 1, None),
                ]
            )

        with mock.patch("dsi.common.mongodb_cluster.run_threads") as mock_run_threads, mock.patch(
            "dsi.common.mongodb_cluster.partial"
        ) as mock_partial:
            mock_run_threads.return_value = [True, False]
            self.assertFalse(self.cluster.shutdown(2))
            mock_partial.assert_has_calls(
                [
                    mock.call(mock.ANY, 2, None),
                    mock.call(mock.ANY, 2, None),
                    mock.call(mock.ANY, 2, None),
                ]
            )

    def test_destroy(self):
        """Test destroy."""
        with mock.patch("dsi.common.mongodb_cluster.run_threads") as mock_run_threads, mock.patch(
            "dsi.common.mongodb_cluster.partial"
        ) as mock_partial:
            mock_run_threads.return_value = [True]
            self.cluster.config_svr.destroy = mock.MagicMock(name="config")
            self.cluster.destroy(1)
            mock_partial.assert_has_calls(
                [
                    mock.call(self.cluster.shards[0].destroy, 1),
                    mock.call(self.cluster.mongoses[0].destroy, 1),
                ],
                any_order=True,
            )
            self.cluster.config_svr.destroy.assert_called_once_with(1)

        with mock.patch("dsi.common.mongodb_cluster.run_threads") as mock_run_threads, mock.patch(
            "dsi.common.mongodb_cluster.partial"
        ) as mock_partial:
            mock_run_threads.return_value = [True, False]
            self.cluster.config_svr.destroy = mock.MagicMock(name="config")
            self.cluster.destroy(2)
            mock_partial.assert_has_calls(
                [mock.call(mock.ANY, 2), mock.call(mock.ANY, 2)], any_order=True
            )
            self.cluster.config_svr.destroy.assert_called_once_with(2)

    def test_add_default_users(self):
        """
        Test that add_default_users adds users on the correct clusters for a sharded cluster.
        """
        mock_add_user = MagicMock(name="add_user")
        mock_add_default_users = MagicMock("add_default_users")
        mongodb_cluster.mongodb_setup_helpers.add_user = mock_add_user
        mongodb_cluster.add_default_users = mock_add_default_users
        self.cluster.add_default_users()
        add_user_calls = [mock.call(self.cluster, self.cluster.auth_settings)]
        add_default_users_calls = [
            mock.call(self.cluster.config_svr, self.cluster.auth_settings)
        ] + [mock.call(shard, self.cluster.auth_settings) for shard in self.cluster.shards]
        mock_add_user.assert_has_calls(add_user_calls)
        mock_add_default_users(add_default_users_calls)


if __name__ == "__main__":
    unittest.main()
