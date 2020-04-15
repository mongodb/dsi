"""Unit tests for the rules module. Run using nosetests."""


import os
import unittest

from dateutil import parser as date_parser
from nose.tools import nottest

from dsi.libanalysis import readers
from dsi.libanalysis import rules
from dsi.libanalysis import util
from test_lib.fixture_files import FixtureFiles

FIXTURE_FILES = FixtureFiles()


class TestResourceRules(unittest.TestCase):
    """Test class evaluates correctness of resource sanity check rules.
    """

    def setUp(self):
        """Specifies the paths used to fetch JSON testing files. Additionally,
        sets up the common parameters for each operation being tested.
        """
        # parameters used in test cases
        self.path_ftdc_3node_repl = FIXTURE_FILES.fixture_file_path(
            "analysis", "linux_3node_replSet_p1.ftdc.metrics"
        )
        self.path_ftdc_3node_repl_initial_sync = FIXTURE_FILES.fixture_file_path(
            "analysis", "linux_3node_replSet_initial_sync.ftdc.metrics"
        )
        self.single_chunk_3node = self._first_chunk(self.path_ftdc_3node_repl)
        self.times_3node = self.single_chunk_3node[rules.FTDC_KEYS["time"]]
        self.members_3node = [b"0", b"1", b"2"]

        self.times_1node = [self.single_chunk_3node[rules.FTDC_KEYS["time"]][0]]
        length = len(self.times_1node)

        self.single_chunk_1node = {
            key: self.single_chunk_3node[key][0:length] for key in self.single_chunk_3node
        }
        self.members_1node = ["0"]

        path_ftdc_standalone = FIXTURE_FILES.fixture_file_path(
            "analysis", "core_workloads_wt.ftdc.metrics"
        )
        self.single_chunk_standalone = self._first_chunk(path_ftdc_standalone)
        self.times_standalone = self.single_chunk_standalone[rules.FTDC_KEYS["time"]]

        self.path_3shard_directory = FIXTURE_FILES.fixture_file_path(
            "analysis", "test_replset_resource_rules"
        )
        self.path_ftdc_repllag = FIXTURE_FILES.fixture_file_path("analysis", "test_repllag")

    @staticmethod
    def _first_chunk(ftdc_filepath):
        """Short helper to only use the first chunk of a file
        """
        for chunk in readers.read_ftdc(ftdc_filepath):
            return chunk

    def test_get_cache_max(self):
        """Test that we can get the configured cache size from a chunk
        """
        cache_max_3node = 31122784256
        observed = rules.get_configured_cache_size(self.single_chunk_3node)
        self.assertEqual(observed, cache_max_3node)

    def test_get_oplog_max(self):
        """Test that we can get the configured oplog size from a chunk
        """
        oplog_max_3node = 161061273600
        observed = rules.get_configured_oplog_size(self.single_chunk_3node)
        self.assertEqual(observed, oplog_max_3node)

    def test_get_repl_members(self):
        """Test that we can return a set of members from a 3-node replSet FTDC chunk
        """
        observed = rules.get_repl_members(self.single_chunk_3node)
        expected = [b"0", b"1", b"2"]
        self.assertEqual(observed, expected)

    def test_no_repl_members(self):
        """Test that we cannot return a set of members from a standalone FTDC chunk
        """
        observed = rules.get_repl_members(self.single_chunk_standalone)
        expected = []
        self.assertEqual(observed, expected)

    def test_below_cache_max_success(self):
        """Test expected success for case of current cache size below configured cache size
        """
        cache_max_3node = 31122784256
        observed = rules.below_configured_cache_size(
            self.single_chunk_3node, self.times_3node, cache_max_3node
        )
        expected = {}
        self.assertEqual(observed, expected)

    def test_below_cache_max_fail(self):
        """Test expected failure for case of current cache size being above configured cache size
        """
        configured_cache_size = 100
        observed = rules.below_configured_cache_size(
            self.single_chunk_3node, self.times_3node, configured_cache_size
        )
        expected = {
            "times": self.times_3node,
            "compared_values": [(32554,), (32554,)],
            "labels": ("current cache size (bytes)",),
            "additional": {"WT configured cache size (bytes)": configured_cache_size},
        }
        self.assertEqual(observed, expected)

    def test_below_oplog_max_success(self):
        """Test expected success for case of current oplog size below configured oplog size
        """
        oplog_max_3node = 161061273600
        observed = rules.below_configured_oplog_size(
            self.single_chunk_3node, self.times_3node, oplog_max_3node
        )
        expected = {}
        self.assertEqual(observed, expected)

    def test_below_oplog_max_fail(self):
        """Test expected failure for case of current oplog size above configured oplog size
        """
        configured_oplog_size = 10
        observed = rules.below_configured_oplog_size(
            self.single_chunk_3node, self.times_3node, configured_oplog_size
        )
        expected = {
            "times": self.times_3node,
            "compared_values": [(86,), (86,)],
            "labels": ("current oplog size (MB)",),
            "additional": {
                "WT configured max oplog size (MB)": configured_oplog_size,
                "rule": "current size <= (max size * 1.1)",
            },
        }
        self.assertEqual(observed, expected)

    def test_rule_not_applicable(self):
        """Test case where a rule does not apply to a variant
        """
        configured_oplog_size = 0
        observed = rules.below_configured_oplog_size(
            self.single_chunk_standalone, self.times_standalone, configured_oplog_size
        )
        expected = {}
        self.assertEqual(observed, expected)

    def test_max_connections_success(self):
        """Test expected success for current # connections below our specified upper bound
        """
        max_thread_level = 64
        observed = rules.max_connections(
            self.single_chunk_standalone, self.times_standalone, max_thread_level, []
        )
        expected = {}
        self.assertEqual(observed, expected)

    @nottest
    def helper_test_max_connections_equal(
        self,
        chunk,
        times,
        max_thread_level,
        repl_member_list,
        current_connections=42,
        expected=None,
    ):
        """Test expected success for current # connections below our specified upper bound: BF-8357
        """
        if expected is None:
            expected = {}
        key = rules.FTDC_KEYS["curr_connections"]
        length = len(chunk[key])
        chunk[key] = [current_connections] * length
        observed = rules.max_connections(chunk, times, max_thread_level, repl_member_list)
        self.assertEqual(observed, expected)

    def test_max_connections_lte(self):
        """Test expected success for current # connections less than or equal to specified upper
        bound: BF-8357
        """
        max_thread_level = 8
        self.helper_test_max_connections_equal(
            self.single_chunk_1node,
            self.times_1node,
            max_thread_level,
            self.members_1node,
            current_connections=41,
        )
        self.helper_test_max_connections_equal(
            self.single_chunk_1node, self.times_1node, max_thread_level, self.members_1node
        )

    def test_max_connections_greater(self):
        """Test expected success for current # connections above our specified upper bound: BF-8357
        """
        max_thread_level = 8
        self.helper_test_max_connections_equal(
            self.single_chunk_1node,
            self.times_1node,
            max_thread_level,
            self.members_1node,
            current_connections=43,
            expected={
                "times": self.times_1node,
                "compared_values": [(43,)],
                "labels": ("number of current connections",),
                "additional": {
                    "max thread level for this task": max_thread_level,
                    "connections between members? (4 * N)": 4,
                    "connections to MC and shell": 2,
                    "fudge_factor": 20,
                    "rule": "# connections <= (2 * max thread level + 2 + 4 + 20)",
                },
            },
        )

    # fudge factor behavior changes between 20 and 21 threads. lte 20 the fudge factor is 20,
    # above this value the fudge factor is 1.75 * max thread level.
    # PERF-1389 should fix this by identifying the tests (change stream and probably
    # snapshot_reads) with other source of connections (e.g. listener threads) and passing this
    # value to the max connections checks
    def test_max_20_connections_lte(self):
        """Test expected success for current # connections less than or equal to specified upper
        bound: BF-8357
        """
        max_thread_level = 20
        self.helper_test_max_connections_equal(
            self.single_chunk_1node,
            self.times_1node,
            max_thread_level,
            self.members_1node,
            current_connections=66,
        )
        self.helper_test_max_connections_equal(
            self.single_chunk_1node, self.times_1node, max_thread_level, self.members_1node
        )

    def test_max_20_connections_greater(self):
        """Test expected success for current # connections above our specified upper bound: BF-8357
        """
        max_thread_level = 20
        self.helper_test_max_connections_equal(
            self.single_chunk_1node,
            self.times_1node,
            max_thread_level,
            self.members_1node,
            current_connections=67,
            expected={
                "times": self.times_1node,
                "compared_values": [(67,)],
                "labels": ("number of current connections",),
                "additional": {
                    "max thread level for this task": max_thread_level,
                    "connections between members? (4 * N)": 4,
                    "connections to MC and shell": 2,
                    "fudge_factor": 20,
                    "rule": "# connections <= (2 * max thread level + 2 + 4 + 20)",
                },
            },
        )

    def test_max_21_connections_lte(self):
        """Test expected success for current # connections less than or equal to specified upper
        bound: BF-8357
        """
        max_thread_level = 21
        current_connections = 86
        self.helper_test_max_connections_equal(
            self.single_chunk_1node,
            self.times_1node,
            max_thread_level,
            self.members_1node,
            current_connections=current_connections,
        )
        self.helper_test_max_connections_equal(
            self.single_chunk_1node, self.times_1node, max_thread_level, self.members_1node
        )

    def test_max_21_connections_greater(self):
        """Test expected success for current # connections above our specified upper bound: BF-8357
        """
        max_thread_level = 21
        current_connections = 87
        fudge = 38
        self.helper_test_max_connections_equal(
            self.single_chunk_1node,
            self.times_1node,
            max_thread_level,
            self.members_1node,
            current_connections=current_connections,
            expected={
                "times": self.times_1node,
                "compared_values": [(current_connections,)],
                "labels": ("number of current connections",),
                "additional": {
                    "max thread level for this task": max_thread_level,
                    "connections between members? (4 * N)": 4,
                    "connections to MC and shell": 2,
                    "fudge_factor": fudge,
                    "rule": "# connections <= (2 * max thread level + 2 + 4 + {})".format(fudge),
                },
            },
        )

    # new test for a subsequent failure
    def test_max_241_connections_pass(self):
        """Test expected success for current # connections well above our specified upper bound
        """
        max_thread_level = 60
        current_connections = 242
        self.helper_test_max_connections_equal(
            self.single_chunk_3node,
            self.times_3node,
            max_thread_level,
            self.members_3node,
            current_connections=current_connections,
        )

    # this test will need to change if PERF-1389 is fixed
    def test_max_connections_fail(self):
        """Test expected failure for current # connections well above our specified upper bound
        """
        max_thread_level = 60
        current_connections = 243
        fudge = 108
        self.helper_test_max_connections_equal(
            self.single_chunk_3node,
            self.times_3node,
            max_thread_level,
            self.members_3node,
            current_connections=current_connections,
            expected={
                "times": self.times_3node,
                "compared_values": [(current_connections,), (current_connections,)],
                "labels": ("number of current connections",),
                "additional": {
                    "max thread level for this task": max_thread_level,
                    "connections between members? (4 * N)": 12,
                    "connections to MC and shell": 2,
                    "fudge_factor": fudge,
                    "rule": "# connections <= (2 * max thread level + 2 + 12 + {})".format(fudge),
                },
            },
        )

    def test_member_state_success(self):
        """Test expected success for members all in 'healthy' states
        """
        observed = rules.repl_member_state(
            self.single_chunk_3node, self.times_3node, self.members_3node, None
        )  # no test times
        expected = {}
        print(observed)
        self.assertEqual(observed, expected)

    def test_member_state_fail(self):
        """Test expected failure for member discovered in an 'unhealthy' state
        """
        rules.FLAG_MEMBER_STATES[2] = b"SECONDARY"
        observed = rules.repl_member_state(
            self.single_chunk_3node, self.times_3node, self.members_3node, None
        )  # no test times
        expected = {
            "members": {
                b"0": {
                    "times": self.times_3node,
                    "compared_values": [(b"SECONDARY",), (b"SECONDARY",)],
                    "labels": (b"member 0 state",),
                }
            }
        }
        self.assertEqual(observed, expected)
        del rules.FLAG_MEMBER_STATES[2]

    def test_member_state_success_initial_sync(self):
        """Test expected success for member discovered in an 'unhealthy' state but in a valid member state transition
        in initial sync
        """
        observed = rules.repl_member_state_initial_sync(self.path_ftdc_3node_repl_initial_sync)
        expected = {}
        self.assertEqual(observed, expected)

    def test_member_state_fail_initial_sync(self):
        """Test expected failure for member discovered in an 'unhealthy' state in initial sync
        """
        default_allowed_member_state_transitions = rules.ALLOWED_MEMBER_STATE_TRANSITIONS
        rules.ALLOWED_MEMBER_STATE_TRANSITIONS = []
        observed = rules.repl_member_state_initial_sync(self.path_ftdc_3node_repl_initial_sync)
        expected = {
            "members": {
                b"2": {
                    "times": [1583439530000],
                    "compared_values": [(b"RECOVERING",)],
                    "labels": (b"member 2 state",),
                }
            }
        }
        self.assertEqual(observed, expected)
        rules.ALLOWED_MEMBER_STATE_TRANSITIONS = default_allowed_member_state_transitions

    def test_allowed_state_transition(self):
        """Test check that an 'unhealthy' state in a valid member state transition sequence
        """
        member_states = [
            0,  # 0: b"STARTUP"
            5,  # 5: b"STARTUP2"
            3,  # 3: b"RECOVERING"
            2,  # 2: b"SECONDARY"
        ]
        index = 2
        self.assertTrue(rules._allowed_state_transition(member_states, index))

    def test_pri_not_found(self):
        """Test expected primary member cannot be found
        """
        primary = rules.find_primary(self.single_chunk_3node, self.members_3node)
        self.assertIsNone(primary)

    def test_pri_found(self):
        """Test expected primary member is found by chunk #4 (manually verified)
        """
        chunks_until_primary = 3
        for chunk in readers.read_ftdc(self.path_ftdc_3node_repl):
            primary = rules.find_primary(chunk, self.members_3node)
            if not chunks_until_primary:
                self.assertEqual(primary, b"0")
                break
            self.assertIsNone(primary)
            chunks_until_primary -= 1

    def test_ftdc_replica_lag_check_success(self):
        """Test expected success for repl set secondary member lag check
        """
        path_ftdc = os.path.join(self.path_3shard_directory, "metrics.3shard_p1_repl")
        perf_json = os.path.join(self.path_3shard_directory, "perf.json")
        test_times = util.get_test_times(perf_json)
        observed = rules.ftdc_replica_lag_check(path_ftdc, test_times)
        expected = []
        self.assertEqual(observed, expected)

    def test_ftdc_replica_lag_check_fail(self):
        """Test expected failure for repl set secondary member lag check

           The diagnostic.data file metrics.mongod.0 contains ftdc data from the primary on a
           3 node replica set. In the data there are 4 distinct periods where replication lag will
           be above the threshold of 15 seconds, as you can see from the `expected` output object
           below. Note that unittest-files/test_repllag/failure_message.txt.ok contains the
           human readable failure message that corresponds to these replication lag failures.
        """
        path_ftdc = os.path.join(self.path_ftdc_repllag, "metrics.mongod.0")
        perf_json = os.path.join(self.path_ftdc_repllag, "perf.json")

        test_times = util.get_test_times(perf_json)
        observed = rules.ftdc_replica_lag_check(path_ftdc, test_times)
        expected = [
            {
                "additional": {
                    "lag end threshold (s)": 2.0,
                    "lag start threshold (s)": 15.0,
                    "primary member": b"0",
                },
                "members": {
                    b"1": {
                        "compared_values": [
                            (16.0, "2017-05-31 16:54:42Z", 129.0, "2017-05-31 16:54:42Z", 120.0),
                            (17.0, "2017-05-31 16:59:23Z", 104.0, "2017-05-31 16:59:26Z", 99.0),
                            (16.0, "2017-05-31 17:04:33Z", 117.0, "2017-05-31 17:04:34Z", 110.0),
                            (16.0, "2017-05-31 17:09:13Z", 93.0, "2017-05-31 17:09:32Z", 12.0),
                        ],
                        "labels": (
                            "start value (s)",
                            "max time",
                            "max value (s)",
                            "end time",
                            "end value (s)",
                        ),
                        "report_all_values": True,
                        "times": [1496248949000, 1496249726000, 1496250019000, 1496250331000],
                    },
                    b"2": {
                        "compared_values": [
                            (16.0, "2017-05-31 16:54:03Z", 90.0, "2017-05-31 16:54:04Z", 82.0),
                            (16.0, "2017-05-31 16:58:53Z", 76.0, "2017-05-31 16:59:00Z", 72.0),
                            (16.0, "2017-05-31 17:03:53Z", 80.0, "2017-05-31 17:03:58Z", 77.0),
                            (16.0, "2017-05-31 17:08:53Z", 70.0, "2017-05-31 17:08:54Z", 62.0),
                        ],
                        "labels": (
                            "start value (s)",
                            "max time",
                            "max value (s)",
                            "end time",
                            "end value (s)",
                        ),
                        "report_all_values": True,
                        "times": [1496248967000, 1496249735000, 1496250027000, 1496250339000],
                    },
                },
            }
        ]
        self.assertEqual(observed, expected)

    def test_lag_no_perf_file(self):
        """Test expected success when no test times are specified
        """
        path_ftdc_3shard = os.path.join(self.path_3shard_directory, "metrics.3shard_p1_repl")
        observed = rules.ftdc_replica_lag_check(path_ftdc_3shard, None)
        expected = []
        self.assertEqual(observed, expected)


class TestFailureOutputFormatting(unittest.TestCase):
    """Test class checks resource sanity rules' error message formatting
    """

    def test_fail_collection_info(self):
        """Test expected output in _failure_collection when failure is detected
        """
        times = [1, 2, 3]
        compared_values = [(0, 1), (0, 3)]
        labels = ("label1", "label2")
        additional = {"random_info": 1}
        observed = rules.failure_collection(times, compared_values, labels, additional)
        expected = {
            "times": times,
            "compared_values": compared_values,
            "labels": labels,
            "additional": additional,
        }
        self.assertEqual(observed, expected)

    def test_fail_collection_empty(self):
        """Test expected output in _failure_collection when no failures detected
        """
        labels = ("label1", "label2")
        observed = rules.failure_collection([], [], labels)
        expected = {}
        self.assertEqual(observed, expected)


class TestLogAnalysisRules(unittest.TestCase):
    """Test class evaluates correctness of mongod.log check rules
    """

    def setUp(self):
        self.rules = {
            "bad_log_types": ["F", "E"],
            "bad_messages": [
                "starting an election",
                "election succeeded",
                "transition to primary",
                "posix_fallocate failed",
            ],
        }

    def test_is_log_line_bad(self):
        """Test `_is_log_line_bad()`."""

        bad_lines = [
            "2016-07-14T01:00:04.000+0000 F err-type foo bar baz",
            "2016-07-14T01:00:04.000+0000 E err-type foo bar baz",
            "2016-07-14T01:00:04.000+0000 L err-type elecTIon suCCEeded",
            "2016-07-14T01:00:04.000+0000 D err-type transition TO PRIMARY",
            "2016-07-14T01:00:04.000+0000 I err-type PosIx_FallocaTE FailEd",
            # First logv2 message. The message has format param `{rsConfig_getElectionTimeoutPeriod}`
            # but the attr is `rsConfig_getElectionTimeoutPeriodMillis` (probably a typo).
            '{"t":{"$date":"2020-03-02T05:37:29.666+0000"},"s":"I", "c":"ELECTION","id":4615652,'
            '"ctx":"ReplCoord-2","msg":"Starting an election, since we\'ve seen no PRIMARY in the past '
            '{rsConfig_getElectionTimeoutPeriod}","attr":{"rsConfig_getElectionTimeoutPeriodMillis":10000}}',
            # Second logv2 message. The `msg` itself is just "{}" but the params indicate failure
            # because it has "Starting an election" in the attr.
            '{"t":{"$date":"2020-03-02T06:32:06.307+0000"},"s":"I", "c":"ELECTION","id":0,'
            '"ctx":"ReplCoord-1","msg":"{}","attr":{"message":"Starting an election"}}',
        ]

        good_lines = [
            "2016-07-14T01:00:04.000+0000 L err-type nothing bad here",
            "2016-07-14T01:00:04.000+0000 L err-type or here",
            "2016-07-14T01:00:04.000+0000 E err-type ttl query execution for index",
            # Example logv2 message. The `msg` itself is just "{}".
            '{"t":{"$date":"2020-03-02T06:32:06.307+0000"},"s":"I", "c":"ELECTION","id":0,'
            '"ctx":"ReplCoord-1","msg":"{}","attr":{"message":"VoteRequester(term 1 dry run) '
            "received a yes vote from 10.2.0.200:27017; response message: { term: 1, voteGranted: true, "
            'reason: \\"\\", ok: 1.0, $clusterTime: { clusterTime: Timestamp(1583130713, 4), signature: '
            "{ hash: BinData(0, 0000000000000000000000000000000000000000), keyId: 0 } }, operationTime: "
            'Timestamp(1583130713, 4) }"}}',
        ]

        for line in bad_lines:
            self.assertTrue(rules.is_log_line_bad(line, self.rules))

        for line in good_lines:
            self.assertFalse(rules.is_log_line_bad(line, self.rules))

    def test_is_log_line_bad_task(self):
        """Test `_is_log_line_bad()` for specific tasks."""

        sometimes_bad_line = "2016-07-14T01:00:04.000+0000 D err-type transition TO PRIMARY"
        always_bad_line = "2016-07-14T01:00:04.000+0000 I err-type PosIx_FallocaTE FailEd"

        self.assertTrue(rules.is_log_line_bad(sometimes_bad_line, self.rules))
        self.assertTrue(
            rules.is_log_line_bad(always_bad_line, self.rules, task="industry_benchmarks")
        )
        self.assertFalse(
            rules.is_log_line_bad(
                sometimes_bad_line, self.rules, task="service_architecture_workloads"
            )
        )

        self.assertTrue(rules.is_log_line_bad(always_bad_line, self.rules))
        self.assertTrue(
            rules.is_log_line_bad(always_bad_line, self.rules, task="industry_benchmarks")
        )
        self.assertTrue(
            rules.is_log_line_bad(
                always_bad_line, self.rules, task="service_architecture_workloads"
            )
        )

    def test_is_log_line_bad_time(self):
        """Test `_is_log_line_bad()` when test times are specified."""

        test_times = [
            (
                date_parser.parse("2016-07-14T01:00:00.000+0000"),
                date_parser.parse("2016-07-14T01:10:00.000+0000"),
            ),
            (
                date_parser.parse("2016-07-14T03:00:00.000+0000"),
                date_parser.parse("2016-07-14T03:10:00.000+0000"),
            ),
            (
                date_parser.parse("2016-07-14T05:00:00.999+0000"),
                date_parser.parse("2016-07-14T05:10:00.000+0000"),
            ),
        ]

        # last 2 times are the same time as test start / end (i.e. the times are inclusive)
        bad_lines = [
            "2016-07-14T01:00:04.000+0000 F err-type message",
            "2016-07-14T01:09:00.000+0000 F err-type message",
            "2016-07-14T03:05:00.000+0000 F err-type message",
            "2016-07-14T05:00:00.999+0000 F err-type message",
            "2016-07-14T05:10:00.000+0000 F err-type message",
        ]

        # last 2 times are just before and after the test started
        bad_lines_to_ignore = [
            "2016-07-14T00:05:00.000+0000 F err-type message",
            "2016-07-14T02:00:00.000+0000 F err-type message",
            "2016-07-14T03:25:00.000+0000 F err-type message",
            "2016-07-14T05:00:00.998+0000 F err-type message",
            "2016-07-14T05:10:00.001+0000 F err-type message",
        ]

        for line in bad_lines:
            self.assertTrue(rules.is_log_line_bad(line, self.rules, test_times))

        for line in bad_lines_to_ignore:
            self.assertFalse(rules.is_log_line_bad(line, self.rules, test_times))


class TestDBCorrectnessRules(unittest.TestCase):
    """Test class evaluates correctness of DB correctness check rules.
    """

    def test_dbcorrect_success(self):
        """Test expected success in db correctness test log file parsing
        """
        log_dir = FIXTURE_FILES.fixture_file_path("analysis", "core_workloads_reports")
        expected_results = [
            {
                "status": "pass",
                "start": 0,
                "log_raw": ("\nPassed db-hash-check.core_workloads_reports JS test."),
                "test_file": "db-hash-check.core_workloads_reports",
                "exit_code": 0,
            },
            {
                "status": "pass",
                "start": 0,
                "log_raw": (
                    "\nPassed validate-indexes-and-collections.core_workloads_reports JS test."
                ),
                "test_file": ("validate-indexes-and-collections.core_workloads_reports"),
                "exit_code": 0,
            },
        ]
        observed_results = rules.db_correctness_analysis(log_dir)
        self.assertEqual(expected_results, observed_results)

    def test_dbcorrect_fail(self):
        """Test expected failure in db correctness test log file parsing
        """
        log_dir = FIXTURE_FILES.fixture_file_path("analysis", "test_db_correctness")
        raw_failure = (
            "\nFAILURE: (logfile `localhost--localhost`)\n"
            "2016-08-03T15:04:55.395-0400 E QUERY    [thread1] "
            "Error: Collection validation failed :\n@(shell eval):1:20\n"
            "@(shell eval):1:2\n\nFailed to run JS test on server [localhost], "
            "host [localhost]\n1"
        )
        expected_results = [
            {
                "status": "fail",
                "start": 0,
                "log_raw": raw_failure,
                "test_file": "validate-indexes-and-collections.test_db_correctness",
                "exit_code": 1,
            }
        ]
        observed_results = rules.db_correctness_analysis(log_dir)
        self.assertEqual(expected_results, observed_results)

    def test_dbcorrect_no_exit_code(self):
        """Test expected failure in db correctness test log file missing integer exit status
        """
        log_dir = FIXTURE_FILES.fixture_file_path("analysis", "test_db_correctness_exit_fail")
        raw_failure = (
            "\nFAILURE: logfile `localhost--localhost` did not record a valid exit "
            "code. Output:\n 2016-08-03T15:04:55.395-0400 E QUERY    [thread1] "
            "Error: Collection validation failed :\n@(shell eval):1:20\n"
            "@(shell eval):1:2\n\nFailed to run JS test on server [localhost], "
            "host [localhost]"
        )

        expected_results = [
            {
                "status": "fail",
                "start": 0,
                "log_raw": raw_failure,
                "test_file": ("validate-indexes-and-collections.test_db_correctness_exit_fail"),
                "exit_code": 1,
            }
        ]
        observed_results = rules.db_correctness_analysis(log_dir)
        self.assertEqual(expected_results, observed_results)

    def test_no_jstests_run(self):
        """Test expected empty result when no db correctness checks are made
        """
        log_dir = FIXTURE_FILES.fixture_file_path("analysis", "test_log_analysis")
        expected_results = []
        observed_results = rules.db_correctness_analysis(log_dir)
        self.assertEqual(expected_results, observed_results)


if __name__ == "__main__":
    unittest.main()
