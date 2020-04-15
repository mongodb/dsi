"""
Classes that represent and allow establishment of
delays between hosts.
"""


from collections import OrderedDict
from collections import namedtuple

from enum import Enum
from six.moves import range


class VersionFlag(Enum):
    """
    Class containing enums defining version flags.
    """

    DEFAULT = 1
    M60_LIKE = 2


Command = namedtuple("Command", ["command", "allow_fail", "error"])
SysConfig = namedtuple(
    "SysConfig",
    [
        "kernel_version",
        "tc_version",
        # Maximum allowed transmission rate. Required by tc.
        "rate",
    ],
)

# Dictionary mapping yml version flags to allowed systems.
ALLOWED_SYS_CONFIGS = {
    VersionFlag.DEFAULT: SysConfig(
        kernel_version="4.15.0-1044-aws",
        tc_version="4.15.0",
        # In the normal case, we use an absurdly high rate limit that is
        # never hit.
        rate="100tbit",
    ),
    VersionFlag.M60_LIKE: SysConfig(
        kernel_version="3.10.0-327.22.2.el7.x86_64",
        tc_version="4.11.0",
        # This kernel/tc version only allows this max rate.
        rate="4.2gbps",
    ),
}

# Constant representing the network interface to set delays on.
INTERFACE = "eth0"


class DelaySpec:
    """ Class representing a single delay edge specification. """

    def __init__(self, delayspec_config):
        self.delay_ms = delayspec_config["delay_ms"]
        self.jitter_ms = delayspec_config["jitter_ms"]


class EdgeSpec:
    """ Class representing a single edgewise delay specification. """

    def __init__(self, edge_config):
        self.node1 = edge_config["node1"]
        self.node2 = edge_config["node2"]
        self.delay = DelaySpec(edge_config["delay"])


class DelayNode:
    """ Class representing delays present at a given node. """

    def __init__(self, version_flag=VersionFlag.DEFAULT):
        """
        :param host: a Host object connecting this node to the host it represents.
        :param version_flag: A flag specifying which system version is expected.
        """
        self.delays = OrderedDict()  # OrderedDict makes unit testing easier
        self.sys_config = ALLOWED_SYS_CONFIGS[version_flag]

    def add(self, ip_address, delay_spec, defer_to_edgewise=False):
        """
        Adds a planned delay to this node.
        :param ip_address: string IP address to which traffic will be delayed
        :param delay_ms: integer of the delay in milliseconds
        :param jitter_ms: integer of the jitter in milliseconds
        :param defer_to_edgewise: false means we complain if there's a duplicate.
        True with the existence of a duplicate IP makes this operation effectless.
        """

        if ip_address in self.delays:
            if defer_to_edgewise:
                return
            raise DelayError(
                "Addition of delay failed: IP address already exists. Address: {ip_address}".format(
                    ip_address=ip_address
                )
            )

        if delay_spec.delay_ms < 0 or delay_spec.jitter_ms < 0:
            raise DelayError(
                (
                    "Addition of delay failed: invalid delay or jitter. Given "
                    "delay: {delay}. Given jitter: {jitter}"
                ).format(delay=str(delay_spec.delay_ms), jitter=str(delay_spec.jitter_ms))
            )

        self.delays[ip_address] = delay_spec

    def reset_delays(self, host):
        """
        Generates and executes commands needed to reset the host's tc settings.
        :param host: the Host object corresponding to this node.
        """
        # We assert the kernel and tc version to protect against changes in how tc works
        errors = []
        kernel_assert = _generate_kernel_assert(self.delays, self.sys_config.kernel_version)
        supported_kernel_version = host.run(kernel_assert.command)
        if not supported_kernel_version and not kernel_assert.allow_fail:
            errors.append(kernel_assert.error)

        tc_assert = _generate_tc_assert(self.delays, self.sys_config.tc_version)
        supported_tc_version = host.run(tc_assert.command)
        if not supported_tc_version and not tc_assert.allow_fail:
            errors.append(tc_assert.error)

        if supported_kernel_version and supported_tc_version:
            # Deleting the root qdisc will fail if it doesn't exist; that's okay.
            del_qdisc_command = ["bash", "-c", "'sudo tc qdisc del dev " + INTERFACE + " root'"]
            host.run(del_qdisc_command)
        elif errors:
            message = "\n".join([str(error) for error in errors])
            raise DelayError(message)

    def generate_delay_commands(self):
        """
        Generates all the tc commands needed to establish the delays.
        :return: a list of Commands, where each Command is a tuple of command string,
        whether that command is allowed to fail, and the exception to throw if it does.
        """
        commands = CommandList()

        if all([t.delay_ms == 0 and t.jitter_ms == 0 for t in self.delays.values()]):
            return commands.get_list()

        # Add the root qdisc
        add_root_qdisc_command = [
            "bash",
            "-c",
            ("'sudo tc qdisc add dev " + INTERFACE + " root handle 1: " "htb default 1'"),
        ]
        commands.append(
            add_root_qdisc_command,
            DelayError("Failed to add root qdisc. Command: {command}", add_root_qdisc_command[2]),
        )

        _generate_class_command(commands, 1, self.sys_config.rate)

        # We start at classid 2 because the root qdisc takes classid 0 and default gets 1.
        classid = 2
        for ip_address in self.delays:
            _generate_class_command(commands, classid, self.sys_config.rate)
            _generate_delay_command(commands, classid, ip_address, self.delays)
            _generate_filter_command(commands, classid, ip_address)
            classid += 1

        return commands.get_list()

    def establish_delays(self, host):
        """
        Establishes all described delays on the connected host. Raises an exception if
        commands fail that shouldn't.
        """
        for command in self.generate_delay_commands():
            if not host.run(command.command) and not command.allow_fail:
                raise command.error


# For more details on how linux traffic control works, check out:
# http://man7.org/linux/man-pages/man8/tc.8.html


def _generate_class_command(commands, classid, rate):
    command_str = (
        "'sudo tc class add dev {interface} parent 1: classid 1:{classid} "
        "htb rate {rate} prio 0'"
    ).format(interface=INTERFACE, classid=str(classid), rate=rate)
    command = ["bash", "-c", command_str]
    commands.append(command, DelayError("Execution of tc command {command} failed.", command))


def _generate_delay_command(commands, classid, ip_address, delays):
    command_str = (
        "'sudo tc qdisc add dev {interface} parent 1:{classid} netem delay {delay_ms}ms "
        "{jitter_ms}ms'"
    ).format(
        interface=INTERFACE,
        classid=classid,
        delay_ms=str(delays[ip_address].delay_ms),
        jitter_ms=str(delays[ip_address].jitter_ms),
    )
    command = ["bash", "-c", command_str]
    commands.append(command, DelayError("Execution of tc command {command} failed.", command))


def _generate_filter_command(commands, classid, ip_address):
    command_str = (
        "'sudo tc filter add dev {interface} protocol ip parent 1:0 prio 1 "
        "u32 match ip dst {ip_address} flowid 1:{classid}'"
    ).format(interface=INTERFACE, ip_address=ip_address, classid=classid)
    command = ["bash", "-c", command_str]
    commands.append(command, DelayError("Execution of tc command {command} failed.", command))


def _generate_kernel_assert(delays, expected_kernel_version):
    kernel_assert_command_str = '\'uname -r | cut -d "." -f 1 | grep -q "{major}"\''.format(
        major=expected_kernel_version.split(".")[0]
    )
    kernel_assert_command = ["bash", "-c", kernel_assert_command_str]

    # We only complain about bad kernel versions if we are actually setting delays.
    if all([t.delay_ms == 0 and t.jitter_ms == 0 for t in delays.values()]):
        return Command(kernel_assert_command, error=None, allow_fail=True)
    kernel_assert_error = DelayError(
        (
            "Trying to use `tc` to simulate network delays, "
            "but found an unexpected kernel version. Expected version {kernel}. "
            "This means the system image was recently upgraded, or that the wrong "
            "system configuration is specified in mongodb_setup.yml. Please set the "
            "version flag in the mongodb_setup.yml file to the correct value. Advanced users "
            "may modify the ALLOWED_SYS_CONFIGS variable at the top of delay.py in DSI to "
            "account for this system configuration and verify that tc works correctly."
        ).format(kernel=expected_kernel_version)
    )
    return Command(command=kernel_assert_command, error=kernel_assert_error, allow_fail=False)


def _generate_tc_assert(delays, expected_tc_version):
    tc_assert_command_str = (
        '\'yum info iproute | grep "Version" | cut -d ":" -f 2 | '
        'cut -d " " -f 2 | cut -d "." -f 1 '
        '| grep -q "{major}"\''
    ).format(major=expected_tc_version.split(".")[0])
    tc_assert_command = ["bash", "-c", tc_assert_command_str]

    # We only complain about bad tc versions if we are actually setting delays.
    if all([t.delay_ms == 0 and t.jitter_ms == 0 for t in delays.values()]):
        return Command(tc_assert_command, error=None, allow_fail=True)
    tc_assert_error = DelayError(
        (
            "Trying to use `tc` to simulate network delays, "
            "but found an unexpected tc version. Expected version {tc}. "
            "This means the system's packages were recently upgraded, or that the wrong "
            "system configuration is specified in mongodb_setup.yml. "
            "Please set the version flag in the mongodb_setup.yml file to the correct value. "
            "Advanced users may modify the ALLOWED_SYS_CONFIGS variable at the top of delay.py "
            "in DSI to account for this system configuration and verify that "
            "tc works correctly."
        ).format(tc=expected_tc_version)
    )
    return Command(command=tc_assert_command, error=tc_assert_error, allow_fail=False)


class CommandList:
    """ Mini class making it easier to manage command lists."""

    def __init__(self):
        self.commands = []

    def append(self, command, error=None, allow_fail=False):
        """
        Creates a Command object and appends it to the list of commands.
        :param command: A list of strings representing the command.
        :param error: The exception that is thrown if the command fails.
        :param allow_fail: Whether the command is allowed to fail without erroring.
        """
        self.commands.append(Command(command=command, error=error, allow_fail=allow_fail))

    def get_list(self):
        """
        :return: The list of commands that was built.
        """
        return self.commands


class DelayGraph:
    """
    Class representing a graph of delays.
    """

    # The workload client is common to all clusters.
    client_node = DelayNode()
    # We need a ConfigDict to set this IP, can be set externally.
    client_ip = "workload_client"

    def __init__(self, topology, delay_config, version_flag=VersionFlag.DEFAULT):
        """
        Extracts configuration information from the topology and delay_config dicts.
        :param topology: The topology ConfigDict for a single cluster.
        :param delay_config: The delay ConfigDict for a single cluster.
        :param version_flag: A flag specifying which system version is expected.
        """
        self.graph = {}

        self.version_flag = version_flag
        self._extract_delay_config(delay_config)
        self._initialize_graph(topology, False)
        self.graph[DelayGraph.client_ip] = DelayGraph.client_node

        self._set_edgewise_delays()
        self._set_default_delays()

    @staticmethod
    def from_topologies(topologies, delay_configs, version_flag=VersionFlag.DEFAULT):
        """
        Creates a DelayGraph for each topology.
        :param topologies: a list of topology ConfigDicts, which is the same
        length as 'delay_configs'
        :param delay_configs: a list of delay ConfigDicts, which is the same
        length as 'topologies'
        :param version_flag: A flag specifying which system version is expected.
        :return: a list of DelayGraph instances
        """
        return [
            DelayGraph(topologies[i], delay_configs[i], version_flag)
            for i in range(len(topologies))
        ]

    def get_node(self, ip_address):
        """
        Gets the DelayNode object corresponding to a given IP address.
        :param ip_address: the private IP address of the desired node.
        :return: the DelayNode object, with all delays added.
        """

        try:
            return self.graph[ip_address]
        except KeyError:
            raise DelayError(
                "Tried to retrieve node for {ip_address}, but that IP address has "
                "no delay specification."
            )

    def _initialize_graph(self, topology, is_standalone_list):
        """
        Reads the topology of a cluster and initializes the delay graph
        based on what nodes are present.
        :param topology: The topology ConfigDict for this cluster.
        :param is_standalone_list: Whether this 'topology' is just a
        list of standalone mongod configurations.
        """
        if is_standalone_list:
            for node in topology:
                private_ip = node["private_ip"]
                self.graph[private_ip] = DelayNode(self.version_flag)
            return

        if topology["cluster_type"] == "sharded_cluster":
            self._initialize_graph(topology["configsvr"], True)
            self._initialize_graph(topology["mongos"], True)
            for replset in topology["shard"]:
                self._initialize_graph(replset, False)
        elif topology["cluster_type"] == "replset":
            self._initialize_graph(topology["mongod"], True)
        elif topology["cluster_type"] == "standalone":
            private_ip = topology["private_ip"]
            self.graph[private_ip] = DelayNode(self.version_flag)

    def _extract_delay_config(self, delay_config):
        """
        Performs all actions needed to extract information from the delay ConfigDict.
        :param delay_config: A ConfigDict for a single cluster's delays.
        """
        self.default_delay = DelaySpec(delay_config["default"])
        self.edgewise_delays = [EdgeSpec(edge) for edge in delay_config.get("edges", [])]

    def _set_edgewise_delays(self):
        for edge in self.edgewise_delays:
            self.graph[edge.node1].add(edge.node2, edge.delay)
            self.graph[edge.node2].add(edge.node1, edge.delay)

    def _set_default_delays(self):
        """
        Sets the default delays for all nodes in the graph.
        """
        for ip_1 in self.graph:
            for ip_2 in self.graph:
                if ip_1 != ip_2:
                    # We defer to existing edgewise configurations with each addition.
                    self.graph[ip_1].add(ip_2, self.default_delay, defer_to_edgewise=True)


class DelayError(Exception):
    """
    Class representing an error in establishing delays.
    """

    def __init__(self, msg, command=""):
        """
        :param msg: The message associated with this error. Include `{command}` in the string
        if a command is also passed in.
        :param command: The tc command responsible for this error.
        """
        super(DelayError, self).__init__(
            msg if command == "" else msg.format(command=" ".join(command))
        )

        self.command = command


class HasDelay:
    """
    Abstract base class for things that can be delayed.
    Unless the delay functions are overridden, this function needs a host
    object to be set at some point. This isn't done at __init__ time to
    save resources.
    """

    def __init__(self, delay_node):
        self.delay_node = delay_node

    def reset_delays(self):
        """ Execute commands needed to reset a host's tc delays. """
        raise NotImplementedError()

    def establish_delays(self):
        """ Execute tc commands needed to establish delays between cluster hosts. """
        raise NotImplementedError()


def str_to_version_flag(flag_str):
    """
    Converts a string to the VersionFlag enum it represents.
    :param flag_str: A string representation of the version flag.
    """
    if flag_str == "default":
        return VersionFlag.DEFAULT
    if flag_str == "M60-like":
        return VersionFlag.M60_LIKE
    raise DelayError("Unrecognized version flag {flag}.".format(flag=flag_str))
