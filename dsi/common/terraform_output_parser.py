"""
Paser output from terraform and generate necessary cluster definition files to track public and
private IP addresses. This file will generate the file "infrastructure_provisioning.out.yml"
"""


import logging
import sys

from six.moves import range

LOG = logging.getLogger(__name__)


class TerraformOutputParser:  # pylint: disable=too-few-public-methods
    """
    DSI Terraform output, this class takes input from stdin or file, parses it and generates
    YML infrastructure_provisioning.out.yml.
    """

    INSTANCE_TYPES = [
        "private_config_ip",
        "private_ip_mc",
        "private_member_ip",
        "private_mongos_ip",
        "public_config_ip",
        "public_ip_mc",
        "public_member_ip",
        "public_mongos_ip",
    ]
    """Constructor. Uses either data from a file (input_file), data passed in as a string
    (terraform_output), or from stdin if neither are set.

    :param config: The system configuration
    :param input_file: (Optional) Name of file to read Terraform output from
    :param terraform_output: (Optional) String of terraform output to parse.

    """

    def __init__(self, config, input_file=None, terraform_output=None):
        self._file = input_file
        self._terraform_output = terraform_output
        # Dict to hold IP addresses.
        self._ips = {}
        self.config_obj = config
        self._parse_terraform_output()

    def _get_ips(self, pub, priv, category, out_data):
        if pub in self._ips:
            if len(self._ips[pub]) != len(self._ips[priv]):
                LOG.error("%s: public and private IP address counts mismatch!", category)
                raise ValueError(category + ": public and private IP address counts mismatch!")

            if self._ips[pub] and self._ips[pub][0]:
                # found category and IP address is not empty
                # IP address could be empty if category instance count is set to 0
                out_data[category] = []
                LOG.debug("_get_ips and non-empty pub in self._ips for category %s", category)
            else:
                # no ip address for this category, return the same back
                return out_data

            for i in range(len(self._ips[priv])):
                out_data[category].append(
                    {"public_ip": self._ips[pub][i], "private_ip": self._ips[priv][i]}
                )

        return out_data

    def _generate_output(self):
        """Update the configuration object for output from infrastructure_provisioning stage."""
        out_data = {}
        # mongod IP address
        out_data = self._get_ips("public_member_ip", "private_member_ip", "mongod", out_data)

        # workload_client(mc) IP addresses
        out_data = self._get_ips("public_ip_mc", "private_ip_mc", "workload_client", out_data)

        # mongos IP addresses
        out_data = self._get_ips("public_mongos_ip", "private_mongos_ip", "mongos", out_data)

        # configsvr IP addresses
        out_data = self._get_ips("public_config_ip", "private_config_ip", "configsvr", out_data)

        self.config_obj["infrastructure_provisioning"]["out"] = out_data

    def _parse_terraform_output(self):
        """To parse terraform output, and extract proper IP address"""
        if self._terraform_output:
            fread = self._terraform_output.splitlines()
        elif self._file is not None:
            LOG.info("Parse input file %s", self._file)
            fread = open(self._file, "r")
        else:
            fread = sys.stdin

        # Read file and parse it.
        for line in fread:
            items = line.rstrip("\n").split(" ")
            if items[0] in self.INSTANCE_TYPES:
                instance_type = items[0]
                LOG.debug("Found instance type %s", instance_type)
                self._ips[instance_type] = [item for item in items[2:] if item != ""]

    def write_output_files(self):
        """
        Write details to infrastructure_provisioning.out.yml
        """
        self._generate_output()
        self.config_obj.save()
