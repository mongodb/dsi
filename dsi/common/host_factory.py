"""
Generate the right type of host object and return it or run commands against it
"""

import logging

from dsi.common.local_host import LocalHost
from dsi.common.log import IOLogAdapter
from dsi.common.remote_ssh_host import RemoteSSHHost

LOG = logging.getLogger(__name__)
# This stream only log error or above messages
ERROR_ONLY = logging.getLogger("error_only")

INFO_ADAPTER = IOLogAdapter(LOG, logging.INFO)
WARN_ADAPTER = IOLogAdapter(LOG, logging.WARN)


def make_host(host_info, mongodb_auth_settings=None, use_tls=False):
    """
    Create a host object based off of host_ip_or_name. The code that receives the host is
    responsible for calling close on the host instance. Each RemoteHost instance can have 2*n+1 open
    sockets (where n is the number of exec_command calls with Pty=True) otherwise n is 1 so there is
    a max of 3 open sockets.

    :param mongodb_auth_settings: MongoDB auth settings dictionary
    :param namedtuple host_info: Public IP address or the string localhost, category and offset
    :rtype: Host
    """

    host = None

    if host_info.public_ip in ["localhost", "127.0.0.1", "0.0.0.0"]:
        LOG.debug("Making localhost for %s", host_info.public_ip)
        host = LocalHost(mongodb_auth_settings, use_tls)
    else:
        LOG.debug("Making remote host for %s using ssh", host_info.public_ip)
        host = RemoteSSHHost(
            host_info.public_ip,
            host_info.ssh_user,
            host_info.ssh_key_file,
            mongodb_auth_settings,
            use_tls,
        )

    host.alias = "{category}.{offset}".format(category=host_info.category, offset=host_info.offset)
    return host
