"""
Classes to control MongoDB clusters.
"""


import logging
import os
import signal
import sys
import time
from functools import partial

from six.moves import range
from six.moves import zip

from dsi.common import host_factory
from dsi.common import mongodb_setup_helpers
from dsi.common.mongo_config import NodeTopologyConfig, ReplTopologyConfig, ShardedTopologyConfig
from dsi.common.thread_runner import run_threads
from dsi.delay import HasDelay

# pylint: disable=too-many-instance-attributes

LOG = logging.getLogger(__name__)

# Remote files that need to be created.
# NB: these could/should come from defaults.yml
DEFAULT_MEMBER_PRIORITY = 1


def create_cluster(topology, delay_graph, config):
    """
    Create MongoNode, ReplSet, or ShardCluster from topology config
    :param topology: topology config to create - see MongoNode, ReplSet, ShardedCluster docs
    :param delay_graph: DelayGraph object for the cluster.
    :param config: root ConfigDict
    """
    cluster_type = topology["cluster_type"]
    LOG.info("creating topology: %s", cluster_type)
    if cluster_type == "standalone":
        node_topology = NodeTopologyConfig(
            topology=topology, root_config=config, delay_graph=delay_graph
        )
        return MongoNode(node_topology)
    if cluster_type == "replset":
        repl_topology = ReplTopologyConfig(
            topology=topology, root_config=config, delay_graph=delay_graph
        )
        return ReplSet(repl_topology)
    if cluster_type == "sharded_cluster":
        sharded_topology = ShardedTopologyConfig(
            topology=topology, root_config=config, delay_graph=delay_graph
        )
        return ShardedCluster(sharded_topology)
    LOG.fatal("unknown cluster_type: %s", cluster_type)
    return sys.exit(1)


class MongoCluster(HasDelay):
    """ Abstract base class for mongo clusters """

    def __init__(self, auth_settings, delay_node):
        """
        :param auth_settings: The username and password needed to connect to this cluster.

        """
        super(MongoCluster, self).__init__(delay_node)
        self.auth_settings = auth_settings

    def wait_until_up(self):
        """ Checks to make sure node is up and accessible"""
        raise NotImplementedError()

    def launch(self, initialize=True, use_numactl=True, enable_auth=False):
        """ Start the cluster """
        raise NotImplementedError()

    def shutdown(self, max_time_ms, auth_enabled, retries=20):
        """ Shutdown the cluster gracefully """
        raise NotImplementedError()

    def destroy(self, max_time_ms):
        """ Kill the cluster """
        raise NotImplementedError()

    def setup_host(self, restart_clean_db_dir=None, restart_clean_logs=None):
        """Ensures necessary files are setup

        :param restart_clean_db_dir Should we clean db dir on restart. If not specified, uses value
        from ConfigDict.
        :param restart_clean_logs   Should we clean logs and diagnostic data. If not specified,
        uses value from ConfigDict.
        """
        raise NotImplementedError()

    def run_mongo_shell(self, js_string, max_time_ms=None, dump_on_error=True):
        """
        Run JavaScript code in a mongo shell on the underlying host
        :param str js_string: the javascript to evaluate.
        For the max_time_ms parameter, see
            :method:`Host.exec_command`
        :param bool dump_on_error: print 100 lines of mongod.log on error
        :return: True if the mongo shell exits successfully
        """
        raise NotImplementedError()

    def add_default_users(self):
        """
        Add the default users.

        Required for authentication to work properly. Assumes that the cluster is already up and
        running. It must connect to the appropriate node before authentication is enabled. Once the
        users are added, the cluster is rebooted with authentication enabled and any connections
        from there on out must use the authentication string.
        """
        mongodb_setup_helpers.add_user(self, self.auth_settings)

    def __str__(self):
        """ String describing the cluster """
        raise NotImplementedError()

    def close(self):
        """Closes SSH connections to remote hosts."""
        raise NotImplementedError()


class MongoNode(MongoCluster):
    """Represents a mongo[ds] program on a remote host."""

    def __init__(self, topology):
        """
        :param topology: A NodeTopologyConfig object.
        """
        super(MongoNode, self).__init__(topology.auth_settings, topology.delay_node)

        self.topology_config = topology

        self.auth_enabled = False

        # Accessed via @property
        self._host = None

        self.delay_node = topology.delay_node

    @property
    def mongo_config(self):
        """
        syntax sugar around the mongo_config from the topology_config
        """
        return self.topology_config.mongo_config

    @property
    def net_config(self):
        """
        syntax sugar around the net_config from the topology_config
        """
        return self.topology_config.net_config

    # This is a @property versus a plain self.host var for 2 reasons:
    # 1. We don't need to be doing SSH stuff or be reading related
    #    configs if we never actually access the host var, and the host
    #    constructors eagerly do this stuff.
    # 2. It makes things slightly easier to test :)
    @property
    def host(self):
        """Access to remote or local host."""
        if self._host is None:
            host_info = self.net_config.compute_host_info()
            self._host = host_factory.make_host(host_info, use_tls=self.topology_config.use_tls)
        return self._host

    def reset_delays(self):
        """ Overrides the parent method to reset delays. """
        self.delay_node.reset_delays(self.host)

    def establish_delays(self):
        """ Overrides the parent method to establish delays. """
        self.delay_node.establish_delays(self.host)

    def wait_until_up(self):
        """ Checks to make sure node is up and accessible"""
        js_string = """
            i = 0
            while (db.serverStatus().ok != 1 && i < 20) {{
                print ("Waiting for node {} to come up");
                sleep(1000);
                i += 1; }}
            assert(db.serverStatus().ok == 1)"""
        i = 0
        while not self.run_mongo_shell(js_string.format(self.net_config.public_ip)) and i < 10:
            i += 1
            time.sleep(1)
        if i == 10:
            LOG.error("Node %s not up at end of wait_until_up", self.net_config.public_ip)
            return False
        return True

    def setup_host(self, restart_clean_db_dir=None, restart_clean_logs=None):
        self.host.kill_mongo_procs()

        setup_cmd_args = self.mongo_config.get_setup_command_args(
            restart_clean_db_dir, restart_clean_logs
        )
        commands = MongoNode._generate_setup_commands(setup_cmd_args)
        return self.host.run(commands)

    @staticmethod
    def _generate_setup_commands(setup_args):
        commands = []
        # Clean the logs and diagnostic data
        if setup_args["clean_logs"]:
            commands.append(["rm", "-rf", os.path.join(setup_args["logdir"], "*.log")])
            commands.append(["rm", "-rf", os.path.join(setup_args["logdir"], "core.*")])
            if not setup_args["is_mongos"]:
                commands.append(
                    ["rm", "-rf", os.path.join(setup_args["dbdir"], "diagnostic.data", "*")]
                )
        # Create the data/logs directories
        commands.append(["mkdir", "-p", setup_args["logdir"]])

        if setup_args["dbdir"] and setup_args["clean_db_dir"]:
            # Deleting diagnostic.data is governed by clean_logs. Don't delete it here.
            # When diagnostic.data doesn't exist, just create an empty one to avoid errors
            commands.append(["mkdir", "-p", os.path.join(setup_args["dbdir"], "diagnostic.data")])
            commands.append(["rm", "-rf", os.path.join(setup_args["logdir"], "diagnostic.data")])
            commands.append(
                ["mv", os.path.join(setup_args["dbdir"], "diagnostic.data"), setup_args["logdir"]]
            )

            commands.append(["rm", "-rf", setup_args["dbdir"]])

            if setup_args["use_journal_mnt"]:
                commands.append(["rm", "-rf", setup_args["journal_dir"]])

            commands.append(["mkdir", "-p", setup_args["dbdir"]])

            commands.append(
                ["mv", os.path.join(setup_args["logdir"], "diagnostic.data"), setup_args["dbdir"]]
            )

            # If not clean_db_dir assume that this has already been done.
            # Create separate journal directory and link to the database
            if setup_args["use_journal_mnt"]:
                commands.append(["mkdir", "-p", setup_args["journal_dir"]])
                commands.append(
                    [
                        "ln",
                        "-s",
                        setup_args["journal_dir"],
                        os.path.join(setup_args["dbdir"], "journal"),
                    ]
                )

        return commands

    # pylint: disable=unused-argument
    def launch_cmd(self, use_numactl=True, enable_auth=False):
        """Returns the command to start this node."""
        remote_file_name = "/tmp/mongo_port_{0}.conf".format(self.net_config.port)
        config = self.mongo_config.get_config(preserve_repl_auth=enable_auth)
        self.host.create_file(remote_file_name, config)
        self.host.run(["cat", remote_file_name])

        cmd = [
            os.path.join(self.mongo_config.bin_dir, self.mongo_config.mongo_program),
            "--config",
            remote_file_name,
        ]

        if use_numactl and self.mongo_config.numactl_prefix:
            if not isinstance(self.mongo_config.numactl_prefix, list):
                raise ValueError(
                    "numactl_prefix must be a list of commands, given: {}".format(
                        self.mongo_config.numactl_prefix
                    )
                )
            cmd = self.mongo_config.numactl_prefix + cmd

        LOG.debug("cmd is %s", str(cmd))
        return cmd

    def launch(self, initialize=True, use_numactl=True, enable_auth=False):
        """Starts this node.

        :param boolean initialize: Initialize the node. This doesn't do anything for the
                                     base node"""

        # initialize is explicitly not used for now for a single node. We may want to use it in
        # the future
        _ = initialize
        self.auth_enabled = enable_auth
        launch_cmd = self.launch_cmd(use_numactl=use_numactl, enable_auth=enable_auth)
        if not self.host.run(launch_cmd):
            LOG.error("failed launch command: %s", launch_cmd)
            self.dump_mongo_log()
            return False
        return self.wait_until_up()

    def run_mongo_shell(self, js_string, max_time_ms=None, dump_on_error=True):
        """
        Run JavaScript code in a mongo shell on the underlying host
        :param str js_string: the javascript to evaluate.
        For the max_time_ms parameter, see
            :method:`Host.exec_command`
        :param bool dump_on_error: print 100 lines of mongod.log on error
        :return: True if the mongo shell exits successfully
        """
        remote_file_name = "/tmp/mongo_port_{0}.js".format(self.net_config.port)
        # Value of auth_enabled changes during the lifetime of a MongoNode, so we have to tell
        # the host about auth settings on a case by case basis.
        if self.auth_enabled:
            self.host.mongodb_auth_settings = self.auth_settings
        else:
            self.host.mongodb_auth_settings = None

        if (
            self.host.exec_mongo_command(
                js_string,
                remote_file_name=remote_file_name,
                connection_string="localhost:" + str(self.net_config.port),
                max_time_ms=max_time_ms,
            )
            != 0
        ):
            # Some functions call this in a loop, so we may not want to dump the same log repeatedly
            if dump_on_error:
                self.dump_mongo_log()
            return False
        return True

    def dump_mongo_log(self):
        """Dump the mongo[ds] log file to the process log"""
        LOG.info("Dumping log for node %s", self.hostport_public())
        self.host.run(["tail", "-n", "100", self.mongo_config.log_path])

    def hostport_private(self):
        """Returns the string representation this host/port."""
        return "{0}:{1}".format(self.net_config.private_ip, self.net_config.port)

    connection_string_private = hostport_private

    def hostport_public(self):
        """Returns the string representation this host/port."""
        return "{0}:{1}".format(self.net_config.public_ip, self.net_config.port)

    connection_string_public = hostport_public

    def shutdown(self, max_time_ms, auth_enabled=None, retries=20):
        """
        Shutdown the node gracefully.

        For the max_time_ms parameter, see :method:`Host.exec_command`
        :return: True if shutdownServer command ran successfully.
        """
        if auth_enabled is not None:
            self.auth_enabled = auth_enabled
        for i in range(retries):
            # If there's a problem, don't dump 20x100 lines of log
            dump_on_error = i < 2
            try:
                self.run_mongo_shell(
                    'db.getSiblingDB("admin").shutdownServer({})'.format(
                        self.mongo_config.shutdown_options
                    ),
                    max_time_ms=max_time_ms,
                    dump_on_error=dump_on_error,
                )
            except Exception:  # pylint: disable=broad-except
                LOG.error(
                    "Error shutting down MongoNode at %s:%s",
                    self.net_config.public_ip,
                    self.net_config.port,
                )

            if self.host.run(["pgrep -l", "mongo"]):
                LOG.warning(
                    "Mongo %s:%s did not shutdown yet",
                    self.net_config.public_ip,
                    self.net_config.port,
                )
            else:
                return True
            time.sleep(1)
        return False

    def destroy(self, max_time_ms):
        """Kills the remote mongo program. First it sends SIGTERM every second for up to
        max_time_ms. It also always sends a SIGKILL and cleans up dbdir if this attribute is set.

        For the max_time_ms parameter, see
            :method:`Host.exec_command`
        :return: bool True if there are no processes matching 'mongo' on completion.
        """
        return_value = False
        try:
            return_value = self.host.kill_mongo_procs(
                signal_number=int(signal.SIGTERM), max_time_ms=max_time_ms
            )
        finally:
            if not return_value:
                LOG.warning(
                    "Mongo %s:%s did not shutdown cleanly! Will now SIGKILL and delete lock file.",
                    self.net_config.public_ip,
                    self.net_config.port,
                )
            # ensure the processes are dead and cleanup
            return_value = self.host.kill_mongo_procs()

            if self.mongo_config.dbdir:
                self.host.run(["rm", "-rf", os.path.join(self.mongo_config.dbdir, "mongod.lock")])
        return return_value

    def close(self):
        """Closes SSH connections to remote hosts."""
        self.host.close()

    def __str__(self):
        """String describing this node"""
        return "{}: {}".format(self.mongo_config.mongo_program, self.hostport_public())


class ReplSet(MongoCluster):
    """Represents a replica set on remote hosts."""

    def __init__(self, topology):
        """
        :param topology: A ReplTopologyConfig object describing this replica set.
        """
        super(ReplSet, self).__init__(topology.auth_settings, None)

        self.topology_config = topology

        self.rs_conf_members = []
        self.nodes = []
        for node_opt in self.topology_config.node_opts:
            self.nodes.append(MongoNode(node_opt))

    def highest_priority_node(self):
        """
        Returns the highest priority node.

        Requires all self.nodes[] to have a 'priority' field explicitly set, to work correctly.
        See :method:`ReplSet._set_explicit_priorities`
        """
        max_node = self.nodes[0]
        max_priority = -1
        for node, member in zip(self.nodes, self.topology_config.rs_conf_members):
            if "priority" in member and member["priority"] > max_priority:
                max_node = node
                max_priority = member["priority"]
        return max_node

    def reset_delays(self):
        """ Overrides grandparent method for resetting delays. """
        run_threads([node.reset_delays for node in self.nodes], daemon=True)

    def establish_delays(self):
        """ Overrides grandparent method for setting delays. """
        run_threads([node.establish_delays for node in self.nodes], daemon=True)

    def wait_until_up(self):
        """ Checks and waits for all nodes in replica set to be either PRIMARY or SECONDARY"""
        primary_js_string = """
            i = 0;
            while (!rs.isMaster().ismaster && i < 120) {{
                print("Waiting for expected primary to become master... attempt = " + i);
                sleep(1000);
                i += 1;
            }}
            assert(rs.isMaster().ismaster);
            rs.slaveOk();
            print("rs.status(): " + tojson(rs.status()));
            print("rs.config(): " + tojson(rs.config()));"""
        # Wait for Primary to be up
        primary = self.highest_priority_node()
        if not self.run_mongo_shell(primary_js_string):
            LOG.error("RS Node %s not up as primary", primary.net_config.public_ip)
            return False

        js_string = """
            i = 0
            while(!rs.isMaster().ismaster && !rs.isMaster().secondary && i < 20) {{
                print ("Waiting for node {} to come up");
                sleep(1000);
                i += 1; }}"""
        # Make sure all nodes are primary or secondary
        for node in self.nodes:
            if not node.run_mongo_shell(js_string.format(node.net_config.public_ip)):
                LOG.error("RS Node %s not up at end of wait_until_up", node.net_config.public_ip)
                return False
        return True

    def setup_host(self, restart_clean_db_dir=None, restart_clean_logs=None):
        return all(
            run_threads(
                [
                    partial(
                        node.setup_host,
                        restart_clean_db_dir=restart_clean_db_dir,
                        restart_clean_logs=restart_clean_logs,
                    )
                    for node in self.nodes
                ],
                daemon=True,
            )
        )

    def launch(self, initialize=True, use_numactl=True, enable_auth=False):
        """Starts the replica set.
        :param boolean initialize: Initialize the replica set"""
        if not all(
            run_threads(
                [
                    partial(
                        node.launch, initialize, use_numactl=use_numactl, enable_auth=enable_auth
                    )
                    for node in self.nodes
                ],
                daemon=True,
            )
        ):
            return False
        self._set_explicit_priorities()
        if initialize:
            LOG.info("Configuring replica set: %s", self.topology_config.name)
            if not self.run_mongo_shell(self.topology_config.get_init_code(self.nodes)):
                return False
        # Wait for all nodes to be up
        return self.wait_until_up()

    def _set_explicit_priorities(self):
        """To make other things easier, we set explicit priorities for all replica set nodes."""
        # Give the first host the highest priority so it will become
        # primary. This is the default behavior.
        if not "priority" in self.topology_config.rs_conf_members[0]:
            self.topology_config.rs_conf_members[0]["priority"] = DEFAULT_MEMBER_PRIORITY + 1
        for member in self.topology_config.rs_conf_members:
            if not "priority" in member:
                member["priority"] = DEFAULT_MEMBER_PRIORITY

    def run_mongo_shell(self, js_string, max_time_ms=None, dump_on_error=True):
        """
        Run JavaScript code in a mongo shell on the primary
        :param str js_string: the javascript to evaluate.
        For the max_time_ms parameter, see
            :method:`Host.exec_command`
        :param bool dump_on_error: print 100 lines of mongod.log on error
        :return: True if the mongo shell exits successfully
        """
        primary = self.highest_priority_node()
        return primary.run_mongo_shell(js_string, max_time_ms, dump_on_error)

    def add_default_users(self):
        """
        See :method:`MongoCluster.add_default_user`.
        On a replset we set the write conern to the total number of nodes in the replset to ensure
        the user is added to all nodes during setup.
        """
        mongodb_setup_helpers.add_user(self, self.auth_settings, write_concern=len(self.nodes))

    def shutdown(self, max_time_ms, auth_enabled=None, retries=20):
        """Shutdown gracefully
        For the max_time_ms parameter, see
            :method:`Host.exec_command`
        """
        return all(
            run_threads(
                [partial(node.shutdown, max_time_ms, auth_enabled) for node in self.nodes],
                daemon=True,
            )
        )

    def destroy(self, max_time_ms):
        """Kills the remote replica members.
        For the max_time_ms parameter, see
            :method:`Host.exec_command`
        """
        run_threads([partial(node.destroy, max_time_ms) for node in self.nodes], daemon=True)

    def close(self):
        """Closes SSH connections to remote hosts."""
        run_threads([node.close for node in self.nodes], daemon=True)

    def connection_string(self, hostport_fn):
        """Returns the connection string using the hostport_fn function"""
        rs_str = ["{0}/{1}".format(self.topology_config.name, hostport_fn(self.nodes[0]))]
        for node in self.nodes[1:]:
            rs_str.append(hostport_fn(node))
        return ",".join(rs_str)

    def connection_string_private(self):
        """Returns the string representation this replica set."""
        return self.connection_string(lambda node: node.hostport_private())

    def connection_string_public(self):
        """Returns the public string representation this replica set."""
        return self.connection_string(lambda node: node.hostport_public())

    def __str__(self):
        """String describing this ReplSet"""
        return "ReplSet: {}".format(self.connection_string_public())


class ShardedCluster(MongoCluster):
    """Represents a sharded cluster on remote hosts."""

    def __init__(self, topology):
        """
        :param topology: A ShardedTopologyConfig object representing this sharded cluster.
        """
        super(ShardedCluster, self).__init__(topology.auth_settings, None)

        self.sharded_config = topology

        self.config_svr = ReplSet(self.sharded_config.config_svr_topology)

        self.shards = []
        self.mongoses = []

        for node_topology in self.sharded_config.node_shards:
            self.shards.append(MongoNode(node_topology))
        for replset_topology in self.sharded_config.repl_shards:
            self.shards.append(ReplSet(replset_topology))

        self.sharded_config.create_mongos_topologies(self.config_svr.connection_string_private())
        for node_topology in self.sharded_config.mongos_topologies:
            self.mongoses.append(MongoNode(node_topology))

    def wait_until_up(self):
        """Checks to make sure sharded cluster is up and
        accessible. Specifically checking that the mognos's are up"""
        num_shards = len(self.shards)
        js_string = """
            db = db.getSiblingDB("config");
            i = 0;
            while (db.shards.find().itcount() < {0} && i < 10) {{
                print ("Waiting for mongos {1} to see {0} shards attempt= " + i);
                sleep(1000);
                i += 1; }}
            assert (db.shards.find().itcount() == {0}) """
        for mongos in self.mongoses:
            if not mongos.run_mongo_shell(
                js_string.format(num_shards, mongos.net_config.public_ip)
            ):
                LOG.error(
                    "Mongos %s does not see right number of shards at end of wait_until_up",
                    mongos.net_config.public_ip,
                )
                return False
        return True

    def setup_host(self, restart_clean_db_dir=None, restart_clean_logs=None):
        commands = [
            partial(
                self.config_svr.setup_host,
                restart_clean_db_dir=restart_clean_db_dir,
                restart_clean_logs=restart_clean_logs,
            )
        ]
        commands.extend(
            partial(
                shard.setup_host,
                restart_clean_db_dir=restart_clean_db_dir,
                restart_clean_logs=restart_clean_logs,
            )
            for shard in self.shards
        )
        commands.extend(
            partial(
                mongos.setup_host,
                restart_clean_db_dir=restart_clean_db_dir,
                restart_clean_logs=restart_clean_logs,
            )
            for mongos in self.mongoses
        )
        return all(run_threads(commands, daemon=True))

    def launch(self, initialize=True, use_numactl=True, enable_auth=False):
        """Starts the sharded cluster.

        :param boolean initialize: Initialize the cluster
        """
        LOG.info("Launching sharded cluster...")
        commands = [
            partial(
                self.config_svr.launch,
                initialize=initialize,
                use_numactl=False,
                enable_auth=enable_auth,
            )
        ]
        commands.extend(
            partial(
                shard.launch,
                initialize=initialize,
                use_numactl=use_numactl,
                enable_auth=enable_auth,
            )
            for shard in self.shards
        )
        commands.extend(
            partial(
                mongos.launch,
                initialize=initialize,
                use_numactl=use_numactl,
                enable_auth=enable_auth,
            )
            for mongos in self.mongoses
        )
        if not all(run_threads(commands, daemon=True)):
            return False
        if initialize:
            if not self._add_shards():
                return False
        if self.sharded_config.disable_balancer and not self.run_mongo_shell("sh.stopBalancer();"):
            return False
        return self.wait_until_up()

    def _add_shards(self):
        """Adds each shard to the cluster."""
        LOG.info("Configuring sharded cluster...")
        # Add shard to mongos
        js_add_shards = []
        for shard in self.shards:
            js_add_shards.append(
                'assert.commandWorked(sh.addShard("{0}"));'.format(
                    shard.connection_string_private()
                )
            )
        if not self.run_mongo_shell("\n".join(js_add_shards)):
            LOG.error("Failed to add shards!")
            return False
        return True

    def run_mongo_shell(self, js_string, max_time_ms=None, dump_on_error=True):
        """
        Run JavaScript code in a mongo shell on the cluster
        :param str js_string: the javascript to evaluate.
        For the max_time_ms parameter, see
            :method:`Host.exec_command`
        :param bool dump_on_error: print 100 lines of mongod.log on error
        :return: True if the mongo shell exits successfully
        """
        return self.mongoses[0].run_mongo_shell(js_string, max_time_ms, dump_on_error)

    def add_default_users(self):
        """
        See :method:`MongoCluster.add_default_user`.
        On a sharded cluster we must add the default user to the config servers and each of the
        shards, in addition to the mongos.
        """
        super(ShardedCluster, self).add_default_users()
        self.config_svr.add_default_users()
        for shard in self.shards:
            shard.add_default_users()

    def reset_delays(self):
        """ Overrides grandparent method for establishing delays. """
        all_nodes = self.shards + self.mongoses + [self.config_svr]
        run_threads([node.reset_delays for node in all_nodes], daemon=True)

    def establish_delays(self):
        """ Overrides grandparent method for establishing delays. """
        all_nodes = self.shards + self.mongoses + [self.config_svr]
        run_threads([node.establish_delays for node in all_nodes], daemon=True)

    def shutdown(self, max_time_ms, auth_enabled=None, retries=20):
        """Shutdown the mongodb cluster gracefully.
        For the max_time_ms parameter, see
            :method:`Host.exec_command`
        """
        commands = []
        commands.extend(partial(shard.shutdown, max_time_ms, auth_enabled) for shard in self.shards)
        commands.append(partial(self.config_svr.shutdown, max_time_ms, auth_enabled))
        commands.extend(
            partial(mongos.shutdown, max_time_ms, auth_enabled) for mongos in self.mongoses
        )
        return all(run_threads(commands, daemon=True))

    def destroy(self, max_time_ms):
        """Kills the remote cluster members.
        For the max_time_ms parameter, see
            :method:`Host.exec_command`
        """
        run_threads([partial(shard.destroy, max_time_ms) for shard in self.shards], daemon=True)
        self.config_svr.destroy(max_time_ms)
        run_threads([partial(mongos.destroy, max_time_ms) for mongos in self.mongoses], daemon=True)

    def close(self):
        """Closes SSH connections to remote hosts."""
        run_threads([shard.close for shard in self.shards], daemon=True)
        self.config_svr.close()
        run_threads([mongos.close for mongos in self.mongoses], daemon=True)

    def __str__(self):
        """String describing the sharded cluster"""
        description = ["ShardedCluster:", "configsvr: {}".format(self.config_svr)]
        for shard in self.shards:
            description.append("shard: {}".format(shard))
        for mongos in self.mongoses:
            description.append(str(mongos))
        return "\n".join(description)
