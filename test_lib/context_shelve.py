"""
Implementation of ContextShelve class.
"""

import shelve

import requests


class ContextShelve:
    """
    ContextShelve is essentially a wrapper around shelve. This is necessary because shelve does not
    have a context manager in Python 2.7 and because get() needed to take in dumby **kwargs for
    mocking on get_as_json.
    """

    def __init__(self, filename, flag="c", protocol=None, writeback=False):
        """
        Create a new ContextShelve.
        Essentially a copy of shelve.open except it args are saved during construction.
        See https://docs.python.org/2/library/shelve.html#shelve.open.

        :param str filename: The name of the file.
        :param str flag: The name of the flag which has the same interpretation as the `flag`
        parameter of dbm.open(). Defaults to 'c'. See
        https://docs.python.org/3/library/dbm.html#dbm.open.
        :param protocol: The version of the pickle protocol. Shelve defaults this to version 3.
        :type protocol: int, None.
        :param bool writeback: When set to `True`, all entries accessed are cached in memory, and
        written back on sync() and close(). Otherwise, only objects assigned to the shelf are
        written. Defaults to `False`.
        """
        self.filename = filename
        self.flag = flag
        self.protocol = protocol
        self.writeback = writeback
        self.dictionary = None

    def __enter__(self):
        """
        Enters the context. Opens the persistent dictionary using shelve.

        :rtype: ContextShelve.
        """
        self.open()
        return self

    def open(self):
        """
        Opens the persistent dictionary using shelve.
        """
        self.dictionary = shelve.open(self.filename, self.flag, self.protocol, self.writeback)

    def get(self, url, **kwargs):
        """
        A wrapper around shelve.get(). If the key is not in the dictionary, does a get request to
        get the data and update the dictionary.

        :param str url: The key used to access value in `self.dictionary`.
        :param **kwargs: Dummy arguments necessary for mocking get_as_json.
        """
        if url not in self.dictionary.keys():
            response = requests.get(url, **kwargs)
            self.dictionary[url] = response.json()
        return self.dictionary.get(url)

    def close(self):
        """
        A wrapper around shelve.close().
        Closes self.dictionary and sets it to None.
        """
        self.dictionary.close()
        self.dictionary = None

    def __exit__(self, *args):
        self.close()
