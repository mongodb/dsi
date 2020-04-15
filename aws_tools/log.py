"""
Set up logging for DSI scripts.

Note: Copy/subset of dsi/common/log.py. Hopefully these can be reunited in the future when
everything installs the same way. For now, we can't import from outside aws_tools.
"""
import logging


def setup_logging(verbose=False, filename=None, explicit_log_level=None):
    """Configure logging verbosity and destination."""
    if explicit_log_level:
        loglevel = explicit_log_level
    else:
        loglevel = logging.DEBUG if verbose else logging.INFO
    handler = logging.FileHandler(filename) if filename else logging.StreamHandler()
    handler.setLevel(loglevel)
    root_logger = logging.getLogger()
    root_logger.setLevel(loglevel)
    root_logger.addHandler(handler)

    # The following sets the minimum level that we will see for the given component. So we will
    # only see warnings and higher for paramiko, boto3 and botocore. We will only see errors / fatal
    # / critical log messages for /dev/null
    logging.getLogger("boto3").setLevel(logging.WARNING)
    logging.getLogger("botocore").setLevel(logging.WARNING)
