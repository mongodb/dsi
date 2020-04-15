"""
Entry points into AWS cleanup code. Setuptools creates executables based off of these functions.
"""
import argparse
import logging
import sys

from aws_tools import aws_cleanup
from aws_tools import log

REGIONS = ["us-west-2", "us-east-1", "eu-west-1"]

LOG = logging.getLogger(__name__)


def base_arg_parsing(description):
    """
    Helper function to setup common arguments for argument parsing.
    :param description: Description for the calling entry point function. Used in help message.

    """

    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("-d", "--debug", action="store_true", help="enable debug output")
    parser.add_argument("--log-file", help="path to log file")
    parser.add_argument(
        "-n", "--dry-run", action="store_true", help="Dry run only. Show what we would do."
    )
    return parser


def delete_stranded_vpcs(argv=None):
    """
    Entry point to delete stranded DSI VPCs.

    :param list argv: Input arguments. Uses sys.argv[1:] if None.

    """
    if argv is None:
        argv = sys.argv[1:]

    parser = base_arg_parsing("Delete Stranded VPCs")
    args = parser.parse_args(argv)
    log.setup_logging(args.debug, args.log_file)
    for region in REGIONS:
        LOG.info("Cleaning up stranded VPCs in region %s", region)
        cleanup = aws_cleanup.AwsCleanup(region_name=region)
        cleanup.delete_stranded_vpcs(dry_run=args.dry_run)


def delete_cluster_by_tag(argv=None):
    """
    Entry point to delete a DSI cluster based on a tag.

    :param list argv: Input arguments. Uses sys.argv[1:] if None.

    """
    if argv is None:
        argv = sys.argv[1:]

    parser = base_arg_parsing("Delete Cluster by Tag")
    parser.add_argument("-k", "--key", required=True, help="Tag key to use to identify cluster")
    parser.add_argument("-v", "--value", required=True, help="Tag value to use to identify cluster")
    args = parser.parse_args(argv)

    log.setup_logging(args.debug, args.log_file)

    for region in REGIONS:
        LOG.info(
            "Checking for cluster with tag %s and value %s in region  %s",
            args.key,
            args.value,
            region,
        )
        cleanup = aws_cleanup.AwsCleanup(region_name=region)
        cleanup.delete_cluster_by_tag(args.key, args.value, args.dry_run)


def delete_cluster_for_task(argv=None):
    """
    Entry point to delete a DSI cluster based on a task ID.

    :param list argv: Input arguments. Uses sys.argv[1:] if None.

    """
    if argv is None:
        argv = sys.argv[1:]

    parser = base_arg_parsing("Delete Cluster for a Task ID")
    parser.add_argument("-t", "--task", required=True, help="TaskID of clusters to delete")
    args = parser.parse_args(argv)

    log.setup_logging(args.debug, args.log_file)

    for region in REGIONS:
        LOG.info("Checking for cluster for task %s in region  %s", args.task, region)
        cleanup = aws_cleanup.AwsCleanup(region_name=region)
        cleanup.delete_cluster_by_tag("task_id", args.task, args.dry_run)


def delete_cluster_for_runner(argv=None):
    """
    Entry point to delete a DSI cluster based on a runner.

    :param list argv: Input arguments. Uses sys.argv[1:] if None.

    """
    if argv is None:
        argv = sys.argv[1:]

    parser = base_arg_parsing("Delete Cluster for a runner")
    parser.add_argument("-r", "--runner", required=True, help="Runner")
    args = parser.parse_args(argv)

    log.setup_logging(args.debug, args.log_file)

    for region in REGIONS:
        LOG.info("Checking for cluster for runner %s in region  %s", args.runner, region)
        cleanup = aws_cleanup.AwsCleanup(region_name=region)
        cleanup.delete_cluster_by_tag("runner", args.runner, args.dry_run)


def delete_placement_groups(argv=None):
    """
    Entry point to delete a DSI cluster based on a task ID.

    :param list argv: Input arguments. Uses sys.argv[1:] if None.

    """
    if argv is None:
        argv = sys.argv[1:]

    parser = base_arg_parsing("Delete Placement groups")
    args = parser.parse_args(argv)

    log.setup_logging(args.debug, args.log_file)

    for region in REGIONS:
        LOG.info("Deleting Placement groups in region  %s", region)
        cleanup = aws_cleanup.AwsCleanup(region_name=region)
        cleanup.delete_placement_groups(dry_run=args.dry_run)
