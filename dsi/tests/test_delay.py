import os
import shutil
import unittest
from contextlib import contextmanager

from mock import MagicMock, call, patch
from six.moves import range

from dsi.common import whereami
from dsi.common.config import ConfigDict
from dsi.delay import (
    DelayNode,
    DelayError,
    DelayGraph,
    DelaySpec,
    EdgeSpec,
    VersionFlag,
    str_to_version_flag,
)

BASIC_DELAY_CONFIG = {"default": {"delay_ms": 0, "jitter_ms": 0}}


class DelayNodeTestCase(unittest.TestCase):
    def test_empty_node(self):
        node = DelayNode()

        expected = []

        # We only test that the actual comman strings are the same
        # because the exception behavior is tested separately.
        actual = node.generate_delay_commands()
        self.assertEqual(len(actual), len(expected))
        for i, expect in enumerate(expected):
            self.assertEqual(actual[i].command, expect)

    def test_zero_delays(self):
        zero_delay_spec = DelaySpec({"delay_ms": 0, "jitter_ms": 0})
        node = DelayNode()
        node.add("fake_ip_str_1", zero_delay_spec)
        node.add("fake_ip_str_2", zero_delay_spec)
        node.add("fake_ip_str_3", zero_delay_spec)

        expected = []

        actual = node.generate_delay_commands()
        self.assertEqual(len(actual), len(expected))
        for i, expect in enumerate(expected):
            self.assertEqual(actual[i].command, expect)

    def test_one_nonzero_delay(self):
        node = DelayNode()
        zero_delay_spec = DelaySpec({"delay_ms": 0, "jitter_ms": 0})
        nonzero_delay_spec = DelaySpec({"delay_ms": 100, "jitter_ms": 5})
        node.add("fake_ip_str_1", zero_delay_spec)
        node.add("fake_ip_str_2", nonzero_delay_spec)
        node.add("fake_ip_str_3", zero_delay_spec)

        expected = [
            ["bash", "-c", "'sudo tc qdisc add dev eth0 root handle 1: htb default 1'"],
            [
                "bash",
                "-c",
                "'sudo tc class add dev eth0 parent 1: classid 1:1 htb rate 100tbit prio 0'",
            ],
            [
                "bash",
                "-c",
                "'sudo tc class add dev eth0 parent 1: classid 1:2 htb rate 100tbit prio 0'",
            ],
            ["bash", "-c", "'sudo tc qdisc add dev eth0 parent 1:2 netem delay 0ms 0ms'"],
            [
                "bash",
                "-c",
                "'sudo tc filter add dev eth0 protocol ip parent 1:0 prio 1 u32 match ip dst fake_ip_str_1 flowid 1:2'",
            ],
            [
                "bash",
                "-c",
                "'sudo tc class add dev eth0 parent 1: classid 1:3 htb rate 100tbit prio 0'",
            ],
            ["bash", "-c", "'sudo tc qdisc add dev eth0 parent 1:3 netem delay 100ms 5ms'"],
            [
                "bash",
                "-c",
                "'sudo tc filter add dev eth0 protocol ip parent 1:0 prio 1 u32 match ip dst fake_ip_str_2 flowid 1:3'",
            ],
            [
                "bash",
                "-c",
                "'sudo tc class add dev eth0 parent 1: classid 1:4 htb rate 100tbit prio 0'",
            ],
            ["bash", "-c", "'sudo tc qdisc add dev eth0 parent 1:4 netem delay 0ms 0ms'"],
            [
                "bash",
                "-c",
                "'sudo tc filter add dev eth0 protocol ip parent 1:0 prio 1 u32 match ip dst fake_ip_str_3 flowid 1:4'",
            ],
        ]

        actual = node.generate_delay_commands()
        self.assertEqual(len(actual), len(expected))
        for i, expect in enumerate(expected):
            self.assertEqual(actual[i].command, expect)

    def test_differing_delays(self):
        nonzero_delay_spec_1 = DelaySpec({"delay_ms": 200, "jitter_ms": 30})
        nonzero_delay_spec_2 = DelaySpec({"delay_ms": 100, "jitter_ms": 5})
        nonzero_delay_spec_3 = DelaySpec({"delay_ms": 500, "jitter_ms": 50})
        nonzero_delay_spec_4 = DelaySpec({"delay_ms": 10, "jitter_ms": 0})

        node = DelayNode()
        node.add("fake_ip_str_1", nonzero_delay_spec_1)
        node.add("fake_ip_str_2", nonzero_delay_spec_2)
        node.add("fake_ip_str_3", nonzero_delay_spec_3)
        node.add("fake_ip_str_4", nonzero_delay_spec_4)

        expected = [
            ["bash", "-c", "'sudo tc qdisc add dev eth0 root handle 1: htb default 1'"],
            [
                "bash",
                "-c",
                "'sudo tc class add dev eth0 parent 1: classid 1:1 htb rate 100tbit prio 0'",
            ],
            [
                "bash",
                "-c",
                "'sudo tc class add dev eth0 parent 1: classid 1:2 htb rate 100tbit prio 0'",
            ],
            ["bash", "-c", "'sudo tc qdisc add dev eth0 parent 1:2 netem delay 200ms 30ms'"],
            [
                "bash",
                "-c",
                "'sudo tc filter add dev eth0 protocol ip parent 1:0 prio 1 u32 match ip dst fake_ip_str_1 flowid 1:2'",
            ],
            [
                "bash",
                "-c",
                "'sudo tc class add dev eth0 parent 1: classid 1:3 htb rate 100tbit prio 0'",
            ],
            ["bash", "-c", "'sudo tc qdisc add dev eth0 parent 1:3 netem delay 100ms 5ms'"],
            [
                "bash",
                "-c",
                "'sudo tc filter add dev eth0 protocol ip parent 1:0 prio 1 u32 match ip dst fake_ip_str_2 flowid 1:3'",
            ],
            [
                "bash",
                "-c",
                "'sudo tc class add dev eth0 parent 1: classid 1:4 htb rate 100tbit prio 0'",
            ],
            ["bash", "-c", "'sudo tc qdisc add dev eth0 parent 1:4 netem delay 500ms 50ms'"],
            [
                "bash",
                "-c",
                "'sudo tc filter add dev eth0 protocol ip parent 1:0 prio 1 u32 match ip dst fake_ip_str_3 flowid 1:4'",
            ],
            [
                "bash",
                "-c",
                "'sudo tc class add dev eth0 parent 1: classid 1:5 htb rate 100tbit prio 0'",
            ],
            ["bash", "-c", "'sudo tc qdisc add dev eth0 parent 1:5 netem delay 10ms 0ms'"],
            [
                "bash",
                "-c",
                "'sudo tc filter add dev eth0 protocol ip parent 1:0 prio 1 u32 match ip dst fake_ip_str_4 flowid 1:5'",
            ],
        ]
        actual = node.generate_delay_commands()
        self.assertEqual(len(actual), len(expected))
        for i, expect in enumerate(expected):
            self.assertEqual(actual[i].command, expect)

    def test_establish_delays_runs_commands(self):
        mocked_host = MagicMock()
        mocked_host.run = MagicMock()
        mocked_host.run.return_value = True

        nonzero_delay_spec_1 = DelaySpec({"delay_ms": 700, "jitter_ms": 10})
        nonzero_delay_spec_2 = DelaySpec({"delay_ms": 300, "jitter_ms": 0})

        delay = DelayNode()
        delay.add("fake_ip_1", nonzero_delay_spec_1)
        delay.add("fake_ip_2", nonzero_delay_spec_2)
        delay.reset_delays(mocked_host)
        delay.establish_delays(mocked_host)

        expected_calls = [
            call(["bash", "-c", '\'uname -r | cut -d "." -f 1 | grep -q "4"\'']),
            call(
                [
                    "bash",
                    "-c",
                    '\'yum info iproute | grep "Version" | cut -d ":" -f 2 | cut -d " " -f 2 | cut -d "." -f 1 | grep -q "4"\'',
                ]
            ),
            call(["bash", "-c", "'sudo tc qdisc del dev eth0 root'"]),
            call(["bash", "-c", "'sudo tc qdisc add dev eth0 root handle 1: htb default 1'"]),
            call(
                [
                    "bash",
                    "-c",
                    "'sudo tc class add dev eth0 parent 1: classid 1:1 htb rate 100tbit prio 0'",
                ]
            ),
            call(
                [
                    "bash",
                    "-c",
                    "'sudo tc class add dev eth0 parent 1: classid 1:2 htb rate 100tbit prio 0'",
                ]
            ),
            call(["bash", "-c", "'sudo tc qdisc add dev eth0 parent 1:2 netem delay 700ms 10ms'"]),
            call(
                [
                    "bash",
                    "-c",
                    "'sudo tc filter add dev eth0 protocol ip parent 1:0 prio 1 u32 match ip dst fake_ip_1 flowid 1:2'",
                ]
            ),
            call(
                [
                    "bash",
                    "-c",
                    "'sudo tc class add dev eth0 parent 1: classid 1:3 htb rate 100tbit prio 0'",
                ]
            ),
            call(["bash", "-c", "'sudo tc qdisc add dev eth0 parent 1:3 netem delay 300ms 0ms'"]),
            call(
                [
                    "bash",
                    "-c",
                    "'sudo tc filter add dev eth0 protocol ip parent 1:0 prio 1 u32 match ip dst fake_ip_2 flowid 1:3'",
                ]
            ),
        ]

        self.assertEqual(mocked_host.run.call_count, len(expected_calls))
        mocked_host.run.assert_has_calls(expected_calls)

    def test_establish_delays_fails(self):
        mocked_host = MagicMock()

        def mocked_run(command):
            if command == [
                "bash",
                "-c",
                "'sudo tc qdisc add dev eth0 root handle 1: htb default 1'",
            ]:
                return False
            return True

        mocked_host.run = mocked_run

        nonzero_delay_spec_1 = DelaySpec({"delay_ms": 700, "jitter_ms": 10})
        nonzero_delay_spec_2 = DelaySpec({"delay_ms": 300, "jitter_ms": 0})

        delay = DelayNode()
        delay.add("fake_ip_1", nonzero_delay_spec_1)
        delay.add("fake_ip_2", nonzero_delay_spec_2)

        self.assertRaises(DelayError, delay.establish_delays, mocked_host)

    def test_assert_kernel_fails(self):
        mocked_host = MagicMock()

        def mocked_run(command):
            if command == ["bash", "-c", '\'uname -r | cut -d "." -f 1 | grep -q "4"\'']:
                return False
            return True

        mocked_host.run = mocked_run

        nonzero_delay_spec_1 = DelaySpec({"delay_ms": 400, "jitter_ms": 10})
        nonzero_delay_spec_2 = DelaySpec({"delay_ms": 100, "jitter_ms": 50})

        delay = DelayNode()
        delay.add("fake_ip_1", nonzero_delay_spec_1)
        delay.add("fake_ip_2", nonzero_delay_spec_2)

        self.assertRaises(DelayError, delay.reset_delays, mocked_host)

    def test_assert_kernel_fails_m60_like(self):
        mocked_host = MagicMock()

        def mocked_run(command):
            if command == ["bash", "-c", '\'uname -r | cut -d "." -f 1 | grep -q "3"\'']:
                return False
            return True

        mocked_host.run = mocked_run

        nonzero_delay_spec_1 = DelaySpec({"delay_ms": 400, "jitter_ms": 10})
        nonzero_delay_spec_2 = DelaySpec({"delay_ms": 100, "jitter_ms": 50})

        delay = DelayNode(VersionFlag.M60_LIKE)
        delay.add("fake_ip_1", nonzero_delay_spec_1)
        delay.add("fake_ip_2", nonzero_delay_spec_2)

        self.assertRaises(DelayError, delay.reset_delays, mocked_host)

    def test_already_defined_ip(self):
        delay = DelayNode()
        nonzero_delay_spec_1 = DelaySpec({"delay_ms": 700, "jitter_ms": 10})
        nonzero_delay_spec_2 = DelaySpec({"delay_ms": 300, "jitter_ms": 0})
        nonzero_delay_spec_3 = DelaySpec({"delay_ms": 200, "jitter_ms": 0})
        delay.add("fake_ip_1", nonzero_delay_spec_1)
        delay.add("fake_ip_2", nonzero_delay_spec_2)
        self.assertRaises(DelayError, delay.add, "fake_ip_1", nonzero_delay_spec_3)

    def test_negative_delay(self):
        delay = DelayNode()
        nonzero_delay_spec_1 = DelaySpec({"delay_ms": 50, "jitter_ms": 10})
        nonzero_delay_spec_2 = DelaySpec({"delay_ms": 10, "jitter_ms": 0})
        negative_delay_spec = DelaySpec({"delay_ms": -20, "jitter_ms": 5})
        delay.add("fake_ip_1", nonzero_delay_spec_1)
        delay.add("fake_ip_2", nonzero_delay_spec_2)
        self.assertRaises(DelayError, delay.add, "fake_ip_3", negative_delay_spec)

    def test_negative_jitter(self):
        delay = DelayNode()
        nonzero_delay_spec_1 = DelaySpec({"delay_ms": 10, "jitter_ms": 3})
        nonzero_delay_spec_2 = DelaySpec({"delay_ms": 10, "jitter_ms": 10})
        negative_jitter_spec = DelaySpec({"delay_ms": 50, "jitter_ms": -5})
        delay.add("fake_ip_1", nonzero_delay_spec_1)
        delay.add("fake_ip_2", nonzero_delay_spec_2)
        self.assertRaises(DelayError, delay.add, "fake_ip_3", negative_jitter_spec)


class DelayGraphTestCase(unittest.TestCase):
    def test_parse_standalone(self):
        topology = {"cluster_type": "standalone", "public_ip": "1.2.3.4", "private_ip": "10.2.0.1"}
        delay_graph = DelayGraph(topology, BASIC_DELAY_CONFIG)
        expected = ["10.2.0.1", "workload_client"]
        for private_ip in delay_graph.graph:
            self.assertTrue(private_ip in expected)
        self.assertEqual(len(expected), len(delay_graph.graph))

    def test_parse_replset(self):
        topology = {
            "cluster_type": "replset",
            "mongod": [
                {"public_ip": "1.2.3.4", "private_ip": "10.2.0.1"},
                {"public_ip": "2.3.4.5", "private_ip": "10.2.0.2"},
                {"public_ip": "3.4.5.6", "private_ip": "10.2.0.3"},
            ],
        }
        delay_graph = DelayGraph(topology, BASIC_DELAY_CONFIG)
        expected = ["10.2.0.1", "10.2.0.2", "10.2.0.3", "workload_client"]
        for private_ip in delay_graph.graph:
            self.assertTrue(private_ip in expected)
        self.assertEqual(len(expected), len(delay_graph.graph))

    def test_parse_sharded(self):
        topology = {
            "cluster_type": "sharded_cluster",
            "configsvr": [
                {"public_ip": "1.2.3.4", "private_ip": "10.2.0.1"},
                {"public_ip": "2.3.4.5", "private_ip": "10.2.0.2"},
                {"public_ip": "3.4.5.6", "private_ip": "10.2.0.3"},
            ],
            "mongos": [
                {"public_ip": "6.7.8.9", "private_ip": "10.2.0.4"},
                {"public_ip": "7.8.9.10", "private_ip": "10.2.0.5"},
                {"public_ip": "8.9.10.11", "private_ip": "10.2.0.6"},
            ],
            "shard": [
                {
                    "cluster_type": "replset",
                    "mongod": [
                        {"public_ip": "9.10.11.12", "private_ip": "10.2.0.7"},
                        {"public_ip": "10.11.12.13", "private_ip": "10.2.0.8"},
                        {"public_ip": "11.12.13.14", "private_ip": "10.2.0.9"},
                    ],
                },
                {
                    "cluster_type": "replset",
                    "mongod": [
                        {"public_ip": "12.13.14.15", "private_ip": "10.2.0.10"},
                        {"public_ip": "13.14.15.16", "private_ip": "10.2.0.11"},
                        {"public_ip": "14.15.16.17", "private_ip": "10.2.0.12"},
                    ],
                },
                {
                    "cluster_type": "replset",
                    "mongod": [
                        {"public_ip": "15.16.17.18", "private_ip": "10.2.0.13"},
                        {"public_ip": "16.17.18.19", "private_ip": "10.2.0.14"},
                        {"public_ip": "17.18.19.20", "private_ip": "10.2.0.15"},
                    ],
                },
            ],
        }
        delay_graph = DelayGraph(topology, BASIC_DELAY_CONFIG)
        expected = ["10.2.0.{num}".format(num=i) for i in range(1, 16)]
        expected.append("workload_client")
        for private_ip in delay_graph.graph:
            self.assertTrue(private_ip in expected)
        self.assertEqual(len(expected), len(delay_graph.graph))

    @patch("dsi.delay.DelayNode")
    def test_zero_default_delays(self, mocked_delay_node):
        topology = {
            "cluster_type": "replset",
            "mongod": [
                {"public_ip": "1.2.3.4", "private_ip": "10.2.0.1"},
                {"public_ip": "2.3.4.5", "private_ip": "10.2.0.2"},
                {"public_ip": "3.4.5.6", "private_ip": "10.2.0.3"},
            ],
        }

        DelayGraph.client_node = mocked_delay_node.return_value
        delay_graph = DelayGraph(topology, BASIC_DELAY_CONFIG)
        self.assertEqual(len(delay_graph.graph), 4)
        default_delay_spec = DelaySpec({"delay_ms": 0, "jitter_ms": 0})
        self.assertEqual(delay_graph.default_delay.delay_ms, default_delay_spec.delay_ms)
        self.assertEqual(delay_graph.default_delay.jitter_ms, default_delay_spec.jitter_ms)

        # Each IP gets called thrice: once for each of the other nodes.
        expected = [
            call("10.2.0.1", delay_graph.default_delay, defer_to_edgewise=True),
            call("10.2.0.1", delay_graph.default_delay, defer_to_edgewise=True),
            call("10.2.0.1", delay_graph.default_delay, defer_to_edgewise=True),
            call("10.2.0.2", delay_graph.default_delay, defer_to_edgewise=True),
            call("10.2.0.2", delay_graph.default_delay, defer_to_edgewise=True),
            call("10.2.0.2", delay_graph.default_delay, defer_to_edgewise=True),
            call("10.2.0.3", delay_graph.default_delay, defer_to_edgewise=True),
            call("10.2.0.3", delay_graph.default_delay, defer_to_edgewise=True),
            call("10.2.0.3", delay_graph.default_delay, defer_to_edgewise=True),
            call("workload_client", delay_graph.default_delay, defer_to_edgewise=True),
            call("workload_client", delay_graph.default_delay, defer_to_edgewise=True),
            call("workload_client", delay_graph.default_delay, defer_to_edgewise=True),
        ]
        self.assertEqual(mocked_delay_node.return_value.add.call_count, len(expected))
        mocked_delay_node.return_value.add.assert_has_calls(expected, any_order=True)

    @patch("dsi.delay.DelayNode")
    def test_nonzero_default_delays(self, mocked_delay_node):
        topology = {
            "cluster_type": "replset",
            "mongod": [
                {"public_ip": "1.2.3.4", "private_ip": "10.2.0.1"},
                {"public_ip": "2.3.4.5", "private_ip": "10.2.0.2"},
                {"public_ip": "3.4.5.6", "private_ip": "10.2.0.3"},
            ],
        }
        delay_config = {"default": {"delay_ms": 100, "jitter_ms": 10}, "edges": []}

        DelayGraph.client_node = mocked_delay_node.return_value
        delay_graph = DelayGraph(topology, delay_config)
        self.assertEqual(len(delay_graph.graph), 4)
        delay_spec = DelaySpec({"delay_ms": 100, "jitter_ms": 10})
        self.assertEqual(delay_graph.default_delay.delay_ms, delay_spec.delay_ms)
        self.assertEqual(delay_graph.default_delay.jitter_ms, delay_spec.jitter_ms)

        # Each IP gets called thrice: once for each of the other nodes.
        expected = [
            call("10.2.0.1", delay_graph.default_delay, defer_to_edgewise=True),
            call("10.2.0.1", delay_graph.default_delay, defer_to_edgewise=True),
            call("10.2.0.1", delay_graph.default_delay, defer_to_edgewise=True),
            call("10.2.0.2", delay_graph.default_delay, defer_to_edgewise=True),
            call("10.2.0.2", delay_graph.default_delay, defer_to_edgewise=True),
            call("10.2.0.2", delay_graph.default_delay, defer_to_edgewise=True),
            call("10.2.0.3", delay_graph.default_delay, defer_to_edgewise=True),
            call("10.2.0.3", delay_graph.default_delay, defer_to_edgewise=True),
            call("10.2.0.3", delay_graph.default_delay, defer_to_edgewise=True),
            call("workload_client", delay_graph.default_delay, defer_to_edgewise=True),
            call("workload_client", delay_graph.default_delay, defer_to_edgewise=True),
            call("workload_client", delay_graph.default_delay, defer_to_edgewise=True),
        ]
        self.assertEqual(mocked_delay_node.return_value.add.call_count, len(expected))
        mocked_delay_node.return_value.add.assert_has_calls(expected, any_order=True)

    @patch("dsi.delay.DelayNode")
    def test_zero_edgewise_delay(self, mocked_delay_node):
        topology = {
            "cluster_type": "replset",
            "mongod": [
                {"public_ip": "1.2.3.4", "private_ip": "10.2.0.1"},
                {"public_ip": "2.3.4.5", "private_ip": "10.2.0.2"},
                {"public_ip": "3.4.5.6", "private_ip": "10.2.0.3"},
            ],
        }
        delay_config = {
            "default": {"delay_ms": 100, "jitter_ms": 10},
            "edges": [
                {"node1": "10.2.0.1", "node2": "10.2.0.2", "delay": {"delay_ms": 0, "jitter_ms": 0}}
            ],
        }

        DelayGraph.client_node = mocked_delay_node.return_value
        delay_graph = DelayGraph(topology, delay_config)
        self.assertEqual(len(delay_graph.graph), 4)

        expected_edge_spec = EdgeSpec(
            {"node1": "10.2.0.1", "node2": "10.2.0.2", "delay": {"delay_ms": 0, "jitter_ms": 0}}
        )
        expected_delay_spec = expected_edge_spec.delay
        actual_edge_spec = delay_graph.edgewise_delays[0]
        actual_delay_spec = actual_edge_spec.delay
        self.assertEqual(actual_edge_spec.node1, expected_edge_spec.node1)
        self.assertEqual(actual_edge_spec.node2, expected_edge_spec.node2)
        self.assertEqual(actual_delay_spec.delay_ms, expected_delay_spec.delay_ms)
        self.assertEqual(actual_delay_spec.jitter_ms, expected_delay_spec.jitter_ms)

        # Each IP gets called once for each of the other nodes and the workload client.
        # The nodes along the edge each get called an additional time.
        expected = [
            call("10.2.0.1", actual_delay_spec),
            call("10.2.0.2", actual_delay_spec),
            call("10.2.0.1", delay_graph.default_delay, defer_to_edgewise=True),
            call("10.2.0.1", delay_graph.default_delay, defer_to_edgewise=True),
            call("10.2.0.1", delay_graph.default_delay, defer_to_edgewise=True),
            call("10.2.0.2", delay_graph.default_delay, defer_to_edgewise=True),
            call("10.2.0.2", delay_graph.default_delay, defer_to_edgewise=True),
            call("10.2.0.2", delay_graph.default_delay, defer_to_edgewise=True),
            call("10.2.0.3", delay_graph.default_delay, defer_to_edgewise=True),
            call("10.2.0.3", delay_graph.default_delay, defer_to_edgewise=True),
            call("10.2.0.3", delay_graph.default_delay, defer_to_edgewise=True),
            call("workload_client", delay_graph.default_delay, defer_to_edgewise=True),
            call("workload_client", delay_graph.default_delay, defer_to_edgewise=True),
            call("workload_client", delay_graph.default_delay, defer_to_edgewise=True),
        ]
        self.assertEqual(mocked_delay_node.return_value.add.call_count, len(expected))
        mocked_delay_node.return_value.add.assert_has_calls(expected, any_order=True)

    @patch("dsi.delay.DelayNode")
    def test_multiple_edgewise_delays(self, mocked_delay_node):
        topology = {
            "cluster_type": "replset",
            "mongod": [
                {"public_ip": "1.2.3.4", "private_ip": "10.2.0.1"},
                {"public_ip": "2.3.4.5", "private_ip": "10.2.0.2"},
                {"public_ip": "3.4.5.6", "private_ip": "10.2.0.3"},
            ],
        }
        delay_config = {
            "default": {"delay_ms": 100, "jitter_ms": 10},
            "edges": [
                {
                    "node1": "10.2.0.1",
                    "node2": "10.2.0.2",
                    "delay": {"delay_ms": 100, "jitter_ms": 10},
                },
                {
                    "node1": "10.2.0.2",
                    "node2": "10.2.0.3",
                    "delay": {"delay_ms": 10, "jitter_ms": 5},
                },
            ],
        }

        DelayGraph.client_node = mocked_delay_node.return_value
        delay_graph = DelayGraph(topology, delay_config)
        self.assertEqual(len(delay_graph.graph), 4)

        expected_edge_spec1 = EdgeSpec(
            {"node1": "10.2.0.1", "node2": "10.2.0.2", "delay": {"delay_ms": 100, "jitter_ms": 10}}
        )
        expected_delay_spec1 = expected_edge_spec1.delay
        actual_edge_spec1 = delay_graph.edgewise_delays[0]
        actual_delay_spec1 = actual_edge_spec1.delay
        self.assertEqual(actual_edge_spec1.node1, expected_edge_spec1.node1)
        self.assertEqual(actual_edge_spec1.node2, expected_edge_spec1.node2)
        self.assertEqual(actual_delay_spec1.delay_ms, expected_delay_spec1.delay_ms)
        self.assertEqual(actual_delay_spec1.jitter_ms, expected_delay_spec1.jitter_ms)

        expected_edge_spec2 = EdgeSpec(
            {"node1": "10.2.0.2", "node2": "10.2.0.3", "delay": {"delay_ms": 10, "jitter_ms": 5}}
        )
        expected_delay_spec2 = expected_edge_spec2.delay
        actual_edge_spec2 = delay_graph.edgewise_delays[1]
        actual_delay_spec2 = actual_edge_spec2.delay
        self.assertEqual(actual_edge_spec2.node1, expected_edge_spec2.node1)
        self.assertEqual(actual_edge_spec2.node2, expected_edge_spec2.node2)
        self.assertEqual(actual_delay_spec2.delay_ms, expected_delay_spec2.delay_ms)
        self.assertEqual(actual_delay_spec2.jitter_ms, expected_delay_spec2.jitter_ms)

        # Each IP gets called thrice: once for each of the other nodes.
        # The nodes along the edge each get called an additional time.
        expected = [
            call("10.2.0.1", actual_delay_spec1),
            call("10.2.0.2", actual_delay_spec1),
            call("10.2.0.2", actual_delay_spec2),
            call("10.2.0.3", actual_delay_spec2),
            call("10.2.0.1", delay_graph.default_delay, defer_to_edgewise=True),
            call("10.2.0.1", delay_graph.default_delay, defer_to_edgewise=True),
            call("10.2.0.1", delay_graph.default_delay, defer_to_edgewise=True),
            call("10.2.0.2", delay_graph.default_delay, defer_to_edgewise=True),
            call("10.2.0.2", delay_graph.default_delay, defer_to_edgewise=True),
            call("10.2.0.2", delay_graph.default_delay, defer_to_edgewise=True),
            call("10.2.0.3", delay_graph.default_delay, defer_to_edgewise=True),
            call("10.2.0.3", delay_graph.default_delay, defer_to_edgewise=True),
            call("10.2.0.3", delay_graph.default_delay, defer_to_edgewise=True),
            call("workload_client", delay_graph.default_delay, defer_to_edgewise=True),
            call("workload_client", delay_graph.default_delay, defer_to_edgewise=True),
            call("workload_client", delay_graph.default_delay, defer_to_edgewise=True),
        ]
        self.assertEqual(mocked_delay_node.return_value.add.call_count, len(expected))
        mocked_delay_node.return_value.add.assert_has_calls(expected, any_order=True)


# Validates every delay configuration yml.
class ConfigurationTestCase(unittest.TestCase):
    def test_validate_delays(self):
        blacklisted_configs = ["mongodb_setup.atlas.yml"]  # Some configs don't have topologies.
        directory = whereami.dsi_repo_path("configurations", "mongodb_setup")
        errors = []

        # There are a few files that aren't configuration files.
        names = [name for name in os.listdir(directory) if name.startswith("mongodb_setup")]

        # We need references to provisioning output
        infrastructure_provisioning = whereami.dsi_repo_path(
            "docs/config-specs/infrastructure_provisioning.out.yml"
        )
        with copied_file(infrastructure_provisioning, "infrastructure_provisioning.out.yml"):

            for conf_name in names:
                if conf_name in blacklisted_configs:
                    continue
                with copied_file(os.path.join(directory, conf_name), "mongodb_setup.yml"):
                    config = ConfigDict("mongodb_setup")
                    config.load()

                    topologies = config["mongodb_setup"]["topology"]
                    network_delays = config["mongodb_setup"]["network_delays"]
                    delay_configs = network_delays["clusters"]

                    try:
                        # The DelayNodes throw exceptions when given bad delays, so we
                        # can validate the configuration by simply constructing a DelayGraph
                        # pylint: disable=unused-variable
                        DelayGraph.client_ip = config["infrastructure_provisioning"]["out"][
                            "workload_client"
                        ][0]["private_ip"]

                        version_flag = str_to_version_flag(
                            network_delays.get("version_flag", "default")
                        )
                        DelayGraph.client_node = DelayNode(version_flag)
                        delays = DelayGraph.from_topologies(topologies, delay_configs, version_flag)
                    # pylint: disable=broad-except
                    except Exception as e:
                        errors.append(e)

        # Reset the delay graph's client variables.
        DelayGraph.client_node = DelayNode()
        DelayGraph.client_ip = "workload_client"
        self.assertEqual(errors, [])


@contextmanager
def copied_file(src, dest):
    shutil.copyfile(src, dest)
    try:
        yield dest
    finally:
        os.remove(dest)
