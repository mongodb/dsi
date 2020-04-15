"""
This class provides a base test class for other tests which use
evergreen.helpers.get_full_git_commit_hash and evergreen.helpers.get_as_json.
It mocks the two functions in every test.

For reference on mocking functions in all tests:
http://www.voidspace.org.uk/python/mock/examples.html#applying-the-same-patch-to-every-test-method
"""

import os
import unittest

from mock import patch

from test_lib.context_shelve import ContextShelve
from test_lib.fixture_files import FixtureFiles

FIXTURE = FixtureFiles()


class TestRequestsParent(unittest.TestCase):
    """
    Parent Class for tests which do requests. Mocks out requests and uses ContextShelve.
    """

    def setUp(self):
        """
        Mocks the connection functions and also opens up the ContextShelve object.
        """
        # pylint: disable=invalid-name
        persistent_dict_path = os.path.join(FIXTURE.fixture_file_path(), "override_responses")
        self.override_responses = ContextShelve(persistent_dict_path)
        self.override_responses.open()
        # Instead of using patch in decorators or as a context manager, the start() and stop()
        # methods are used for better control over mock.
        # patch() simply creates the mock object on the specific function
        # start() begins the actual mock on the function/object; this is when the function or object
        # will now be seen as a mock object by Python
        # end() gives the mocked function/object back its original functionality
        self.get_full_git_commit_hash_patcher = patch(
            "dsi.evergreen.helpers.get_full_git_commit_hash"
        )
        self.get_as_json_patcher = patch("dsi.evergreen.helpers.get_as_json")
        self.mock_get_full_git_commit_hash = self.get_full_git_commit_hash_patcher.start()
        self.mock_get_as_json = self.get_as_json_patcher.start()
        self.mock_get_full_git_commit_hash.return_value = "c2af7abae8d09d290d7457ab77f5a7529806b75a"
        self.mock_get_as_json.side_effect = self.override_responses.get
        # pylint: enable=invalid-name

    def tearDown(self):
        """
        Unpatches the connection functions and closes the ContextShelve.
        """
        self.get_full_git_commit_hash_patcher.stop()
        self.get_as_json_patcher.stop()
        self.override_responses.close()
