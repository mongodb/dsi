"""Module of utility functions for analysis"""


import os
from collections import namedtuple

EXIT_STATUS_OK = 0
""" This code indicates that the command did not return an error """

EXIT_STATUS_ERR = 1
""" This code indicates that the command returned an error, although it is not specific """

EXIT_STATUS_LINE_PREFIX = "exit_status:"
""" A test output file name status must start with this prefix """


class StatusWithMessage(namedtuple("StatusWithMessage", ["status", "message"])):
    """ Class to hold exit status and message """

    __slots__ = ()
    """ https://docs.python.org/2/library/collections.html The subclass shown above sets __slots__
        to an empty tuple. This helps keep memory requirements low by preventing the creation of
        instance dictionaries.
    """

    def __str__(self):
        """ generate a human readable exit status. """
        if self.status == 0:
            result = "Succeeded"
        else:
            result = "Failed"

        if self.message:
            human = "Command {}: status={} message={}".format(result, self.status, self.message)
        else:
            human = "Command {}: status={}".format(result, self.status)
        return human


def read_exit_status(filename):
    """
    read the exit status from the last line of filename.

    :param str filename: the test output filename.
    """

    stat = os.stat(filename)
    if stat.st_size:
        with open(filename, "r") as file_handle:
            last_line = file_handle.readlines()[-1]
        if last_line.startswith(EXIT_STATUS_LINE_PREFIX):
            parts = last_line.split(" ", 2)
            if len(parts) == 1:
                status, message = (EXIT_STATUS_ERR, None)
            elif len(parts) == 2:
                status, message = (parts[1], None)
            else:
                status, message = parts[1:]
            status = int(status)
            if message:
                message = message.decode("string_escape")
        else:
            status = EXIT_STATUS_ERR
            message = "Unknown Error: expected status line was missing from '{}'".format(filename)
    else:
        status = EXIT_STATUS_ERR
        message = "Unknown Error: empty file '{}'".format(filename)

    return StatusWithMessage(status, message)
