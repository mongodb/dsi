"""
Given a list of commands, run threads and return the results as a list. If you want to give
argument to a command, wrap it in a partial using functools.
example:
   1. work(arg1, arg2) becomes
   2. partial(work, arg1, arg2)
"""


import logging
import sys
import threading
import time

import six.moves.queue

# logging must have been setup else where
LOG = logging.getLogger(__name__)


def run_threads(commands, daemon=False):
    """
    Given a list of commands, run threads and return the results as a list.
    """
    if not commands:
        return []
    threads = []
    thread_results = six.moves.queue.Queue(maxsize=len(commands))
    thread_exceptions_bucket = six.moves.queue.Queue()
    stop_thread_execution = threading.Event()
    try:
        for command in commands:
            thread = threading.Thread(
                target=wrap,
                args=(command, thread_results, thread_exceptions_bucket, stop_thread_execution),
            )
            thread.daemon = daemon
            threads.append(thread)
            thread.start()
        # Exit from the loop on one of these two conditions:
        #    1. An exception has been created in a worker thread and said exception information
        #       has been placed in the 'thread_exceptions_bucket', OR
        #    2. 'threading.activeCount()' is zero, meaning that all worker threads have
        #       returned (or raised exceptions).
        while thread_exceptions_bucket.empty() and not thread_results.full():
            time.sleep(0.1)

        stop_thread_execution.set()
        if not thread_exceptions_bucket.empty():
            exception_info = thread_exceptions_bucket.get()
            raise exception_info[0]
        return list(thread_results.queue)
    except Exception as exc:
        stop_thread_execution.set()
        raise exc


def wrap(command, thread_results, thread_exceptions_bucket, stop_thread_execution):
    """
    Takes the command, runs it, and tracks the result in a queue.
    """
    if stop_thread_execution.is_set():
        return
    try:
        thread_results.put(command())
    except Exception:  # pylint: disable=broad-except
        LOG.warning("Unexpected exception in thread", exc_info=1)
        thread_exceptions_bucket.put(sys.exc_info())
