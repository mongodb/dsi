#!/usr/bin/env python3.7

"""
Utility to expand aliases to ip addresses, either as full dotted names or shorter aliases.

Ultimately, the names are defined within *infrastructure_provisioning.out.yml*
and specifically within the *infrastructure_provisioning.out* dict.

Names are long form dotted names of the following form (indexing starts at 0):
  * mongod.0
  * mongos.1
  * configsvr.2
  * workload_client.0

It is also possible to provide shorter names. For example the following are
all equivalent (0 is the default index):
  * mongod.0
  * mongod

Finally, aliases are also available for use:
  * md for mongod
  * ms for mongos
  * cs for configsvr (configsrv as an alternate spelling is also available)
  * wc for workload_client


$ ../run-dsi alias.py wc
52.33.116.65

$ ../run-dsi alias workload_client
52.33.116.65

$ ../run-dsi alias mongod.0
52.33.116.64

Note: when --export is specified the variable name will be the alias passed in. For example,
see the following invocations:

$ ../run-dsi alias mongod.0 --export
export mongod.0=52.33.116.64

$ ../run-dsi alias md --export
export md=52.33.116.64

Some expected usages of this utility are as follows.

The first example export wc and the second exports workload_client (with the same ip  addresss):

   $(../run-dsi alias wc --export)
   $(../run-dsi alias workload_client --export)

Eval could also be used:

   eval '../run-dsi alias md --export'

For more control over the variable name then the next example
sets a shell var called **mc** value:

readonly mc=$(../run-dsi alias workload_client)


"""


import sys

import argparse

from dsi.common.config import ConfigDict
from dsi.common.log import setup_logging

ALIASES = {
    "md": "mongod",
    "ms": "mongos",
    "cs": "configsvr",
    # I'm pretty sure I will transpose the following
    "configsrv": "configsvr",
    "wc": "workload_client",
}


def unalias(host, aliases=None):
    """ unalias the first portion of the host (a single name or up to the first dot).
    It should be possible to run the unalias or expand in either order and get the
    same result.

    For example, the default aliases are:
       md        --> mongod
       ms        --> mongos
       cs        --> configsvr
       configsrv --> configsvr
       wc        --> workload_client

    :param host str the (optionally) dotted host.
    :param aliases dict a mapping of short names to long names

    :returns str the expanded version of the dotted name
    """

    if aliases is None:
        aliases = ALIASES
    path = host
    pos = host.find(".")
    if pos != -1:
        path = host[:pos]

    unaliased = aliases.get(path, path)
    if unaliased != path:
        host = host.replace(path, unaliased)
    return host


def expand(host):
    """ expand the host (be it a single name or a dotted field).
    It should be possible to run the unalias or expand in either order and get the
    same result.

    For example:
       mongod             --> mongod.0.public_ip
       mongod.0           --> mongod.0.public_ip
       mongod.0.public_ip --> mongod.0.public_ip

       md                 --> md.0.public_ip
       md.0               --> md.0.public_ip
       md.0.public_ip     --> md.0.public_ip

    :param host str the (optionally) dotted host spec.

    :returns str the expanded version of the dotted name
    :raises ValueError if there are more than 2 dot's
    """

    nesting = host.count(".") + 1
    if nesting > 3:
        raise ValueError("The max level of nesting is 3: '{}'".format(host))

    if nesting == 1:
        host += ".0.public_ip"
    if nesting == 2:
        host += ".public_ip"

    return host


def parse_args(args):
    """ create the parser, parse the arguments and set up logging

    :returns tuple of parser and parsed arguments
    """
    parser = argparse.ArgumentParser(description="Expand an alias to a server ip address.")

    parser.add_argument("-d", "--debug", action="store_true", help="enable debug output")
    parser.add_argument("-e", "--export", action="store_true", help="enable output as shell export")
    parser.add_argument("--log-file", default="/tmp/expand.log", help="path to log file")
    parser.add_argument(
        "host", metavar="host", type=str, help="the alias to expand and convert to an ip"
    )

    arguments = parser.parse_args(args)
    setup_logging(arguments.debug, arguments.log_file)

    return arguments


def lookup_host(host, config):
    """
    get the ip address for a given host
    :param: str(host)  the dotted named of the host to use. This name is expected to
    have been fully expanded.
    :param: dict(config) object the root config dict
    :retutn: str the ip address
    """
    return config["infrastructure_provisioning"]["out"].lookup_path(host)


def main(argv):
    """ Main function. parse args and execute

    :param argv list the command line arguments excluding the program name. Default is
    sys.argv[1:]
    """
    args = parse_args(argv)
    config = ConfigDict("infrastructure_provisioning").load()

    host = args.host
    expanded = expand(host)
    unaliased = unalias(expanded)
    ip_address = lookup_host(unaliased, config)
    template = "{ip_address}"
    if args.export:
        template = "export {host}={ip_address}"

    print(template.format(host=host, ip_address=ip_address))


if __name__ == "__main__":
    main(sys.argv[1:])
