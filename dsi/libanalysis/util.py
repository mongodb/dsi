"""Module of utility functions for analysis"""


import datetime
import doctest
import json
import os

import six
from dateutil import tz, parser as date_parser


def get_project_variant_rules(config, variant, rule):
    """The rules we want to check are specified in nested dictionaries. They all follow the same
       structure, so this is a short helper to fetch a list of functions, corresponding to the
       rules evaluated for a given project and variant.

    :type project: ConfigDict
    :type variant: str
    :type rule: str
    :rtype: list(str)
    """
    value = config["analysis"]["rules"][rule]["default"]
    if variant in config["analysis"]["rules"][rule]:
        value = config["analysis"]["rules"][rule][variant]
    return value


def get_test_times(perf_json_or_path):
    """
    Read the performance report file at `perf_file_path` (usually called "perf.json") and return a
    `(start, end)` tuple of its "start" and "end" timestamps, represented as UTC `datetime`s.
    """

    if isinstance(perf_json_or_path, dict):
        perf_json = perf_json_or_path

    else:
        perf_file_path = perf_json_or_path
        try:
            perf_json = get_json(perf_file_path)

        except IOError:
            return None

    try:
        return [(num_or_str_to_date(perf_json["start"]), num_or_str_to_date(perf_json["end"]))]

    except KeyError:
        return [
            (num_or_str_to_date(test["start"]), num_or_str_to_date(test["end"]))
            for test in perf_json["results"]
            if "start" in test and "end" in test
        ]


def num_or_str_to_date(ts_or_date_str):
    """
    Convert `ts_or_date_str`, which is either a seconds-since-epoch `float` or a formatted date
    string, to a `datetime` object.
    """

    conv_func = (
        date_parser.parse
        if isinstance(ts_or_date_str, six.string_types)
        else _unix_ts_to_utc_datetime
    )
    return conv_func(ts_or_date_str)


def _unix_ts_to_utc_datetime(unix_ts):
    """
    Convert `unix_ts` (a seconds-since-epoch `float`) to a UTC `datetime` object with
    `tzinfo=tzutc()`.
    """

    datetime_ts = datetime.datetime.utcfromtimestamp(unix_ts)
    return datetime_ts.replace(tzinfo=tz.tzutc())


def get_json(filename):
    """ Load a file and parse it as json """
    with open(filename) as json_file:
        return json.load(json_file)


def get_thread_sum(perf_json="perf.json"):
    """
    Returns the sum of max thread count for each test in the task.

    TODO: Yes, this is way too high, but keeping it consistent with historical implementation for
    now.
    :return: Sum of all client threads in a task.
    """
    threads = 0
    if os.path.isfile(perf_json):
        task_results = get_json(perf_json)
        for test_obj in task_results.get("results", []):
            threads += max(int(x) for x in test_obj["results"].keys())
        return threads
    return 999999999999


if __name__ == "__main__":
    doctest.testmod()
