"""
analysis.py plugin: Dummy plugin.

Dummy plugin that does nothing. Used for unit testing.
"""


import structlog

from six.moves import range

LOGGER = structlog.get_logger(__name__)


def dummy(config, results):
    """
    Dummy plugin for testing.
    """
    results.add("dummy", "pass", 1, 2, "Arbitrary text string", 0)
    for i in range(1, config.get("_test_failures", 0) + 1):
        results.add("dummy_fail." + str(i), "fail", 3, 4, "This test failed", i)
