#!/usr/bin/env python3.7

"""
Teardown AWS resources using terraform.
It is important this python file can be used without any dependencies on our own other python files
since in one of the cases the script is used, it is isolated from the other python files. This
occurs when it is used from within the Evergreen data directory which stores terraform state.
Furthermore, this file does not have any pip package dependencies.

"""

import glob
import logging
import os
import subprocess
import sys
from subprocess import CalledProcessError

import argparse

from dsi.common.utils import find_terraform
import dsi.common.whereami as whereami

LOG = logging.getLogger(__name__)


def destroy_resources():
    """
    Destroys AWS resources using terraform.
    """
    teardown_script_path = whereami.dsi_repo_path("dsi")
    previous_directory = None
    if glob.glob(teardown_script_path + "/provisioned.*"):
        previous_directory = os.getcwd()
        os.chdir(teardown_script_path)

    terraform = find_terraform()
    LOG.info("Using terraform binary: %s", terraform)

    if os.path.isfile("cluster.json"):
        var_file = "-var-file=cluster.json"
    else:
        LOG.critical("In infrastructure_teardown.py and cluster.json does not exist. Giving up.")
        if previous_directory is not None:
            os.chdir(previous_directory)
        raise UserWarning

    LOG.info("Destroy starting")
    try:
        # Destroy instances first.
        subprocess.check_call([terraform, "destroy", var_file, "-force", "-target=module.cluster"])
    except CalledProcessError as e:
        LOG.warning("Failed destroying resources: %s", e)
    finally:
        # Then destroy the rest, which is the placement group.
        # This is a workaround for the fact that depends_on doesn't work with modules.
        LOG.info("Attempting to destroy remaining resources")
        subprocess.check_call([terraform, "destroy", var_file, "-force"])

    if previous_directory is not None:
        os.chdir(previous_directory)


def destroy_atlas_resources():
    """
    Destroys Atlas resources using atlas_client REST call.
    """
    # The following will work if run from a work directory, such as during an Evergreen task.
    # It will cause ImportError when run from an Evergreen teardown hook.
    # This means Atlas clusters must be shut down at the end of the task, they are not reused.
    try:
        # pylint: disable=import-outside-toplevel
        from dsi.common import config
        from dsi.common import atlas_setup
    except ImportError as error:
        LOG.info(error)
        LOG.info("Cannot import ConfigDict or AtlasSetup. Skipping Atlas teardown.")
        LOG.info("(This is benign inside evergreen teardown hook.)")
        return True

    # AtlasSetup.destroy() will write to mongodb_setup.out.yml
    configdict = config.ConfigDict("mongodb_setup")
    configdict.load()

    # start a mongodb configuration using config
    atlas = atlas_setup.AtlasSetup(configdict)
    atlas.destroy()

    return True


def parse_command_line():
    """
    Parse command line arguments.
    """
    parser = argparse.ArgumentParser(description="Destroy EC2 & Atlas resources.")
    parser.add_argument("--log-file", help="path to log file")
    parser.add_argument("-d", "--debug", action="store_true", help="enable debug output")
    args = parser.parse_args()
    return args


def setup_logging(verbose, filename=None):
    """
    Copied over from common.log due to isolation of this script.
    Configure logging verbosity and destination.
    """
    loglevel = logging.DEBUG if verbose else logging.INFO
    handler = logging.FileHandler(filename) if filename else logging.StreamHandler()
    handler.setLevel(loglevel)
    handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    root_logger = logging.getLogger()
    root_logger.setLevel(loglevel)
    root_logger.addHandler(handler)


def main():
    """
    Main function.
    """
    return_value = 0
    args = parse_command_line()
    setup_logging(args.debug, args.log_file)
    try:
        destroy_resources()
    except:  # pylint: disable=broad-except, bare-except
        LOG.error("Teardown of EC2 resources failed.")
        LOG.error("Check EC2 console to see if something still needs to be terminated.")
        LOG.error("Stack trace:", exc_info=1)
        return_value += 1

    try:
        destroy_atlas_resources()
    except:  # pylint: disable=broad-except, bare-except
        LOG.error("Teardown of Atlas resources failed.")
        LOG.error("Check Atlas console to see if something still needs to be terminated.")
        LOG.error("Stack trace:", exc_info=1)
        return_value += 2  # Using powers of two to distinguish failures in return_value

    return return_value


if __name__ == "__main__":
    sys.exit(main())
