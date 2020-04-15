#!/usr/bin/env python3.7

"""
Setup an work environment. Copy over the appropriate files.
"""


import os
import os.path
import shutil
import subprocess
import sys
import zipfile

import argparse
import requests
import structlog
import yaml

from dsi import expansions
from dsi.common import utils
from dsi.common import whereami
from dsi.common.config import ConfigDict
from dsi.common.log import setup_logging

LOGGER = structlog.get_logger(__name__)


def parse_command_line(config, args=None):
    """
    Parse the command line options for setting up a working directory

    :param dict config: The bootstrap.py config, populated from cli options. (NOT ConfigDict.)
    :param list args: Command line arguments to pass to argparse.
    """

    parser = argparse.ArgumentParser(
        description="Setup DSI working environment. For instructions \
                    on setting up dsi locally, see \
                    https://drive.google.com/open?id=14QXOmo-ia8w72pW5zqQ2fCWfXEwiVQ8_1EoMCkB4baY"
    )

    parser.add_argument(
        "-b",
        "--bootstrap-file",
        help="Specify the bootstrap file. If not specified, will look for "
        "bootstrap.yml in the current directory. ",
    )
    parser.add_argument("-d", "--debug", action="store_true", help="enable debug output")
    parser.add_argument(
        "-D", "--directory", default=".", help="Directory to setup. Defaults to current directory"
    )
    parser.add_argument("--log-file", help="path to log file")

    # These options are ignored but allowed for backward compatibility
    parser.add_argument("--production", action="store_true", default=False, help="(Ignored)")
    parser.add_argument("-v", "--verbose", action="store_true", help="(Ignored, use -d instead.)")

    parser.add_argument(
        "-l",
        "--symlink",
        action="store_true",
        default=False,
        help="Symlink files instead of copying them.",
    )
    args = parser.parse_args(args)

    setup_logging(args.debug, args.log_file)  # pylint: disable=no-member

    if args.bootstrap_file:
        config["bootstrap_file"] = args.bootstrap_file
    if args.directory:
        config["directory"] = args.directory
    if args.symlink:
        config["symlink"] = args.symlink
    return config


def copy_config_files(dsipath, config, directory):
    """
    Copy all related config files to the target directory

    :param str dsipath: Path to DSI repo.
    :param dict config: The bootstrap.py internal config.
    :param str directory: The work directory.
    """
    # Pairs of ConfigDict module, and bootstrap.yml input.
    # This is all the variable info needed to build the from and to file paths down below.
    configs_to_copy = {
        "infrastructure_provisioning": config.get("infrastructure_provisioning", ""),
        "mongodb_setup": config.get("mongodb_setup", ""),
        "test_control": config.get("test_control", ""),
        "workload_setup": config.get("workload_setup", ""),
        "analysis": config.get("analysis", ""),
    }

    # If this task was generated with genny_auto_tasks, use the dynamic
    # test_control.auto_genny_workload.yml file.
    auto_workload = config.get("auto_genny_workload", "")
    if auto_workload != "" and auto_workload is not None:
        configs_to_copy["test_control"] = "auto_genny_workload"

    for config_module, bootstrap_variable in configs_to_copy.items():
        # Example: ./mongodb_setup.yml
        target_file = os.path.join(directory, config_module + ".yml")
        # Example: ../dsi/configurations/mongodb_setup/mongodb_setup.standalone.wiredTiger.yml
        source_file = os.path.join(
            dsipath,
            "configurations",
            config_module,
            config_module + "." + bootstrap_variable + ".yml",
        )

        _warn_if_overwriting(target_file)
        # pylint: disable=broad-except
        try:
            copy_method = (
                os.symlink if "symlink" in config and config["symlink"] else shutil.copyfile
            )
            copy_method(source_file, target_file)
            LOGGER.debug(
                "Copied file to work directory", source_file=source_file, target_file=target_file
            )
        except Exception as error:
            # If a source file doesn't exist, it's probably because a wrong or no option was
            # provided in bootstrap.yml. When running manually, this is not fatal. For example,
            # user may want to manually copy some files from somewhere else
            error_str = "Failed to copy {} from {}.\nError: {}".format(
                target_file, source_file, str(error)
            )
            if config["production"]:
                LOGGER.critical(error_str)
                raise
            LOGGER.warn(error_str)


def setup_overrides(config_dict, directory):
    """
    Generate the overrides.yml file

    :param ConfigDict config_dict: The ConfigDict object. Note, must be a real ConfigDict instance,
                                   passing a dict will fail.
    :param str directory: The work directory.
    """
    # Use the raw dict to prevent ${variable.references} from being prematurely evaluated.
    overrides = config_dict.raw["bootstrap"].get("overrides", {})
    override_path = os.path.join(directory, "overrides.yml")

    # A bit odd place, but this used to be here when code was different, so leaving here for now
    try:
        if overrides["infrastructure_provisioning"]["tfvars"]["tags"]["owner"] == "your.username":
            message = (
                "owner is set to your.username. Please update this setting in your "
                "bootstrap.yml file, and review the other settings in that file."
            )
            LOGGER.critical(message)
            assert False, message
    except KeyError:
        pass
    except TypeError:
        pass

    if overrides:
        _warn_if_overwriting(override_path)
        with open(override_path, "w", encoding="utf-8") as override_file:
            override_file.write(yaml.dump(overrides, default_flow_style=False))


def _extract_zip(zip_bytes, directory):
    """
    Separate open() calls so they can be mocked in tests.
    """
    zip_file_path = os.path.join(directory, "terraform.zip")
    with open(zip_file_path, "wb") as zip_file_handle:
        zip_file_handle.write(zip_bytes)
    with zipfile.ZipFile(zip_file_path, "r") as zip_file_handle:
        zip_file_handle.extractall(directory)
    os.chmod(os.path.join(directory, "terraform"), 0o0555)


def download_terraform(directory, config):
    """
    Download terraform to directory (if it wasn't found in PATH).
    """
    if "terraform_url" not in config:
        LOGGER.critical(
            "No Terraform download url found for your operating system. "
            "Automatic terraform download is not supported.",
            platform=sys.platform,
        )
        assert False
    url = config["terraform_url"]
    LOGGER.info("Downloading terraform for you.", url=url)

    response = requests.get(url)
    if not response.ok:
        response.raise_for_status()
    _extract_zip(response.content, directory)


def find_terraform(directory, config):
    """
    Returns the location of the terraform binary to use.

    :param str directory: The work directory.
    """
    terraform = None
    try:
        terraform = utils.find_terraform(directory)
    except utils.TerraformNotFound:
        LOGGER.info("Terraform not found in PATH.")
        download_terraform(directory, config)
        terraform = os.path.join(directory, "terraform")
    return terraform


def validate_terraform(directory, config):
    """
    Asserts that terraform is the correct version.

    :param dict config: The bootstrap.py internal config.
    """
    if not config["production"]:
        try:
            version = subprocess.check_output(
                [config["terraform"], "-version"], encoding="utf-8"
            ).split("\n")[0]
        except subprocess.CalledProcessError as error:
            if error.returncode == 1:
                LOGGER.critical("Call to terraform failed.")
            if error.returncode == 126:
                LOGGER.critical("Cannot execute terraform binary file.")
            if error.returncode == 127:
                LOGGER.critical("No terraform binary file found.")
            LOGGER.critical("See documentation for installing terraform: http://bit.ly/2ufjQ0R")
            assert False
        if not version == config["terraform_version_check"]:
            LOGGER.info(
                "Wrong terraform version found in PATH.",
                installed_version=version,
                required_version=config["terraform_version_check"],
            )
            download_terraform(directory, config)
            config["terraform"] = os.path.join(directory, "terraform")


def symlink_bindir(directory):
    """
    Create symlink to dsi_repo/dsi.

    :param str directory: The work directory.
    """
    src = whereami.dsi_repo_path("dsi")
    dest = os.path.join(directory, ".bin")
    if os.path.exists(dest):
        LOGGER.warning("Removing old symlink to binaries.", dest=dest)
        os.remove(dest)
    LOGGER.info("Creating symlink to binaries.", src=src, dest=dest)
    os.symlink(src, dest)


def write_dsienv(directory, terraform):
    """
    Writes out the dsienv.sh file.

    :param str directory: The work directory.
    :param str terraform: Path to terraform.

    """
    with open(os.path.join(directory, "dsienv.sh"), "w") as dsienv:
        dsienv.write("export PATH={0}:$PATH\n".format(whereami.dsi_repo_path("dsi")))
        dsienv.write("export TERRAFORM={0}\n".format(terraform))
        dsienv.write('echo "Tip: Sourcing dsienv.sh is now optional. You can also just execute:"\n')
        dsienv.write('echo "    ./.bin/infrastructure_provisioning.py     # etc..."\n')


def load_bootstrap(config, directory):
    """
    Move specified bootstrap.yml file to correct location for read_runtime_values
    """
    # Create directory if it doesn't exist
    if not os.path.exists(directory):
        os.makedirs(directory)

    if "bootstrap_file" in config:
        bootstrap_path = os.path.abspath(os.path.expanduser(config["bootstrap_file"]))
        if os.path.isfile(bootstrap_path):
            if not bootstrap_path == os.path.abspath(os.path.join(directory, "bootstrap.yml")):
                if os.path.isfile(os.path.abspath(os.path.join(directory, "bootstrap.yml"))):
                    LOGGER.critical(
                        "Attempting to overwrite existing bootstrap.yml file. Aborting.",
                        directory=directory,
                    )
                    assert False
                shutil.copyfile(bootstrap_path, os.path.join(directory, "bootstrap.yml"))
        else:
            LOGGER.critical("Location specified for bootstrap.yml is invalid.")
            assert False
    else:
        bootstrap_path = os.path.abspath(
            os.path.expanduser(os.path.join(os.getcwd(), "bootstrap.yml"))
        )
        if os.path.isfile(bootstrap_path):
            if not bootstrap_path == os.path.abspath(os.path.join(directory, "bootstrap.yml")):
                if os.path.isfile(os.path.abspath(os.path.join(directory, "bootstrap.yml"))):
                    LOGGER.critical(
                        "Attempting to overwrite existing bootstrap.yml file in %s. " "Aborting.",
                        directory,
                    )
                    assert False
                shutil.copyfile(bootstrap_path, os.path.join(directory, "bootstrap.yml"))

    expansions.write_if_necessary(directory)

    current_path = os.getcwd()
    os.chdir(directory)
    config_dict = ConfigDict("bootstrap")
    config_dict.load()
    for key in config_dict["bootstrap"].keys():
        config[key] = config_dict["bootstrap"][key]

    # terraform required_version must be specified, we fail hard if user has tried to unset
    config["terraform_version_check"] = config_dict["infrastructure_provisioning"]["terraform"][
        "required_version"
    ]
    config["terraform_linux_download"] = config_dict["infrastructure_provisioning"]["terraform"][
        "linux_download"
    ]
    config["terraform_mac_download"] = config_dict["infrastructure_provisioning"]["terraform"][
        "mac_download"
    ]

    os.chdir(current_path)

    return config_dict


def _warn_if_overwriting(destination):
    """
    Warn if destination exists.

    :param str destination: A path to a config file.
    """
    if os.path.exists(destination):
        LOGGER.warn("Overwriting existing file.", destination=destination)


def run_bootstrap(config):
    """
    Main logic.
    :param config: parsed command-line args
    """
    directory = os.path.abspath(os.path.expanduser(config["directory"]))
    LOGGER.info("Creating work directory", directory=directory)

    if os.path.exists(os.path.join(directory, "dsienv.sh")):
        print(
            "It looks like you have already setup "
            "{0} for dsi. dsienv.sh exists. Stopping".format(directory)
        )
        sys.exit(1)

    # Copies bootstrap.yml if necessary and then reads values into config
    config_dict = load_bootstrap(config, directory)

    # Checks for aws credentials, fails if cannot find them
    utils.read_aws_credentials(config_dict)

    url = None
    if sys.platform.startswith("linux"):
        url = config_dict["infrastructure_provisioning"]["terraform"]["linux_download"]
    elif sys.platform.startswith("darwin"):
        url = config_dict["infrastructure_provisioning"]["terraform"]["mac_download"]
    config["terraform_url"] = url
    config["terraform"] = find_terraform(directory, config)
    validate_terraform(directory, config)
    LOGGER.info("Path to terraform binary", terraform=config["terraform"])

    symlink_bindir(directory)
    write_dsienv(directory, config["terraform"])

    # copy necessary config files to the current directory
    copy_config_files(whereami.dsi_repo_path(), config, directory)

    # This writes an overrides.yml with the ssh_key_file, ssh_key_name and owner, if given in
    # bootstrap.yml, and with expire-on-delta if running DSI locally.
    setup_overrides(config_dict, directory)

    LOGGER.info("Local environment setup", directory=directory)


def main(args=None):
    """
    Run main logic.

    :param args: argv (uses sys.argv if None)
    :return: nothing
    """
    config = parse_command_line({}, args)
    run_bootstrap(config)


if __name__ == "__main__":
    main()
