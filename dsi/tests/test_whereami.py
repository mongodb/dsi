"""
Unit tests for `whereami.py`
"""
from __future__ import absolute_import

import os
import unittest
from os.path import dirname as dn

from dsi.common import whereami

#
# This should be the only place in the repo that relies on __file__
# NB: in this test we rely on knowing our directory hierarchy (knowing that
#     this file is located in /dsi/tests, but the actual implementation of
#     whereami relies on the special .dsi-root file.
#
ACTUAL_ROOT = dn(dn(dn(__file__)))


class TestRequestsParent(unittest.TestCase):
    def test_repo_root(self):
        self.assertEqual(whereami.dsi_repo_path(), ACTUAL_ROOT)

    def test_repo_root_different_cwd(self):
        existing = os.getcwd()
        try:
            os.chdir(os.path.dirname(ACTUAL_ROOT))
            self.assertEqual(whereami.dsi_repo_path(), ACTUAL_ROOT)
        finally:
            os.chdir(existing)

    def test_repo_root_file_exists(self):
        self.assertEqual(whereami.dsi_repo_path("docs"), os.path.join(ACTUAL_ROOT, "docs"))

    def test_repo_root_file_exists_subdir(self):
        self.assertEqual(
            whereami.dsi_repo_path("docs", "config-specs"),
            os.path.join(ACTUAL_ROOT, "docs", "config-specs"),
        )

    def test_repo_root_file_not_exists(self):
        with self.assertRaises(IOError):
            whereami.dsi_repo_path("W5GY17UME80A6A653JYA_does_not_exist_4N044G86N9QRFC3PJ1UC")
