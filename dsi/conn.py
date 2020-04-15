#!/usr/bin/env python3.7

"""
Thin wrapper around ssh. This script *should* allow ease of access to remote
provisioned servers, either as full dotted names or shorter aliases.

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

The command can be run interactively or with a command. Like the following:

$ ./dsi/conn.py wc
Last login: Tue Mar 28 12:05:43 2017 from 77.107.233.162

       __|  __|_  )
       _|  (     /   Amazon Linux AMI
      ___|___|___|

https://aws.amazon.com/amazon-linux-ami/2015.03-release-notes/
41 package(s) needed for security, out of 133 available
Run "sudo yum update" to apply all updates.
Amazon Linux version 2016.09 is available.
[ec2-user@ip-10-2-0-98 ~]$ logout
Connection to 52.33.116.65 closed.

$ ./dsi/conn.py wc -c 'ls -lh '
total 5.8M
lrwxrwxrwx  1 ec2-user ec2-user   17 Mar 27 10:47 data -> /media/ephemeral0
drwxrwxr-x 17 ec2-user ec2-user  12K Mar 27 10:48 fio
-rw-rw-r--  1 ec2-user ec2-user 1.5M Mar 27 10:48 mongo-java-driver-3.2.2.jar
-rwxrwxr-x  1 ec2-user ec2-user 4.4M Mar 27 10:48 netfio

$ echo "find me " | ./dsi/conn.py wc -c 'cat - > file'


To run the same command on multiple hosts, use:

$ ./dsi/conn.py md.0 md.1 md.2 md.3  -c 'ls -lh '

Currently, support is not provided for here documents (http://tldp.org/LDP/abs/html/here-docs.html)
as command line parameters.
"""


import logging
import os
import sys
import threading

import argparse

from dsi import alias
from dsi.common.config import ConfigDict
from dsi.common.log import setup_logging

LOGGER = logging.getLogger(__name__)


def parse_args(args):
    """ create the parser, parse the arguments and set up logging

    :returns tuple of parser and parsed arguments
    """
    parser = argparse.ArgumentParser(
        description="Create a connection to the remote server.\
                                     For instructions on setting up dsi locally"
    )

    parser.add_argument("-d", "--debug", action="store_true", help="enable debug output")
    parser.add_argument(
        "--dryrun",
        action="store_true",
        default=False,
        help="Do not run the command, just evaluate it.",
    )
    parser.add_argument("--log-file", help="path to log file")
    parser.add_argument("-s", "--ssh", default="ssh", help="the ssh location")
    parser.add_argument(
        "host", metavar="host", nargs="+", type=str, help="the path of the host to connect to"
    )

    parser.add_argument(
        "-c",
        "--command",
        metavar="command",
        nargs="?",
        action="append",
        default=[],
        help="the remote command to run",
    )

    arguments = parser.parse_args(args)
    setup_logging(arguments.debug, arguments.log_file)

    return parser, arguments


def remote_cmd(host, command, config, args):
    """
    run the remote command
    :param host str the dotted named of the host to use. This name is expected to
    have been fully expanded.
    :param command str the command to run or an empty str or None for interactive
    :param config object the root config dict
    :param args object the parsed arguments
    """
    pemfile = config["infrastructure_provisioning"]["tfvars"]["ssh_key_file"]
    pemfile = os.path.expanduser(pemfile)
    sshuser = config["infrastructure_provisioning"]["tfvars"]["ssh_user"]
    ip_address = config["infrastructure_provisioning"]["out"].lookup_path(host)

    if not command:
        command = ""
    cmd = [
        args.ssh,
        "-A",
        "-i",
        pemfile,
        "@".join(x for x in [sshuser, ip_address] if x),
        "'{}'".format(command),
    ]

    LOGGER.info("conn: %s", " ".join(cmd))
    if not args.dryrun:
        os.system(" ".join(cmd))


def main(argv):
    """ Main function. parse args and execute

    :param argv list the command line arguments excluding the program name. Default is
    sys.argv[1:]
    """
    parser, args = parse_args(argv)
    config = ConfigDict("infrastructure_provisioning").load()

    if len(args.host) == 1:
        host = alias.expand(args.host[0])
        host = alias.unalias(host)
        cmd = ";".join(args.command)
        remote_cmd(host, cmd, config, args)
    else:

        if not args.command:
            print("You must provide a command with more than one host\n\n")
            parser.print_help()
            sys.exit(1)

        cmd = ";".join(args.command)
        threads = []
        for host in args.host:
            host = alias.expand(host)
            host = alias.unalias(host)
            thread = threading.Thread(target=remote_cmd, args=(host, cmd, config, args))
            threads.append(thread)
            thread.start()
        for thread in threads:
            thread.join()


if __name__ == "__main__":
    main(sys.argv[1:])
