#!/usr/bin/env python3.7

"""
Provision AWS resources using terraform
"""

import datetime
import glob
import os
import re
import shutil
import subprocess
from functools import partial

import argparse
import structlog

from dsi.common import host_factory
from dsi.common import host_utils
from dsi.common import utils
from dsi.common import whereami
from dsi.common.command_runner import run_pre_post_commands, EXCEPTION_BEHAVIOR
from dsi.common.config import ConfigDict
from dsi.common.log import setup_logging
from dsi.common.remote_host import RemoteHost
from dsi.common.terraform_config import TerraformConfiguration
from dsi.common.terraform_output_parser import TerraformOutputParser
from dsi.common.thread_runner import run_threads
from dsi.infrastructure_teardown import destroy_resources

LOG = structlog.get_logger(__name__)

# Set terraform parallelism so it can create multiple resources
# The number determines the number it can create at a time together
TERRAFORM_PARALLELISM = 20
TF_LOG_PATH = "terraform.debug.log"
PROVISION_LOG_PATH = "terraform.stdout.log"
CLUSTER_JSON = "cluster.json"


def rmtree_when_present(tree_path):
    """Remove the given tree only if present"""
    LOG.debug("rmtree_when_present start", arg=tree_path)
    if os.path.exists(tree_path):
        shutil.rmtree(tree_path)
    else:
        LOG.info("rmtree_when_present: No such path", arg=tree_path)


# pylint: disable=too-many-instance-attributes
class Provisioner:
    """ Used to provision AWS resources """

    def __init__(
        self, config, log_file=TF_LOG_PATH, provisioning_file=PROVISION_LOG_PATH, verbose=False
    ):
        self.config = config
        ssh_key_file = config["infrastructure_provisioning"]["tfvars"]["ssh_key_file"]
        ssh_key_file = os.path.expanduser(ssh_key_file)
        self.ssh_key_file = ssh_key_file
        self.ssh_key_name = config["infrastructure_provisioning"]["tfvars"]["ssh_key_name"]
        self.aws_access_key, self.aws_secret_key = utils.read_aws_credentials(config)
        self.cluster = config["infrastructure_provisioning"]["tfvars"].get(
            "cluster_name", "missing_cluster_name"
        )
        self.var_file = None
        self.parallelism = "-parallelism=" + str(TERRAFORM_PARALLELISM)
        self.terraform = utils.find_terraform()
        LOG.info("Using terraform binary:", path=self.terraform)
        self.tf_log_path = TF_LOG_PATH
        self.hostnames_method = (
            config["infrastructure_provisioning"].get("hostnames", {}).get("method")
        )

        os.environ["TF_LOG"] = "DEBUG"
        os.environ["TF_LOG_PATH"] = TF_LOG_PATH

        self.dsi_dir = whereami.dsi_repo_path()
        self.bin_dir = whereami.dsi_repo_path("dsi")

        self.log_file = log_file
        self.verbose = verbose
        self.provisioning_file = provisioning_file

        # Counter-intuitively, _None_ has the following stream semantics.
        # "With the default settings of None, no redirection will occur; the child's file handles
        # will be inherited from the parent"
        # @see subprocess.Popen
        if self.verbose:
            self.stdout = self.stderr = None
        else:
            LOG.info("Redirecting terraform output to file", path=self.provisioning_file)
            self.stdout = self.stderr = open(self.provisioning_file, "w")

    def setup_security_tf(self):
        """
        Generate the security.tf file
        """
        # Write security.tf.
        with open(os.path.join("security.tf"), "w") as security:
            security.write('provider "aws" {\n')
            security.write('    access_key = "{0}"\n'.format(self.aws_access_key))
            security.write('    secret_key = "{0}"\n'.format(self.aws_secret_key))
            security.write("    region = var.region\n")
            security.write(
                '    version = "{}"\n'.format(
                    self.config["infrastructure_provisioning"]["terraform"]["aws_required_version"]
                )
            )
            security.write("}\n")
            security.write('variable "key_name" {\n')
            security.write('    default = "{0}"\n'.format(self.ssh_key_name))
            security.write("}\n")
            security.write('variable "key_file" {\n')
            security.write('    default = "{0}"\n'.format(self.ssh_key_file))
            security.write("}")

    def setup_terraform_tf(self):
        """
        Copy terraform tf files and remote-scripts to work directory
        """
        # Copy terraform files and remote-scripts to work directory
        directory = os.getcwd()
        cluster_path = os.path.join(self.dsi_dir, "terraform", "default")
        remote_scripts_path = os.path.join(self.dsi_dir, "terraform", "remote-scripts")
        LOG.debug("Cluster path is", path=cluster_path)
        for filename in glob.glob(os.path.join(cluster_path, "*")):
            shutil.copy(filename, directory)
            LOG.debug("Copied file to work directory.", source_path=filename, target_path=directory)
        remote_scripts_target = os.path.join(directory, "remote-scripts")
        LOG.debug(
            "Create fresh directory and copy remote scripts.",
            source_path=remote_scripts_path,
            target_path=remote_scripts_target,
        )
        rmtree_when_present(remote_scripts_target)
        os.mkdir(remote_scripts_target)
        for filename in glob.glob(os.path.join(remote_scripts_path, "*")):
            shutil.copy(filename, remote_scripts_target)
            LOG.debug(
                "Copied file to work directory.",
                source_path=filename,
                target_path=remote_scripts_target,
            )

        # Copy modules
        modules_path = os.path.join(self.dsi_dir, "terraform", "modules")
        modules_target = os.path.join(directory, "modules")
        rmtree_when_present(modules_target)
        shutil.copytree(modules_path, modules_target)
        LOG.debug(
            "Copied file to work directory.", source_path=modules_path, target_path=modules_target
        )

    def provision_resources(self):
        """
        Function used to actually provision the resources
        """
        self.setup_cluster()

    def setup_cluster(self):
        """
        Runs terraform to provision the cluster
        """
        # Create and copy needed security.tf and terraform.tf files into current work directory
        self.setup_security_tf()
        self.setup_terraform_tf()
        LOG.info("terraform: init")
        subprocess.check_call(
            [self.terraform, "init", "-upgrade"], stdout=self.stdout, stderr=self.stderr
        )
        tf_config = TerraformConfiguration(self.config)
        tf_config.to_json(file_name=CLUSTER_JSON)  # pylint: disable=no-member
        self.var_file = "-var-file={}".format(CLUSTER_JSON)
        LOG.info("Creating AWS cluster.", cluster=self.cluster)
        LOG.info("terraform: apply")
        # -auto-approve is like -y for yum: Without it terraform will wait for someone to type "yes"
        terraform_command = [
            self.terraform,
            "apply",
            self.var_file,
            self.parallelism,
            "-auto-approve",
        ]
        # Disk warmup for initialsync-logkeeper takes about 4 hours. This will save
        # about $12 by delaying deployment of the two other nodes.
        if self.cluster == "initialsync-logkeeper":
            terraform_command.extend(
                ["-var=mongod_ebs_instance_count=0", "-var=workload_instance_count=0"]
            )
        try:
            subprocess.check_call(terraform_command, stdout=self.stdout, stderr=self.stderr)
            if self.cluster == "initialsync-logkeeper":
                subprocess.check_call(
                    [self.terraform, "apply", self.var_file, self.parallelism, "-auto-approve"],
                    stdout=self.stdout,
                    stderr=self.stderr,
                )
            LOG.info("terraform: refresh")
            subprocess.check_call(
                [self.terraform, "refresh", self.var_file], stdout=self.stdout, stderr=self.stderr
            )
            LOG.info("terraform: plan")
            subprocess.check_call(
                [self.terraform, "plan", "-detailed-exitcode", self.var_file],
                stdout=self.stdout,
                stderr=self.stderr,
            )
            LOG.info("terraform: output")
            subprocess.check_call([self.terraform, "output"])
            terraform_output = run_and_save_output([self.terraform, "output"])
            tf_parser = TerraformOutputParser(config=self.config, terraform_output=terraform_output)
            tf_parser.write_output_files()

            # Write hostnames to /etc/hosts
            self.setup_hostnames()
            with open("infrastructure_provisioning.out.yml", "r") as provisioning_out_yaml:
                LOG.info("Contents of infrastructure_provisioning.out.yml:")
                LOG.info(provisioning_out_yaml.read())
            LOG.info("EC2 resources provisioned/updated successfully.")
            # Run post provisioning scripts.
            run_pre_post_commands(
                "post_provisioning",
                [self.config["infrastructure_provisioning"]],
                self.config,
                EXCEPTION_BEHAVIOR.EXIT,
            )
        except Exception as exception:
            LOG.error("Failed to provision EC2 resources.", exc_info=True)
            if self.stderr is not None:
                self.stderr.close()
            self.print_terraform_errors()
            LOG.error("Releasing any EC2 resources that did deploy.")
            destroy_resources()
            raise exception

    @staticmethod
    def _tail(filename):
        return subprocess.check_output(["tail", "-n", "100", filename])

    def print_terraform_errors(self, logger=LOG, tailer=None):
        """
        Grep and print errors from terraform.log and provisioning.log.

        Since Summer 2017, Terraform usually fails to print the actual EC2 error that caused a
        deployment to fail, and instead just keeps spinning until you get a timeout error instead.
        The real error, such as InsufficientInstanceCapacity, is however logged in our very verbose
        terraform.log file. As a convenience to the user, we will find and print errors from it.
        See PERF-1095 for more info.
        """
        if tailer is None:
            # pylint: disable=unnecessary-lambda
            tailer = lambda f: Provisioner._tail(f)

        # pylint: disable=too-many-nested-blocks
        strings_to_grep = {"<Response><Errors><Error>"}
        strings_to_ignore = {"The specified rule does not exist in this security group."}
        seen_errors = set()

        # Print errors from terraform.log.
        for line in open(self.tf_log_path):
            for to_grep in strings_to_grep:
                if to_grep in line:
                    print_it = True
                    for to_ignore in strings_to_ignore:
                        if to_ignore in line:
                            print_it = False

                    if print_it:
                        line = line.strip()
                        # Terraform is very persistent, so it will often retry a non-recoverable
                        # error multiple times, and the verbose log is then full with the same
                        # error. We print each kind of error only once. So we need to keep track
                        # of them.
                        result = re.search(r"<Code>(.+)</Code>", line)
                        if result:
                            error_code = result.group(1)
                            if error_code not in seen_errors:
                                seen_errors.add(error_code)
                                logger.error(line)
                        else:
                            logger.error(line)

        if seen_errors:
            logger.error("For more info, see:", path=self.tf_log_path)

        # Print tail of provisioning.log.
        if os.path.exists(self.provisioning_file):
            logger.error(tailer(self.provisioning_file))
            logger.error("For more info, see:", path=self.provisioning_file)

    def setup_hostnames(self):
        """
        Write hostnames to /etc/hosts on deployed instances.

        Example:

            10.2.0.100  md md0 mongod0 mongod0.dsi.10gen.cc
        """
        if self.hostnames_method != "/etc/hosts":
            LOG.debug("Not configuring hostnames.", method=self.hostnames_method)
            return
        LOG.info("Write hostnames to /etc/hosts on deployed instances.")

        output = self._build_hosts_file()
        self._write_hosts_file(output)
        self.config.save()

    def _build_hosts_file(self):
        output = []
        host_types = ["mongod", "mongos", "configsvr", "workload_client"]
        short_names = {"mongod": "md", "mongos": "ms", "configsvr": "cs", "workload_client": "wc"}
        domain = self.config["infrastructure_provisioning"]["hostnames"]["domain"]
        out = self.config["infrastructure_provisioning"].get("out")
        LOG.debug("infrastructure_provisioning.out", out=out)

        if not isinstance(out, ConfigDict):
            return output

        for key in host_types:
            i = 0
            primary_hostname = ""
            for host in out.get(key, {}):
                # As usual, we use the private network address if available.
                ip_addr = host["private_ip"] if "private_ip" in host else host["public_ip"]
                # Example: 10.1.2.3\t
                line = "{}\t".format(ip_addr)
                if i == 0:
                    # md is short for md0, ms for ms0, etc...
                    # Example: 10.1.2.3    md
                    line += short_names[key] + " "
                # Example: 10.1.2.3    md md0
                line += short_names[key] + str(i) + " "
                # Example: 10.1.2.3    md md0 mongod0
                line += key + str(i) + " "
                primary_hostname = key + str(i) + " "
                if domain:
                    # Example: 10.1.2.3    md md0 mongod0 mongod0.dsitest.dev
                    line += key + str(i) + "." + domain
                    primary_hostname = key + str(i) + "." + domain
                output.append(line)
                # Also record the hostname in ConfigDict (out.yml)
                self.config["infrastructure_provisioning"]["out"][key][i][
                    "private_hostname"
                ] = primary_hostname
                i = i + 1

        return output

    def _write_hosts_file(self, output):
        hosts = host_utils.extract_hosts("all_hosts", self.config)
        LOG.debug("Write /etc/hosts on all hosts.", hosts=hosts)
        run_threads([partial(_write_hosts_file_thread, host_info, output) for host_info in hosts])


def _write_hosts_file_thread(host_info, output):
    timestamp = datetime.datetime.now().isoformat("T")
    upload_file = "/tmp/hosts.new." + timestamp
    bak_file = "/etc/hosts.bak." + timestamp
    argv = [
        ["sudo", "cp", "/etc/hosts", bak_file],
        ["sudo", "bash", "-c", "'cat {} >> /etc/hosts'".format(upload_file)],
    ]

    file_contents = "###### BELOW GENERATED BY DSI ####################\n"
    file_contents += "\n".join(output) + "\n"
    target_host = host_factory.make_host(host_info)
    assert isinstance(target_host, RemoteHost), "/etc/hosts writer must be a RemoteHost"
    target_host.create_file(upload_file, file_contents)
    target_host.run(argv)


# pylint: enable=too-many-instance-attributes


def run_and_save_output(command):
    """
    Used to replicate the tee command. Sends the output from the command
    to both the log_file and to stdout.
    """
    process = subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding="utf-8"
    )
    # This ensures that as subprocess runs the command, the output is caught in real time
    # and is not buffered by subprocess.
    lines = []
    for line in process.stdout:
        LOG.debug(line)
        lines.append(line)
    process.communicate()
    output = "".join(lines)
    if process.returncode != 0:
        raise subprocess.CalledProcessError(process.returncode, command, output=output)
    return output


def parse_command_line():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Provision EC2 instances on AWS using terraform.")
    parser.add_argument("--log-file", help="path to log file")
    parser.add_argument("-d", "--debug", action="store_true", help="enable debug output")
    args = parser.parse_args()
    return args


def main():
    """ Main function """
    args = parse_command_line()
    setup_logging(args.debug, args.log_file)
    config = ConfigDict("infrastructure_provisioning")
    config.load()
    provisioner = Provisioner(config, verbose=args.debug)
    provisioner.provision_resources()


if __name__ == "__main__":
    main()
