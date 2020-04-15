"""
Module of constants and rules used in our resource sanity checks. Used in post_run_check.py.
"""


import json
import logging
import math
import os
import re
from datetime import datetime

import six
from dateutil import parser as date_parser
from six.moves import range

from dsi.libanalysis import readers
from dsi.libanalysis import util

LOGGER = logging.getLogger(__name__)

# TODO: currently lots of globals in here. PERF-580 (unify post_run_check and perf_regression_check)
# will likely involve refactoring to address this global constants vs. config file issue.

CONSTANTS = {
    "sys-perf": {
        "default": {"threshold": 0.2, "thread_threshold": 0.3, "lag_threshold": 15.0, "ndays": 7.0},
        "linux-3-node-replSet-initialsync": {
            # from Judah: initial sync uses 16 threads to put data into the database
            "max_thread_level": 32.0
        },
    },
    "mongo-longevity": {
        "default": {"threshold": 0.25, "thread_threshold": 0.25, "lag_threshold": 15.0}
    },
}

# mongod.log analysis rules


def get_bad_messages(rules, task):
    """
    Get the bad messages for a certain task.

    :param task: the name of the task
    :return: a list of signatures of bad messages.
    """
    if task == "service_architecture_workloads":
        return ["posix_fallocate failed"]

    return rules["bad_messages"]


# Whitelisting message "Not starting an election": BF-4019
# Whitelisting message "older than oldest timestamp" until SERVER-38871 is done (TODO: TIG-1357)
MESSAGE_WHITELIST = [
    msg.lower()
    for msg in [
        "ttl query execution for index",
        "not starting an election",
        "older than oldest timestamp",
        "less than the oldest timestamp",
    ]
]

# Resource sanity check rules

FTDC_KEYS = {
    "cache_size": (b"serverStatus", b"wiredTiger", b"cache", b"bytes currently in the cache"),
    "heap_size": (b"serverStatus", b"tcmalloc", b"generic", b"heap_size"),
    "oplog_size": (b"local.oplog.rs.stats", b"size"),
    "curr_connections": (b"serverStatus", b"connections", b"current"),
    "max_cache_size": (b"serverStatus", b"wiredTiger", b"cache", b"maximum bytes configured"),
    "max_oplog_size": (b"local.oplog.rs.stats", b"maxSize"),
    "time": (b"start",),
    "repl_set_status": (b"replSetGetStatus", b"members", b"([0-9])+"),
}

FLAG_MEMBER_STATES = {3: b"RECOVERING", 6: b"UNKNOWN", 8: b"DOWN", 9: b"ROLLBACK", 10: b"REMOVED"}
STARTUP_MEMBER_STATES = {0: b"STARTUP", 5: b"STARTUP2"}
ALLOWED_MEMBER_STATE_TRANSITIONS = [{5: b"STARTUP2", 3: b"RECOVERING", 2: b"SECONDARY"}]

# cache size must be below (1 + CACHE_ALLOCATOR_OVERHEAD) * heap size.
CACHE_ALLOCATOR_OVERHEAD = 0.08

# current oplog size must be below (1 + WT_OPLOG_BUFFER)
WT_OPLOG_BUFFER = 0.10

# in seconds, when is the member lag too large?
REPL_MEMBER_LAG_THRESHOLD_S = 15.0
# if threshold was triggered, when do we consider the secondary caught up?
# see https://en.wikipedia.org/wiki/Hysteresis
REPL_MEMBER_LAG_RESET_S = 2.0

### end of configurable constants ##################################################################

MS = 1000.0
REPL_MEMBER_LAG_THRESHOLD_MS = REPL_MEMBER_LAG_THRESHOLD_S * MS
REPL_MEMBER_LAG_RESET_MS = REPL_MEMBER_LAG_RESET_S * MS


def is_log_line_bad(log_line, rules, test_times=None, task=None):
    """
    Return whether or not `log_line`, a line from a log file, is suspect. Only messages that were
    printed during the time a test was run (as specified in `test_times`) are considered, unless
    `test_times` is None.
    """

    log_line = log_line.strip()
    timestamp = err_type_char = log_msg = error = None

    try:
        log_json = json.loads(log_line)
    # Older versions of MongoDB don't support structured logging; fall back to using legacy log parsing
    except ValueError:
        line_components = log_line.split(" ", 3)
        if len(line_components) != 4:
            error = Exception("Invalid number of components in log")
        else:
            timestamp, err_type_char, _, log_msg = line_components
    except Exception as e:
        error = e
    else:
        try:
            timestamp = log_json["t"]["$date"]
            err_type_char = log_json["s"]
            log_msg = log_json["msg"]
            if "attr" in log_json:
                if log_msg == "{}":
                    log_msg = log_json["attr"]["message"]
                else:
                    try:
                        # Some log messages are inconsistent in their format strings
                        # versus their "attrs".
                        log_msg = log_msg.format(**log_json["attr"])
                    except KeyError:
                        pass
        except Exception as e:
            error = e

    if error is not None:
        LOGGER.warning("Couldn't parse log line. Error: `%s`. Line: `%s`", error, log_line)
        return False

    try:
        log_ts = date_parser.parse(timestamp)
    except ValueError as err:
        LOGGER.warning("Failed to parse timestamp from line `%s` with error `%s`", log_line, err)
        return False

    try:
        if test_times is not None and not any(start <= log_ts <= end for start, end in test_times):
            return False
    except TypeError as err:
        LOGGER.warning("Failed timestamp comparison. Log_line is %s", log_line)

    log_msg = log_msg.lower()
    if any(whitelist_msg in log_msg for whitelist_msg in MESSAGE_WHITELIST):
        return False

    return err_type_char in rules["bad_log_types"] or any(
        bad_msg in log_msg for bad_msg in get_bad_messages(rules, task)
    )


def ftdc_date_parse(time_in_s):
    """Helper to convert timestamps in s to human-readable format. Matches formatting in the
    timeseries web tool

    :type time_in_s: int
    :rtype: str
    """
    return datetime.utcfromtimestamp(time_in_s).strftime("%Y-%m-%d %H:%M:%SZ")


def failure_collection(
    failure_times, compared_values, labels, other_rule_info=None, report_all_values=False
):
    """Helper function to standardize the dictionary data structure that stores failure information.
    TODO: Each rule currently needs to initialize variables to collect the following parameters.
          Currently, this means any modification to the structure requires code updates in
          every rule function. I've thought about designing a general "rule framework" function
          where you pass in a custom comparison function, but wanted to hold off in case
          there were other suggestions for improving this design.

    :param list[int] failure_times: times (in ms) where failures occurred.
    :param list[tuple(*int)] compared_values: values that failed the resource check
    :param tuple labels: values in each tuple need to have labels to generate informative failure
                         messages
    :param dict other_rule_info: a dict containing any additional information we need to include
                                 in a failure message.
    :param bool print_all_values: Flag the failure data so that all compared_values are reported.
                                  This is used e.g. for repl lag, where each failure is different,
                                  rather than log messages, which tend to be very similar.
    :rtype: dict
    """
    if not failure_times:
        return {}
    rule_info = {}
    rule_info["times"] = failure_times
    rule_info["compared_values"] = compared_values
    rule_info["labels"] = labels
    if other_rule_info:
        rule_info["additional"] = other_rule_info
    if report_all_values:
        rule_info["report_all_values"] = True
    return rule_info


def _fetch_constant(chunk, key):
    if key in chunk:
        return chunk[key][0]
    return None


# Some constants can be fetched from the FTDC data. Find the first occurrence of these metrics in
# the FTDC chunks and use them accordingly.
def get_configured_cache_size(chunk):
    """Helper function to fetch maximum cache size value from a chunk

    :param collection.OrderedDict chunk: FTDC JSON chunk
    :rtype: int|None if chunk does not contain the needed key.
    """
    return _fetch_constant(chunk, FTDC_KEYS["max_cache_size"])


def get_configured_oplog_size(chunk):
    """Helper function to fetch maximum oplog size value from a chunk

    :param collection.OrderedDict chunk: FTDC JSON chunk
    :rtype: int|None if chunk does not contain the needed key.
    """
    return _fetch_constant(chunk, FTDC_KEYS["max_oplog_size"])


def get_repl_members(chunk):
    """Helper function to fetch a list of members with available repl set status information.

    :param collection.OrderedDict chunk: FTDC JSON chunk
    :rtype: list[str]
    """
    match_on_member_key = b";".join(FTDC_KEYS["repl_set_status"])
    members = set()
    for key in chunk:
        re_key = b";".join(key)
        match = re.match(match_on_member_key, re_key)
        if match:
            member = match.group(1)
            members.add(member)
    member_list = list(sorted(members))
    return member_list


# Map each of the helper functions to the parameter their return values will correspond to in the
# resource rules.
FETCH_CONSTANTS = {
    "configured_cache_size": get_configured_cache_size,
    "configured_oplog_size": get_configured_oplog_size,
    "repl_member_list": get_repl_members,
}


def below_configured_cache_size(chunk, times, configured_cache_size):
    """Is the current cache size below (1+CACHE_ALLOCATOR_OVERHEAD) * WT configured cache size?

    :param collection.OrderedDict chunk: FTDC JSON chunk
    :param list[int] times: the time at which each metric value was collected
    :param int configured_cache_size: specified cache size configuration in bytes
    :rtype: dict
    """
    if FTDC_KEYS["cache_size"] not in chunk:
        return {}

    cache_size_values = chunk[FTDC_KEYS["cache_size"]]

    failure_times = []
    labels = ("current cache size (bytes)",)
    compared_values = []
    additional = {"WT configured cache size (bytes)": configured_cache_size}

    for index, cache_size in enumerate(cache_size_values):
        if cache_size > (1 + CACHE_ALLOCATOR_OVERHEAD) * configured_cache_size:
            failure_times.append(times[index])
            compared_values.append((cache_size,))
    return failure_collection(failure_times, compared_values, labels, additional)


def max_connections(chunk, times, max_thread_level, repl_member_list):
    """Does the total number of connections remain below some expected limit?
    NOTES:
      - This rule is NOT applied to the sharded variant. From discussion, it is difficult to
        upper bound the # of connections on a sharded cluster.
      - In the future, we should think about how to account for mixed workloads, specific tests,
        and how the expected # of connections differs for primaries vs. secondaries

    :param collection.OrderedDict chunk: FTDC JSON chunk
    :param list[int] times: the time at which each metric value was collected
    :param int max_thread_level: the maximum thread level that is specified in the whole task
    :param list[str]: for replSets, the upper bound depends on the number of members
    :rtype: dict
    """
    if FTDC_KEYS["curr_connections"] not in chunk:
        return {}
    curr_connection_values = chunk[FTDC_KEYS["curr_connections"]]

    if not repl_member_list:  # standalone
        upper_bound_factor = 0
    else:
        upper_bound_factor = 4 * len(repl_member_list)

    # TODO: fix this as part of PERF-1389
    fudge_factor = 20
    if max_thread_level > fudge_factor:
        fudge_factor = int(math.ceil(max_thread_level * 1.8))
    failure_times = []
    labels = ("number of current connections",)
    compared_values = []
    additional = {
        "max thread level for this task": max_thread_level,
        "connections between members? (4 * N)": upper_bound_factor,
        "connections to MC and shell": 2,
        "fudge_factor": fudge_factor,
        "rule": "# connections <= (2 * max thread level + 2 + {0} + {1})".format(
            upper_bound_factor, fudge_factor
        ),
    }
    threshold = (max_thread_level * 2) + 2 + upper_bound_factor + fudge_factor
    for index, num_connections in enumerate(curr_connection_values):
        if num_connections > threshold:
            failure_times.append(times[index])
            compared_values.append((num_connections,))
    return failure_collection(failure_times, compared_values, labels, additional)


def below_configured_oplog_size(chunk, times, configured_oplog_size):
    """Is the current oplog size below (1 + WT_OPLOG_BUFFER) * configured oplog max size?

    :param collection.OrderedDict chunk: FTDC JSON chunk
    :param list[int] times: the time at which each metric value was collected
    :param int configured_oplog_size: specified oplog size configuration in MB
    :rtype: dict
    """
    if FTDC_KEYS["oplog_size"] not in chunk:
        return {}
    oplog_size_values = chunk[FTDC_KEYS["oplog_size"]]
    upper_bound_factor = 1 + WT_OPLOG_BUFFER

    failure_times = []
    labels = ("current oplog size (MB)",)
    compared_values = []
    additional = {
        "WT configured max oplog size (MB)": configured_oplog_size,
        "rule": "current size <= (max size * {0})".format(upper_bound_factor),
    }

    for index, oplog_size in enumerate(oplog_size_values):
        if oplog_size > configured_oplog_size * upper_bound_factor:
            failure_times.append(times[index])
            compared_values.append((oplog_size,))
    return failure_collection(failure_times, compared_values, labels, additional)


def repl_member_state(chunk, times, repl_member_list, test_times=None):
    """Do any of the members ever go into a "bad" state? (i.e. RECOVERING; see FLAG_MEMBER_STATES.)

    :param collection.OrderedDict chunk: FTDC JSON chunk
    :param list[int] times: the time at which each metric value was collected
    :param list[bytearray] repl_member_list: list of replica set members in this variant
    :param list[(datetime, datetime)] test_times: list of (start, end) test times.
        Use this to ignore problematic member states if it doesn't occur during a test run.
    :rtype: dict
    """
    # We want to disregard FTDC data collected when a test is not being run.
    # This whitelists the indices where metrics were collected for a test workload.
    test_run_indices = _get_whitelist_from_test_times(chunk, test_times)

    member_states = {}
    for member in repl_member_list:
        member_state_key = (b"replSetGetStatus", b"members", member, b"state")
        if member_state_key not in chunk:
            continue
        member_state_values = chunk[member_state_key]

        failure_times = []
        labels = (b"member " + member + b" state",)
        compared_values = []

        for index in test_run_indices:
            state = member_state_values[index]
            if state in FLAG_MEMBER_STATES:
                failure_times.append(times[index])
                compared_values.append((FLAG_MEMBER_STATES[state],))
        failure = failure_collection(failure_times, compared_values, labels)
        if failure:
            member_states[member] = failure
    if member_states:
        return {"members": member_states}
    return {}


def _allowed_state_transition(member_states, index):
    """Helper function to check that an 'unhealthy' state is in a valid member state transition

    :param list[int] member_states: list of replica set member states
    :param int index: current state index in list
    :rtype: bool
    """
    for sequence_dict in ALLOWED_MEMBER_STATE_TRANSITIONS:
        sequence = list(sequence_dict)
        state = member_states[index]
        if state in sequence:
            start = index - sequence.index(state)
            stop = start + len(sequence)
            if start < 0:
                continue
            if member_states[start:stop] == sequence:
                return True
    return False


def repl_member_state_initial_sync(path_to_ftdc_file, test_times=None):
    """Do any of the members ever go into a "bad" state? (i.e. RECOVERING; see FLAG_MEMBER_STATES.)
        Except allowed transitions in initial sync (see VALID_MEMBER_STATE_TRANSITIONS)

    :param str path_to_ftdc_file: path to a FTDC metrics file
    :param list[(datetime, datetime)] test_times: list of (start, end) test times.
        Use this to ignore problematic member states if it doesn't occur during a test run.
    :rtype: dict
    """
    repl_member_list = []
    repl_member_states = {}

    # Collect full members' state transition sequence from full FTDC data
    for chunk in readers.read_ftdc(path_to_ftdc_file):
        if not repl_member_list:
            repl_member_list = get_repl_members(chunk)
            if not repl_member_list:
                continue
        times = chunk[FTDC_KEYS["time"]]
        test_run_indices = _get_whitelist_from_test_times(chunk, test_times)
        chunk_member_states = {}

        for member in repl_member_list:
            member_state_key = (b"replSetGetStatus", b"members", member, b"state")
            if member_state_key not in chunk:
                continue
            member_state_values = chunk[member_state_key]
            state_times = []
            states = []

            for index in test_run_indices:
                state_times.append(times[index])
                states.append(member_state_values[index])

            if state_times and states:
                chunk_member_states[member] = {}
                chunk_member_states[member]["state_times"] = state_times
                chunk_member_states[member]["states"] = states

        if chunk_member_states:
            for member, member_states in chunk_member_states.items():
                if member in repl_member_states:
                    repl_member_states[member]["state_times"].extend(member_states["state_times"])
                    repl_member_states[member]["states"].extend(member_states["states"])
                else:
                    repl_member_states[member] = member_states

    failures = {}

    # Find failed member states
    for member, member_states in repl_member_states.items():
        failure_times = []
        labels = (b"member " + member + b" state",)
        compared_values = []

        for index in list(range(len(member_states["states"]))):
            time = member_states["state_times"][index]
            state = member_states["states"][index]
            if (
                state in FLAG_MEMBER_STATES
                and _allowed_state_transition(member_states["states"], index) is False
            ):
                failure_times.append(time)
                compared_values.append((FLAG_MEMBER_STATES[state],))

        failure = failure_collection(failure_times, compared_values, labels)
        if failure:
            failures[member] = failure

    if failures:
        return {"members": failures}
    return failures


def find_primary(chunk, repl_member_list):
    """Is there a member in state PRIMARY right now?

    :param collection.OrderedDict chunk: FTDC JSON chunk
    :param list[str] repl_member_list: list of replica set members in this variant
    :rtype: str|None
    """
    for member in repl_member_list:
        member_state_key = (b"replSetGetStatus", b"members", member, b"state")
        if member_state_key not in chunk:
            return None
        member_state = set(chunk[member_state_key])
        if len(member_state) != 1:
            # No formal error logging here right now.
            print(
                "State transition occurred mid-chunk. Member {0} states: {1}".format(
                    member, str(member_state)
                )
            )
            continue
        if member_state.pop() == 1:
            return member
    return None


def ftdc_replica_lag_check(path_to_ftdc_file, test_times=None):
    """Replica set lag computation requires some knowledge of the lag times over entire chunks,
    so the standard structure of our resource checks (in the rules module) will not apply.

    :param str path_to_file: path to a FTDC metrics file
    :param list[(datetime, datetime)] test_times: list of (start, end) test times.
        Use this to ignore problematic lag value if it doesn't occur during a test run.
    :rtype: list[dict] each dict corresponds to failure info for a different primary member.
            (accounts for possible election in the middle of a task)
    """
    repl_member_list = []
    collect_by_primary = []  # in case election occurs, lag info is specific to each primary

    lag_info_dict = {"times": []}
    current_primary = None

    for chunk in readers.read_ftdc(path_to_ftdc_file):
        if not repl_member_list:  # need a list of members in the replica set
            repl_member_list = get_repl_members(chunk)  # is there member info in this chunk?
            if not repl_member_list:
                continue
        primary = find_primary(chunk, repl_member_list)
        if not primary:  # skip if no primary
            continue
        # a primary member has been identified. check the newly fetched primary against our
        # currently declared primary
        if not current_primary:
            current_primary = primary
        elif primary is not current_primary:
            # an election has occurred. in this case, we store the information gathered thus far
            # using our currently declared primary and reset the necessary variables as we move
            # forward with the newly named primary
            collect_by_primary.append(lag_info_dict)
            lag_info_dict = {"times": []}
            current_primary = primary

        primary_optimedate_key = (b"replSetGetStatus", b"members", current_primary, b"optimeDate")
        if primary_optimedate_key not in chunk:  # skip if no optimeDate data for primary
            continue

        secondary_members = list(repl_member_list)
        secondary_members.remove(current_primary)
        # add the members as keys to the lag info dict if we are collecting lag info for the first
        # time with this primary.
        for member in secondary_members:
            if member not in lag_info_dict:
                lag_info_dict[member] = []

        test_run_indices = _get_whitelist_from_test_times(chunk, test_times)
        collect_lag = _chunk_member_lag(
            chunk, secondary_members, chunk[primary_optimedate_key], test_run_indices
        )

        # the two lengths may not be equivalent if, for whatever reason, optimeDate data for some
        # member is missing for this chunk. shouldn't happen, but if it does, we want to ignore
        # the data from this chunk.
        if len(list(collect_lag.keys())) == len(secondary_members):
            # `times` is an array of timestamps corresponding to when each sample was collected.
            # note that each chunk contains samples collected over some duration.
            lag_info_dict["primary"] = current_primary
            lag_info_dict["times"] += [chunk[FTDC_KEYS["time"]][i] for i in test_run_indices]
            for member, member_lag in six.iteritems(collect_lag):
                lag_info_dict[member] += member_lag

    # after processing the whole file, append the remaining lag info dictionary
    collect_by_primary.append(lag_info_dict)

    return _lag_failures_per_primary(collect_by_primary, repl_member_list)


def _chunk_member_lag(chunk, repl_member_list, primary_optimedates, test_run_indices):
    """Helper function to compute secondary lag from values in a chunk

    :param collection.OrderedDict chunk: FTDC JSON chunk
    :param list[str] repl_member_list: list of all members in the replSet
    :param str primary: which member is the primary?
    :param list[int] primary_optimedates: optimeDate values for the primary
    :rtype: dict (lag values for the secondaries)
    """
    collect_chunk_lag = {}
    for member in repl_member_list:
        member_optimedate_key = (b"replSetGetStatus", b"members", member, b"optimeDate")
        if member_optimedate_key not in chunk:
            break
        member_optimedate_values = chunk[member_optimedate_key]
        member_lag = []
        for index in test_run_indices:
            secondary_optimedate = member_optimedate_values[index]
            lag = primary_optimedates[index] - secondary_optimedate
            member_lag.append(lag)
        collect_chunk_lag[member] = member_lag
    return collect_chunk_lag


def _lag_failures_per_primary(lag_info_per_primary, repl_member_list):
    """Helper function to flag issues with repl secondary lag. Wrapper around the
    _flag_unacceptable_lag function call because lag information is collected `per primary`

    :param list[dict] lag_info_per_primary: list of lag information dicts specific to each newly
           elected primary
    :param list[str] repl_member_list: list of all members in the replSet
    :rtype: list[dict] each dict corresponds to failure info for a different primary member
    """
    failures = []
    for lag_info_dict in lag_info_per_primary:
        if lag_info_dict["times"]:  # check that lag information was indeed collected...
            flagged = _flag_unacceptable_lag(lag_info_dict, repl_member_list)
            if flagged:
                failures.append(flagged)
    return failures


def _flag_unacceptable_lag(lag_info_dict, repl_member_list):  # pylint: disable=too-many-locals
    """Helper function to analyze lag times and flag potential problems

       When there's a write after an idle period, we can observe lag that's equal to the duration
       to the idle period. Note that idle period can be as large as (now - unix_epoch) for the
       first write! We account for this error with the following simple formula:

            bounded_lag = min(current_lag, previous['lag'] + time_delta)
            # ...analyze lag...
            previous['lag'] = bounded_lag

       ...where time_delta is the time from previous lag to current lag. In practice always 1 sec.

       Initialization is: previous['lag'] = 0

       That means that we assume the data begins from a stable initial state where there is no
       lag - by definition. For an empty new cluster this is trivially the case. It is also
       possible that a cluster is started with an existing database snapshot on the primary, but
       empty secondaries. In this case the interpretation is that the initial state isn't
       considered lag, since it is "by design", but this algorithm will trigger an error, if
       secondaries wouldn't catch up within REPL_MEMBER_LAG_THRESHOLD_MS. (Which will be a hard
       requirement for larger database snapshots.)

    :param dict lag_info_dict: contains lag information for all members, the primary, and the
           timestamps for all the data collected.
    :param list[str] repl_member_list: list of all members in the replSet
    :rtype: dict (failure information)
    """
    failure_by_member = {}
    num_samples = len(lag_info_dict["times"])
    if num_samples <= 1:  # if lag is too large at beginning, it could just be a false positive.
        return {}
    for member in repl_member_list:
        if lag_info_dict["primary"] is member:
            continue

        failure_times = []
        compared_values = []
        member_lag = lag_info_dict[member]

        previous = {"lag": 0, "time": member_lag[0]}
        is_lagging = False
        failure_dict = {}

        for index in range(1, num_samples):
            current_time = lag_info_dict["times"][index]
            current_lag = member_lag[index]
            time_delta = current_time - previous["time"]
            bounded_lag = min(current_lag, previous["lag"] + time_delta)

            if not is_lagging:
                if bounded_lag > REPL_MEMBER_LAG_THRESHOLD_MS:
                    # Following if statement shouldn't be needed. It is used to filter out the fact
                    # that index_build will always have secondary lag and we don't have an override
                    # mechanism to turn this off test-by-test, so this would always fail for
                    # index_build. Characteristic for index_build is that the lag grows exactly
                    # 1 sec / sec, because the secondary is completely blocked.
                    # FIXME: if can be removed when PERF-1031 is implemented.
                    if bounded_lag - previous["lag"] < time_delta:
                        LOGGER.debug("lag start")
                        LOGGER.debug(
                            "bounded_lag > threshold %s %s %s",
                            current_lag,
                            previous["lag"],
                            current_time,
                        )
                        is_lagging = True
                        failure_dict = {
                            "start_time": current_time,
                            "start_value": current_lag,
                            "max_value": current_lag,
                            "max_time": current_time,
                        }
            else:
                # We want to capture consecutive ranges of lag happening. Therefore the thershold
                # to determine lag has ended is lower than the treshold that triggers the start.
                if current_lag < REPL_MEMBER_LAG_RESET_MS:
                    LOGGER.debug("lag end")
                    is_lagging = False
                    failure_dict["end_value"] = previous["lag"]
                    failure_dict["end_time"] = previous["time"]

                    failure_times.append(failure_dict["start_time"])
                    compared_values.append(
                        (
                            failure_dict["start_value"] / MS,
                            ftdc_date_parse(failure_dict["max_time"] / MS),
                            failure_dict["max_value"] / MS,
                            ftdc_date_parse(failure_dict["end_time"] / MS),
                            failure_dict["end_value"] / MS,
                        )
                    )
                else:
                    # lag continues
                    if current_lag > failure_dict["max_value"]:
                        failure_dict["max_value"] = current_lag
                        failure_dict["max_time"] = current_time

            previous["lag"] = bounded_lag
            previous["time"] = current_time

        labels = ("start value (s)", "max time", "max value (s)", "end time", "end value (s)")
        failure = failure_collection(failure_times, compared_values, labels, None, True)
        if failure:
            failure_by_member[member] = failure
    if failure_by_member:
        return {
            "members": failure_by_member,
            "additional": {
                "lag start threshold (s)": REPL_MEMBER_LAG_THRESHOLD_S,
                "lag end threshold (s)": REPL_MEMBER_LAG_RESET_S,
                "primary member": lag_info_dict["primary"],
            },
        }
    return {}


def _get_whitelist_from_test_times(chunk, test_times=None):
    """FTDC data is stored in chunks. Each chunk is a key-value mapping from some FTDC_KEY
    to a list of values collected over a period of time. This is a quick way to whitelist
    the list indices during which a test is being executed.
    If test_times is not specified (i.e. no perf.json parameter passed in),
    we just return the full range across the chunk time metric.

    :param collection.OrderedDict chunk: FTDC JSON chunk
    :param list[(datetime, datetime)] test_times: list of (start, end) test times.
        Use this to ignore problematic lag value if it doesn't occur during a test run.
    :rtype: list[int]
    """
    test_run_indices = []
    times = chunk[FTDC_KEYS["time"]]
    if not test_times:
        test_run_indices = list(range(len(times)))
    else:
        chunk_times_in_s = [time_in_ms / MS for time_in_ms in times]
        for index, time_in_s in enumerate(chunk_times_in_s):
            if any(start <= util.num_or_str_to_date(time_in_s) <= end for start, end in test_times):
                test_run_indices.append(index)
    return test_run_indices


# DB correctness jstest rules


def db_correctness_analysis(dir_path):
    """Recursively search `dir_path` for db-correctness directory. test_control.py is responsible
    for running these JS tests if the relevant scripts are present. As a result of the JS tests
    being run, test_control.py will create the db-correctness directory in addition to the
    db-hash-check & validate-indexes-and-collections sub-directories to hold the resulting log
    files.  If such log files exist, this function finds and parses them.

    :type dir_path: str
    :rtype: list[dict], a list of result dictionaries to be written to report.json

    """
    find_directory = "db-correctness"
    # The directories in db-correctness. Same as the name of the test on Evergreen.
    db_correctness_log_directories = ["db-hash-check", "validate-indexes-and-collections"]
    report_results = []
    for root_directory, sub_directory, _ in os.walk(dir_path):
        if find_directory in sub_directory:
            path_to_target = os.path.join(root_directory, find_directory)
            for log_directory in db_correctness_log_directories:
                path_to_directory = os.path.join(path_to_target, log_directory)
                log_name = log_directory + "." + os.path.basename(root_directory)
                if os.path.exists(path_to_directory):
                    log_files = os.listdir(path_to_directory)
                    if log_files:
                        log_results = _report_js_test_result(log_name, path_to_directory, log_files)
                        report_results.append(log_results)
    return report_results


def _report_js_test_result(test_name, path_to_file, filename_list):
    """Helper function to parse the JS test log file. Last line should be an exit code, 0 or 1,
    denoting whether or not the checks passed.

    :type test_name: str
    :type path_to_file: str
    :type filename_list: list[str]
    :rtype: dict
    """
    js_test_failure_output = ""
    for filename in filename_list:
        path_to_logfile = os.path.join(path_to_file, filename)
        log_output = ""
        last_line = None
        with open(path_to_logfile) as file_handle:
            for line in file_handle:
                log_output += line
                last_line = line.strip()
        try:
            exit_status = int(last_line)
            if exit_status:
                js_test_failure_output += "\nFAILURE: (logfile `{0}`)\n".format(filename)
                js_test_failure_output += log_output
        except ValueError:
            js_test_failure_output = (
                "\nFAILURE: logfile `{0}` did not record a valid exit " "code. Output:\n {1}"
            ).format(filename, log_output)
    result = {"test_file": test_name, "start": 0}
    if js_test_failure_output:
        result["status"] = "fail"
        result["log_raw"] = js_test_failure_output
        result["exit_code"] = 1
    else:
        result["status"] = "pass"
        result["log_raw"] = "\nPassed {0} JS test.".format(test_name)
        result["exit_code"] = 0
    return result
