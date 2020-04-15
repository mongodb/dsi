"""
IO utils for testing.
"""

import contextlib
import os
import sys


@contextlib.contextmanager
def redirect_stdout(file_handle):
    """
    A context manager for temporarily redirecting the program's `stdout` output to `file_handle`.

    :param file file_handle: The file to which `stdout` will be redirected.
    """
    normal_stdout = sys.stdout
    sys.stdout = file_handle
    exception = None
    try:
        yield
    except Exception as exception:  # pylint: disable=broad-except
        pass
    sys.stdout = normal_stdout
    if exception is not None:
        raise exception  # pylint: disable=raising-bad-type


@contextlib.contextmanager
def in_dir(into):
    """perform some operation in context of another dir"""
    old_dir = os.getcwd()
    try:
        os.chdir(into)
        yield
    finally:
        os.chdir(old_dir)
