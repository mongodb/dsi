"""
Utilities for discovering and cleaning up resources in AWS
"""

import logging
import time

import boto3
import botocore

LOG = logging.getLogger(__name__)


def make_aws_filter(name, value):
    """
    Helper to construct an AWS Filter. Many boto3 commands take an argument of the form:
    Filter=[{'Name': 'some string',
            'Values': [list, of, values]}]

    :param str name: The value to put after Name.
    :param list values: The value to put in the Values list.
    :returns: The formatted Filter object
    :rtype: list
    """

    return [{"Name": "{}".format(name), "Values": [value]}]


def make_aws_filter_tags(tag_name, tag_value):
    """
    Helper to construct and AWS Filter based on one tag.

    :param str tag_name: The name of the tag
    :param str tag_value: The value to use with the tag
    :returns: The formatted Filter object
    :rtype: list
    """

    return make_aws_filter("tag:{}".format(tag_name), tag_value)


class AwsCleanup:
    """
    A set of utilities wrapping boto3.client.
    """

    def __init__(self, region_name=None):
        if region_name:
            boto3.setup_default_session(region_name=region_name)
        self.client = boto3.client("ec2")

    def get_all_instances(self):
        """ Get a list of all the instances in the region.

        :returns: List of ec2 instances
        :rtype: list(boto3.instance)
        """
        return [
            instance
            for reservation in self.client.describe_instances()["Reservations"]
            for instance in reservation["Instances"]
        ]

    def find_instances_tagged(self, tag_key, tag_value):
        """
        Get a list of all the instances with given tag key/value pair in the region.

        :param str tag_key: The name of the tag
        :param str tag_value: The value of the tag
        :returns: List of ec2 instances
        :rtype: list(boto3.instance)
        """
        filters = make_aws_filter_tags(tag_key, tag_value)
        LOG.debug("Finding instances with filters %s", filters)
        return [
            instance
            for reservation in self.client.describe_instances(Filters=filters)["Reservations"]
            for instance in reservation["Instances"]
        ]

    def _find_instances_tagged_not_terminated(self, tag_key, tag_value):
        """
        Get a list of all the instances with given tag key/value pair in the region that are not in
        the terminated state.

        :param str tag_key: The name of the tag
        :param str tag_value: The value of the tag
        :returns: List of ec2 instances ids
        :rtype: list(str)
        """
        return [
            instance["InstanceId"]
            for instance in self.find_instances_tagged(tag_key, tag_value)
            if instance["State"]["Name"] != "terminated"
        ]

    def get_active_vpcs(self):
        """
        Return all vpcs associated with any active instance.

        :returns: List of vpc ids
        :rtype: list(str)
        """
        return set(
            instance["VpcId"] for instance in self.get_all_instances() if "VpcId" in instance
        )

    def get_vpcs_tagged(self, tag_key, tag_value):
        """
        :param str tag_key: The name of the tag
        :param str tag_value: The value of the tag
        :returns: list of vpc ids for vpcs with a given tag.

        :rtype: list(str)
        """
        return set(
            vpc["VpcId"]
            for vpc in self.client.describe_vpcs(Filters=make_aws_filter_tags(tag_key, tag_value))[
                "Vpcs"
            ]
        )

    def get_placement_groups(self, dry_run=False):
        """
        Get a list of all placement groups names.
        :rtype: list(str)
        """
        groups = self.client.describe_placement_groups(DryRun=dry_run)
        return [
            group["GroupName"] for group in groups["PlacementGroups"] if groups["PlacementGroups"]
        ]

    def find_stranded_vpcs_tagged(
        self, tag_key="owner", tag_value="perf-terraform-alerts@10gen.com"
    ):
        """
        Find stranded vpcs. A vpc is stranded if it exists, but is not associated with any
        instances.

        :param str tag_key: The name of the tag.
        :param str tag_value: The value of the tag.
        :returns: List of vpcs ids
        :rtype: list(str)
        """
        return self.get_vpcs_tagged(tag_key, tag_value) - self.get_active_vpcs()

    def find_security_groups_vpc(self, vpcid):
        """
        Find all the security groups associated with a VPCID.

        :param str vpcid: The VPCID to check.
        :returns: The GroupIds of the matching security groups.
        :rtype: list(str)
        """
        return set(
            sg["GroupId"]
            for sg in self.client.describe_security_groups(
                Filters=make_aws_filter("vpc-id", vpcid)
            )["SecurityGroups"]
            if sg["GroupName"] != "default"
        )

    def find_subnets_vpc(self, vpcid):
        """
        Find all the subnets associated with a VPCID.

        :param str vpcid: The VPCID to check.
        :returns: The SubnetIds of the matching security groups.
        :rtype: list(str)
        """
        return set(
            subnet["SubnetId"]
            for subnet in self.client.describe_subnets(Filters=make_aws_filter("vpc-id", vpcid))[
                "Subnets"
            ]
        )

    def find_route_tables_vpc(self, vpcid):
        """
        Find all the route tables associated with a VPCID.

        :param str vpcid: The VPCID to check.
        :returns: The RouteTableIds of the matching security groups.
        :rtype: list(str)
        """
        return set(
            route["RouteTableId"]
            for route in self.client.describe_route_tables(
                Filters=make_aws_filter("vpc-id", vpcid)
            )["RouteTables"]
        )

    def find_internet_gateways_vpc(self, vpcid):
        """
        Find all internet gateways associated with a VPCID.

        :param str vpcid: The VPCID to check.
        :returns: The InternetGatewayIds of the matching security groups.
        :rtype: list(str)
        """
        return set(
            gateway["InternetGatewayId"]
            for gateway in self.client.describe_internet_gateways(
                Filters=make_aws_filter("attachment.vpc-id", vpcid)
            )["InternetGateways"]
        )

    def delete_security_groups_vpc(self, vpcid):
        """
        Delete all the security groups associated with a given VPC.

        :param vpcid: The VpcId of the VPC
        """
        for sgid in self.find_security_groups_vpc(vpcid):
            self.client.delete_security_group(GroupId=sgid)

    def delete_subnets_vpc(self, vpcid):
        """
        Delete all the subnets associated with a given VPC.

        :param vpcid: The VpcId of the VPC
        """
        for subnetid in self.find_subnets_vpc(vpcid):
            self.client.delete_subnet(SubnetId=subnetid)

    def delete_route_tables_vpc(self, vpcid):
        """
        Delete all the route tables associated with a given VPC. Note that not all route tables can
        be deleted. This function does a best effort.

        :param vpcid: The VpcId of the VPC
        """
        for routeid in self.find_route_tables_vpc(vpcid):
            try:
                self.client.delete_route_table(RouteTableId=routeid)
            # I don't know the correct exception list to catch here. The documenation is lacking.
            except Exception as e:  # pylint: disable=broad-except
                LOG.warning(
                    "Unable to delete route table %s. If there are no ERRORS this can be ignored.",
                    routeid,
                )
                LOG.warning(e)

    def delete_internet_gateways_vpc(self, vpcid):
        """
        Delete all internet gateways associed with a given VPC.

        This detaches the gateway, and then deletes it.

        :param vpcid: The VpcId of the VPC.
        """
        for gatewayid in self.find_internet_gateways_vpc(vpcid):
            self.client.detach_internet_gateway(InternetGatewayId=gatewayid, VpcId=vpcid)
            self.client.delete_internet_gateway(InternetGatewayId=gatewayid)

    def delete_idle_vpc(self, vpcid):
        """
        Delete a given vpc if it is idle.

        :param str vpcid: The ID of the vpc to delete.
        """
        # Check that not in active vpcs
        assert vpcid not in self.get_active_vpcs(), "Trying to delete non idle vpc"

        # Cleanup related items
        self.delete_security_groups_vpc(vpcid)
        self.delete_subnets_vpc(vpcid)
        self.delete_route_tables_vpc(vpcid)
        self.delete_internet_gateways_vpc(vpcid)

        # Actually delete the vpc
        self.client.delete_vpc(VpcId=vpcid)

    def delete_stranded_vpcs(self, dry_run=False):
        """
        Find and delete all stranded VPCs. A VPC is stranded if it has no instances.

        :param bool dry_run: If true, don't actually delete the vpcs.
        """
        LOG.info(
            "There are %i stranded vpcs to delete. Deleting...",
            len(self.find_stranded_vpcs_tagged()),
        )
        for vpcid in self.find_stranded_vpcs_tagged():
            LOG.info("Deleting VPC with id %s", vpcid)
            if not dry_run:
                self.delete_idle_vpc(vpcid)

    def delete_cluster_by_tag(self, tag_key, tag_value, dry_run=False):
        """
        Delete a complete DSI cluster, based on a tag. This includes terminating all associated
        instances and VPCs.

        :param str tag_key: The name of the tag
        :param str tag_value: The value of the tag
        :param bool dry_run: If true, don't actually delete the vpcs.
        """
        vpcids = self.get_vpcs_tagged(tag_key, tag_value)
        instance_ids = self._find_instances_tagged_not_terminated(tag_key, tag_value)
        LOG.info("delete_cluster_by tag called with key %s and value %s", tag_key, tag_value)
        LOG.info("Found the following vpcids: %s", str(vpcids))
        LOG.info("Found the following instance ids: %s", str(instance_ids))
        LOG.info("Deleting instances %s", str(instance_ids))
        if not dry_run and instance_ids:
            count = 0
            # This is in a loop with a sleep because the client.terminate_instances is non-blocking
            # and we need to make sure the instances have actually been terminated.
            while instance_ids and count < 180:
                LOG.info(
                    "Not all instances in terminated state yet. Waiting on %s", str(instance_ids)
                )
                self.client.terminate_instances(InstanceIds=instance_ids)
                time.sleep(1)
                count += 1
                instance_ids = self._find_instances_tagged_not_terminated(tag_key, tag_value)
        for vpcid in vpcids:
            LOG.info("Deleting vpc %s", vpcid)
            if not dry_run:
                self.delete_idle_vpc(vpcid)

    def delete_placement_groups(self, dry_run=False):
        """
        Delete all placement groups. A failure can mean that the placement group is still in use.

        :param bool dry_run: If true, don't actually delete the placement groups.
        """
        groups = self.get_placement_groups(dry_run=dry_run)
        LOG.info("delete_placement_group: found %s groups", len(groups))
        for group in groups:
            try:
                self.client.delete_placement_group(GroupName=group, DryRun=dry_run)
                LOG.info("%s deleted", group)
            except botocore.exceptions.ClientError as e:
                if e.response["Error"]["Code"] != "InvalidPlacementGroup.InUse":
                    raise e
                LOG.debug("%s skipped, in use.", group)
