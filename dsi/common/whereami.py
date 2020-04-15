"""
Knows about how to locate files DSI needs to do its job.
Always use whereami instead of hard-coding knowledge about DSI's repo layout.
I.e., use this file instead of __file__ or relative paths based on cwd in code or tests.
"""
import os


def _findup(fpath, cwd):
    """
    Look "up" the directory tree for fpath starting at cwd. Raises if not found.
    :param fpath:
    :param cwd:
    :return:
    """
    curr = cwd
    while os.path.exists(curr):
        if os.path.exists(os.path.join(curr, fpath)):
            return os.path.normpath(curr)
        curr = os.path.join(curr, "..")
    raise BaseException("Cannot find {} in {} or any parent dirs.".format(fpath, cwd))


def dsi_repo_path(*args):
    """
    :param args: string path elements for a file in the dsi repo
                 e.g. ("dsi", "common", "whereami.py") for this file
    :return: the full path to the file or IOError if it doesn't exist.
    """
    root = _findup(".repo-root", os.path.dirname(__file__))
    result = os.path.join(root, *args)
    if not os.path.exists(result):
        raise IOError("DSI file {} doesn't exist".format(args))
    return result
