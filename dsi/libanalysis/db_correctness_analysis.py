"""
analysis.py plugin: Check the output of the db-correctness validation.
"""


import structlog

from dsi.libanalysis import rules

LOG = structlog.get_logger(__name__)


def db_correctness(config, results):
    """
    analysis.py plugin: Check the output of the db-correctness validation.

    :param ConfigDict config: The global config.
    :param ResultsFile results: Object to add results to.
    """
    LOG.info("Checking results from db-correctness validation.")
    path = config["test_control"]["reports_dir_basename"]
    results.extend(rules.db_correctness_analysis(path))
