"""Tests for dsi/alias.py"""


import unittest

from dsi.alias import unalias, expand, ALIASES


class AliasTestCase(unittest.TestCase):
    """Unit tests for Alias utility functions."""

    def test_unalias(self):
        """check that the alias work as expected."""

        self.assertEqual(unalias("md"), "mongod")
        self.assertEqual(unalias("ms"), "mongos")
        self.assertEqual(unalias("cs"), "configsvr")
        self.assertEqual(unalias("configsrv"), "configsvr")
        self.assertEqual(unalias("wc"), "workload_client")

        self.assertEqual(unalias("MD"), "MD")

        aliases = {"MD": "MONGOD", "md": "mongod"}
        self.assertEqual(unalias("MD", aliases), "MONGOD")
        self.assertEqual(unalias("md", aliases), "mongod")

        # do not do something like the following, as it will permanently add to
        # ALIASES, either copy before the update or use a dict constructor as shown
        # in the test
        #
        # aliases = ALIASES.update({'m': 'mongod'})
        aliases = dict(ALIASES, **{"m": "mongod"})
        self.assertEqual(unalias("m", aliases), "mongod")
        self.assertEqual(unalias("md", aliases), "mongod")

        overrides = dict(ALIASES, **{"m": "mongod", "md": "MONGOD"})
        self.assertEqual(unalias("m", overrides), "mongod")
        self.assertEqual(unalias("md", overrides), "MONGOD")

    def test_expand(self):
        """check that the expand works as expected."""
        self.assertEqual(expand("md"), "md.0.public_ip")
        self.assertEqual(expand("mongod"), "mongod.0.public_ip")
        self.assertEqual(expand("mongod.0"), "mongod.0.public_ip")

    def test_expand_ex(self):
        """check that the expand throws exceptions as expected."""
        self.assertRaisesRegex(
            ValueError, "The max level of nesting is 3:", expand, "md.0.public_ip.extra"
        )

    def test_expand_and_unalias(self):
        """check that the order of alias and expand is not important."""
        # runtime = self.config['runtime']
        self.assertEqual(expand(unalias("md")), "mongod.0.public_ip")
        self.assertEqual(unalias(expand("md")), expand(unalias("md")))


if __name__ == "__main__":
    unittest.main()
