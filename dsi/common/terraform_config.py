"""
Take input from ConfigDict config files, output a terraform json file (cluster.json).
"""


import datetime
import json
import logging
import os
import socket
from uuid import uuid4

import requests

# RequestException is the parent exception for all requests.exceptions.*
# http://docs.python-requests.org/en/master/_modules/requests/exceptions/
from requests.exceptions import RequestException

LOG = logging.getLogger(__name__)

# http://docs.aws.amazon.com/AWSEC2/latest/UserGuide/placement-groups.html#concepts-placement-groups
INSTANCE_CLASSES_SUPPORT_PG = [
    "c3",
    "c4",
    "c5",
    "cc2",
    "m4",
    "m5",
    "r3",
    "r4",
    "x1",
    "x1e",
    "cr1",
    "d2",
    "i2",
    "i3",
    "hi1",
    "hs1",
    "f1",
    "g2",
    "g3",
    "p2",
    "p3",
]
TF_NODE_TYPES_TO_CHECK = ["mongod", "mongod_ebs", "mongod_seeded_ebs", "mongos", "workload"]


def is_placement_group_needed(node_type, tfvars):
    """
    True if node_type_count > 0 and node_type instance type supports placement groups.

    :param str node_type: A node type used in dsi configurations, such as "mongod", "mongod_ebs"...
    :param dict(str) tfvars: A dict with terraform variables from dsi configuration
    :return: Whether placement types are supported for given node_type
    :rtype: bool
    """

    if tfvars.get(node_type + "_instance_count", 0) > 0:
        assert node_type + "_instance_type" in tfvars
        instance_type = tfvars[node_type + "_instance_type"]
        instance_class = instance_type[0:2]
        if instance_class in INSTANCE_CLASSES_SUPPORT_PG:
            LOG.debug(
                "node_type=%s instance_type=%s DOES support placement group",
                node_type,
                instance_type,
            )
            return True
        LOG.debug(
            "node_type=%s instance_type=%s DOES NOT support placement group",
            node_type,
            instance_type,
        )

    return False


def generate_placement_group(tfvars, prefix="dsi"):
    """
    Define a placement_group name that is different for each cluster.

    For each of our node_type, check whether the EC2 instance_type class supports placement
    groups, and set those that do to the same unique value.

    :param dict(str) tfvars: A dict with terraform variables from dsi configuration
    :param str prefix: A prefix to use in the unique placement group name
    :return: the tfvars dict with unique string generated for each [node_type]_placement_group
    :rtype: dict(str)
    """

    unique_placement_group = "-".join([prefix, str(uuid4())])
    tfvars["placement_group"] = unique_placement_group
    LOG.debug("Generated new placement group: %s", unique_placement_group)

    for node_type in TF_NODE_TYPES_TO_CHECK:
        if is_placement_group_needed(node_type, tfvars):
            tfvars[node_type + "_placement_group"] = unique_placement_group

    return tfvars


def generate_expire_on_tag(hour_delta=2, _datetime_utcnow=datetime.datetime.utcnow):
    """
    This will generate expire-on tag based on current time or input time,
    expired-on tag will be (now + hour_delta) hours in UTC, default to 2 hours.

    :param int hour_delta: How many hours to add to _datetime_utcnow()
    :param function _datetime_utcnow: 0-argument function to call to get the current time as a
    datetime. Only meant to be used for testing purposes due to the inability to mock datetime.now.
    :return: A datestring with second-level precision, such as "2006-01-02 15:04:05"
    :rtype: str
    """
    now = _datetime_utcnow()
    expire_on = now + datetime.timedelta(hours=hour_delta)
    return expire_on.strftime("%Y-%m-%d %H:%M:%S")


def generate_runner_hostname():
    """
    Get the hostname of the runner.
    """
    return _do_generate_runner("public-hostname")


def _do_generate_runner(endpoint):
    """
    Get the hostname or IP of the runner.

    Will try to get the public host name from AWS metadata first, then from
    reverse lookup, and then fall back to using the local hostname

    :return: An ip address or a hostname
    :rtype: str
    """
    try:
        response = requests.get(
            "http://169.254.169.254/latest/meta-data/%s" % endpoint, timeout=0.01
        )
        response.raise_for_status()
        return response.text
    except RequestException as exception:
        LOG.info(
            "Terraform_config.py _do_generate_runner could not access AWS"
            "meta-data. Falling back to other methods"
        )
        LOG.info(repr(exception))

    try:
        response = requests.get("http://ip.42.pl/raw", timeout=1)
        response.raise_for_status()
        return response.text
    except RequestException as exception:
        LOG.info(
            "Terraform_config.py _do_generate_runner could not access ip.42.pl "
            "to get public IP. Falling back to gethostname"
        )
        LOG.info(repr(exception))

    return str(socket.gethostname(), encoding="utf-8")


def retrieve_runner_instance_id():
    """Get the instance id of the (evergreen) runner for labelling cluster

    """
    try:
        response = requests.get("http://169.254.169.254/latest/meta-data/instance-id", timeout=0.01)
        response.raise_for_status()
        return response.text
    except RequestException as exception:
        LOG.info(
            "Terraform_config.py retrieve_runner_instance_id could not access AWS" "instance id."
        )
        LOG.info(repr(exception))
        return "deploying host is not an EC2 instance"


class TerraformConfiguration:
    """
    DSI Terraform configuration
    """

    def __init__(self, config):
        """
        Instantiate a TerraformConfiguration object

        :param ConfigDict config: A configuration object
        :param str file_name: The name of the output json file
        """
        self.config = config

        self.tfvars = {}
        self.set_tfvars()
        # Since this is a new cluster, generate a unique id for the placement group to be
        self.tfvars = generate_placement_group(self.tfvars, self.tfvars.get("cluster_name"))
        # Cluster metadata
        self.tfvars["runner_hostname"] = generate_runner_hostname()

        self.refresh_tfvars()

    def set_tfvars(self):
        """
        Update self.tfvars from self.config.

        For a new cluster, this is the initialization of self.tfvars. When reusing an existing
        cluster, we expect this to be a no-op, but in the rare case that input config has been
        changed, we want to capture it and then terraform to take corrective action based on it.
        """
        self.tfvars.update(self.config["infrastructure_provisioning"]["tfvars"].as_dict())
        # For now, we just fold the tags subsection into the top level. Beware of collisions!
        # This is to say, our downstream terraform files don't support passing through arbitrary
        # tags (yet).
        tags = self.tfvars.pop("tags")
        self.tfvars.update(tags)
        self.tfvars.pop("expire-on-delta")

    def refresh_tfvars(self):
        """Compute or update various generated fields in self.tfvars"""

        # Careful there: The tag looked at by the reaper is "expire-on". To match, the yaml file
        # config option is expire-on-delta. However, terraform variable is expire_on.
        self.tfvars["expire_on"] = generate_expire_on_tag(
            self.config["infrastructure_provisioning"]["tfvars"]["tags"]["expire-on-delta"]
        )

        # Cluster metadata
        self.tfvars["status"] = "running"
        if "runtime" in self.config and "task_id" in self.config["runtime"]:
            self.tfvars["task_id"] = self.config["runtime"]["task_id"]
        else:
            LOG.info("Couldn't find runtime.task_id in config")

    def to_json(self, compact=False, file_name=None):
        """
        To create JSON configuration string.

        :param bool compact: Whether to use a more compact form of json.dumps
        :param str file_name: A file_name to write json into. If None, json is simply returned.
        :return: tfvars in json syntax
        :rtype: str
        """
        if compact:
            json_str = json.dumps(self.tfvars, sort_keys=True, separators=(",", ":"))
        else:
            json_str = json.dumps(self.tfvars, sort_keys=True, indent=4)

        LOG.info(json_str)
        if file_name is not None:
            # write to file as well
            with open(file_name, "w") as file_handle:
                file_handle.write(json_str)
        return json_str

    def get_json(self, file_name):
        """
        Read back a json file created by to_json

        When reusing a cluster, we specifically need to continue using the same placement group name
        and not generate a new string each time.

        :param str file_name: The file_name to read json content from
        :return: True if file_name existed and was read
        """
        if os.path.isfile(file_name):
            with open(file_name, "r") as file_handle:
                LOG.info("Reusing terraform variables from existing %s file.", file_name)
                self.tfvars = json.load(file_handle)
                return True

        return False
