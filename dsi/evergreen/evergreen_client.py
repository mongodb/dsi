"""Module for interacting with Evergreen."""


import logging
from copy import deepcopy

from dsi.evergreen import helpers

DEFAULT_EVERGREEN_URL = "https://evergreen.mongodb.com"
"""The default Evergreen URL."""


class EvergreenError(Exception):
    """Generic class for Evergreen errors."""


class Empty(EvergreenError):
    """Indicates that an empty response from Evergreen was not expected."""


class Client:
    """Allows for interaction with an Evergreen server.

    2020-01-10 Henrik Ingo: I deleted all methods that weren't used. See git history if you need
    something. The idea is to get rid of all this and migrate to
    https://pypi.org/project/evergreen.py/
    """

    def __init__(self, configuration=None, verbose=True):
        """Create a new handle to an Evergreen server.

        :param dict configuration: (optional) contents of personal Evergreen YAML config file
        :param bool verbose: (optional) Control the verbosity of logging statements
        """
        self.__setstate__({"configuration": configuration, "verbose": verbose})

    def __getstate__(self):
        """
        Get state for pickle support.

        Multiprocessor uses pickle to serialize and deserialize data to sub processes. However,
        complex types cannot be pickled. They can be recreated with the core state (and
        this is what this calls does).

        :return: The pickled state.
        """
        return {"configuration": self.configuration, "verbose": self.verbose}

    def __setstate__(self, state):
        """
        Set state for pickle support.

        Clear the lazy params so that the are recreated on demand.

        :param dict state: The pickled state.
        """
        self.configuration = state["configuration"]
        self.verbose = state["verbose"]

        self.logger = logging.getLogger("evergreen")
        self.logger.level = logging.INFO if self.verbose else logging.WARNING
        # Parse the config file
        try:
            self.headers = {
                "api-user": self.configuration["user"],
                "api-key": self.configuration["api_key"],
            }
            self.base_url = self.configuration["ui_server_host"]
        except (TypeError, KeyError):
            self.logger.warning("Using default evergreen credentials.")
            self.base_url = DEFAULT_EVERGREEN_URL
            self.headers = {}

    def _redact_copy(self):
        """
        Get a copy of the state and redact any sensitive info.

        :returns: A redacted copy of the state.
        """
        copy = deepcopy(self.__getstate__())
        if "configuration" in copy:
            configuration = copy["configuration"]
            if "api_key" in configuration:
                configuration["api_key"] = "XXXXXXXXX"
            if "evergreen" in configuration and "api_key" in configuration["evergreen"]:
                configuration["evergreen"]["api_key"] = "XXXXXXXXX"
            if "github" in configuration and "token" in configuration["github"]:
                configuration["github"]["token"] = "XXXXXXXXX"

        return copy

    def __str__(self):
        """
        Get a readable string for this job.

        :returns: A readable string.
        """
        copy = self._redact_copy()
        return str(copy)

    def __repr__(self):
        """
        Get an unambiguous string for this job.

        :returns: An unambiguous string.
        """
        copy = self._redact_copy()
        return "<{}{}({!r})>".format(self.__module__, self.__class__.__name__, copy)

    def query_project_history(self, project):
        """Gets all the information on the most recent revisions.

        Evergreen endpoint: /rest/v1/projects/{project_name}/versions

        :param str project: The name of the Evergreen project (e.g. 'performance', 'sys-perf')
        :rtype: dict
        """
        return helpers.get_as_json(
            "{}/rest/v1/projects/{}/versions".format(self.base_url, project), headers=self.headers
        )

    def query_revision(self, revision_id):
        """Get information on a given revision.

        Evergreen endpoint: /rest/v1/versions/{revision_id}

        :param str revision_id: The Evergreen ID of a particular revision or version
        :rtype: dict
        """
        return helpers.get_as_json(
            "{}/rest/v1/versions/{}".format(self.base_url, revision_id), headers=self.headers
        )

    def query_build_variant(self, build_variant_id):
        """Get information on a particular build variant.

        Evergreen endpoint: /rest/v1/builds/{build_id}

        :param str build_variant_id: The Evergreen ID of a particular build variant
        :rtype: dict
        """
        return helpers.get_as_json(
            "{url}/rest/v1/builds/{build_id}".format(url=self.base_url, build_id=build_variant_id),
            headers=self.headers,
        )

    def query_perf_results(self, task_id):
        """Get the 'perf.json' performance results for given task_id

        Evergreen endpoint: /plugin/json/task/{task_id}/perf/

        (Tested on sys-perf, but mongo-perf should be the same.)

        :param str project: task_id of a specific build+variant
        :rtype: dict
        """
        return helpers.get_as_json(
            "{}/plugin/json/task/{}/perf/".format(self.base_url, task_id), headers=self.headers
        )
