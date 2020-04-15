"""
analysis.py plugin: Check core files.

Copied from analysis/post_run_check.py
"""


import fnmatch
import os

import six
import structlog

LOG = structlog.get_logger(__name__)


def core(config, results):
    """
    analysis.py plugin: Check core files

    :param ConfigDict config: The global config.
    :param ResultsFile results: Object to add results to.
    """
    LOG.info("Checking core files.")
    path = config["test_control"]["reports_dir_basename"]
    results.extend(check_core_file_exists(path))


def check_core_file_exists(reports_dir_path, pattern="core.*"):
    """Analyze all the file in the directory tree rooted at `reports_dir_path`,
    and return a list of test-result dictionaries ready to be placed in the report JSON generated
    by `post_run_check`/`perf_regression_check`.

    The check first looks for directories matching the following patterns  'mongo?.[0-9]' or '
    configsvr.[0-9]'

    If no directories match then an empty array is returned (this case covers a system failure or
    the case where nothing is captured for some other reason).

    For each matching directory, it will return a result with the 'test_name' field set to
    'core.<directory>'.

    *Note*: 'test_name' is the name of the check, not the name of an actual file. Unlike the other
    sanity checks, in the majority of cases there won't a file.
    *Note*: directory will be something like mongod.0, mongod.1, mongos.2, configsvr.3.

    In each matching directories, files matching the pattern parameter are checked (default to
    'core.*').

    If one or more core file is found per directory then a record is created with:
      * 'test_file' set to 'core.<directory>'. As described above, this is the name of the sanity
         check.
      * 'status' set to 'fail'.
      * 'exit_code' set to 1.
      * 'log_raw'  set to 'No core files found' or a comma separated list of the base filenames
         (i.e. excluding the parent directory). These are the messages displayed within
         the test results widget in the dashboard.

    A Failing check result looks like:
    {
                "status": "fail",
                "test_file": 'core.<directory>',
                "log_raw": '<comma separated core files>',
                "start": 0,
                "exit_code": 1
    }

    If no core is found then each directory generates a result like the following:
    {
                "status": "pass",
                "test_file": 'core.<directory>',
                "log_raw": 'No core files found',
                "start": 0,
                "exit_code": 0
    }
    """
    # List of directories that could contain a core file
    mongo_dir_paths = []

    # Core files, if they happen, are downloaded into reports/test_id/mongod.0/core.*
    for test_name in os.listdir(reports_dir_path):
        test_dir_path = os.path.join(reports_dir_path, test_name)
        if os.path.isdir(test_dir_path):
            for mongo_name in os.listdir(test_dir_path):
                mongo_dir_path = os.path.join(test_dir_path, mongo_name)
                if (
                    os.path.isdir(mongo_dir_path)
                    and fnmatch.fnmatch(mongo_name, "mongo?.[0-9]")
                    or fnmatch.fnmatch(mongo_name, "configsvr.[0-9]")
                ):
                    mongo_dir_paths.append(mongo_dir_path)

    def _format_msg_body(basenames=None):
        msg_body = (
            "\nNo core files found"
            if not basenames
            else "\ncore files found: {}\nNames: \n{}".format(len(basenames), ", ".join(basenames))
        )
        return msg_body

    results = []
    if mongo_dir_paths:
        cores_lookup = {}
        for mongo_dir_path in mongo_dir_paths:
            cores_lookup[mongo_dir_path] = []

            for potential_corefile in os.listdir(mongo_dir_path):
                if fnmatch.fnmatch(potential_corefile, pattern):
                    cores_lookup[mongo_dir_path].append(potential_corefile)

        for mongo_dir_path in sorted(six.iterkeys(cores_lookup)):
            cores = cores_lookup[mongo_dir_path]
            mongo_host = os.path.basename(mongo_dir_path)
            test_id = os.path.basename(os.path.dirname(mongo_dir_path))
            message = _format_msg_body(cores)
            results.append(
                {
                    "status": "fail" if cores else "pass",
                    "test_file": "core.{}.{}".format(test_id, mongo_host),
                    "log_raw": message,
                    "start": 0,
                    "exit_code": 1 if cores else 0,
                }
            )
            LOG.debug(message, cores=cores, test_id=test_id, mongo_host=mongo_host)
    return results
