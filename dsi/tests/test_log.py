"""Tests for dsi/common/host.py"""

import unittest
from io import StringIO

from mock import MagicMock

from dsi.common.log import TeeStream


class LogTestCase(unittest.TestCase):
    """ Unit Test for Host library """

    def test_tee_write(self):
        """ Test TeeStream write """

        first = StringIO()
        second = StringIO()
        subject = TeeStream(first, second)
        expected = "this is a test"
        subject.write(expected)

        self.assertEqual(first.getvalue(), expected)
        self.assertEqual(second.getvalue(), expected)

    def test_tee_writelines(self):
        """ Test TeeStream writelines """

        first = StringIO()
        second = StringIO()
        subject = TeeStream(first, second)
        expected = "this is a test"
        subject.writelines([expected, expected])

        self.assertEqual(first.getvalue(), expected * 2)
        self.assertEqual(second.getvalue(), expected * 2)

        first = StringIO()
        second = StringIO()
        subject = TeeStream(first, second)
        expected = "this is a test"
        subject.writelines([expected + "\n", expected])

        self.assertEqual(first.getvalue(), expected + "\n" + expected)
        self.assertEqual(second.getvalue(), expected + "\n" + expected)

    def test_tee_flush(self):
        """ Test TeeStream flush """

        first = MagicMock()
        second = MagicMock()
        subject = TeeStream(first, second)
        subject.flush()

        first.flush.assert_called_once()
        second.flush.assert_called_once()

    def test_tee_close(self):
        """ Test TeeStream flush """

        first = MagicMock()
        second = MagicMock()
        subject = TeeStream(first, second)
        subject.close()

        first.close.assert_called_once()
        second.close.assert_called_once()

    def test_tee_closed(self):
        """ Test TeeStream closed """

        first = MagicMock()
        second = MagicMock()
        subject = TeeStream(first, second)
        self.assertFalse(subject.closed)
        subject.close()
        self.assertTrue(subject.closed)


if __name__ == "__main__":
    unittest.main()
