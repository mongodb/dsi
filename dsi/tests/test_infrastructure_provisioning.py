"""
Unit test for infrastructure_provisioning.py
"""

import glob
import logging
import os
import shutil
import unittest
from subprocess import CalledProcessError

from mock import patch, call, mock_open, MagicMock
from testfixtures import LogCapture

import test_lib.structlog_for_test as structlog_for_test
from dsi import infrastructure_provisioning as ip
from dsi.common import utils
from dsi.common import whereami
from dsi.common.config import ConfigDict
from test_lib.fixture_files import FixtureFiles

# pylint: disable=too-many-locals

FIXTURE_FILES = FixtureFiles()


class TestInfrastructureProvisioning(unittest.TestCase):
    """
    Test suite for infrastructure_provisioning.py
    """

    def setUp(self):
        self.os_environ_patcher = patch("dsi.infrastructure_provisioning.os.environ")
        self.mock_environ = self.os_environ_patcher.start()
        self.dsi_path = whereami.dsi_repo_path()
        self.reset_mock_objects()
        # pylint: disable=line-too-long
        self.config = {
            "bootstrap": {"infrastructure_provisioning": "single"},
            "infrastructure_provisioning": {
                "hostnames": {"method": "/etc/hosts"},
                "terraform": {"aws_required_version": "test_aws_version"},
                "tfvars": {
                    "cluster_name": "single",
                    "ssh_key_file": "aws_ssh_key.pem",
                    "ssh_key_name": "serverteam-perf-ssh-key",
                },
                "post_provisioning": [
                    {
                        "on_all_hosts": {
                            "exec": """
                     # set ulimit nofile for user
                     echo "${infrastructure_provisioning.tfvars.ssh_user}           soft    nofile          65535" | sudo tee -a /etc/security/limits.conf
                     echo "${infrastructure_provisioning.tfvars.ssh_user}           hard    nofile          65535" | sudo tee -a /etc/security/limits.conf
                     echo "${infrastructure_provisioning.tfvars.ssh_user}   soft   core   unlimited" | sudo tee -a /etc/security/limits.conf
                     echo "${infrastructure_provisioning.tfvars.ssh_user}   hard   core   unlimited" | sudo tee -a /etc/security/limits.conf
                     """
                        }
                    }
                ],
            },
            "runtime_secret": {
                "aws_access_key": "test_access_key",
                "aws_secret_key": "test_secret_key",
            },
        }
        # pylint: enable=line-too-long
        # create a provision log path that can be safely deleted post test
        self.provision_log_path = os.path.join(
            FIXTURE_FILES.fixture_file_path(), ip.PROVISION_LOG_PATH
        )

        # Setup logging so that structlog uses stdlib, and LogCapture works
        structlog_for_test.setup_logging()

    def tearDown(self):
        self.os_environ_patcher.stop()
        if os.path.exists(self.provision_log_path):
            os.remove(self.provision_log_path)

    def reset_mock_objects(self):
        """
        Used to reset environment variables and mock objects
        """
        self.os_environ = {"TERRAFORM": "test/path/terraform", "DSI_PATH": self.dsi_path}
        self.mock_environ.__getitem__.side_effect = self.os_environ.__getitem__
        self.mock_environ.__contains__.side_effect = self.os_environ.__contains__
        self.mock_environ.__delitem__.side_effect = self.os_environ.__delitem__

    def check_subprocess_call(self, command_to_check, command, env=None):
        """
        Needed to properly check subprocess.check_call since whereami is used
        to find the path to the file being executed.
        :param command_to_check list that represents the expected command
        :param command is the command subprocess.check_call tries to run. This command is checked
        against command_to_check based on the file in the commands.
        :param env dict that represents the environment variables passed into subprocess.check_call
        """
        if len(command_to_check) > 1:
            if command_to_check[1].endswith("infrastructure_teardown.py"):
                self.assertTrue("TERRAFORM" not in env)
        else:
            if command_to_check[0].endswith("infrastructure_teardown.sh"):
                self.assertTrue("TERRAFORM" not in env)
        self.assertEqual(command_to_check, command)

    def test_provisioner_init(self):
        """
        Test Provisioner.__init__
        """
        # Check that the correct default provisioning log is created
        mock_open_file = mock_open()
        with patch("dsi.infrastructure_provisioning.open", mock_open_file, create=True):
            ip.Provisioner(self.config)
            mock_open_file.assert_called_with(ip.PROVISION_LOG_PATH, "w")

        # Check when TERRAFORM is an environment variable
        provisioner = ip.Provisioner(self.config, provisioning_file=self.provision_log_path)
        self.assertEqual(provisioner.cluster, "single")
        self.assertEqual(provisioner.dsi_dir, self.dsi_path)
        self.assertEqual(provisioner.parallelism, "-parallelism=20")
        self.assertEqual(provisioner.terraform, "test/path/terraform")

        # Check when TERRAFORM is not environment variable
        os_environ_missing_terraform = self.os_environ.copy()
        del os_environ_missing_terraform["TERRAFORM"]
        os_environ_missing_terraform["PATH"] = "/foo:/bar"
        self.mock_environ.__getitem__.side_effect = os_environ_missing_terraform.__getitem__
        self.mock_environ.__contains__.side_effect = os_environ_missing_terraform.__contains__
        with self.assertRaises(utils.TerraformNotFound):
            provisioner_missing_terraform = ip.Provisioner(
                self.config, provisioning_file=self.provision_log_path
            )
            self.assertEqual(provisioner_missing_terraform.cluster, "single")
            self.assertEqual(provisioner_missing_terraform.dsi_dir, self.dsi_path)
            self.assertEqual(provisioner_missing_terraform.parallelism, "-parallelism=20")
            self.assertEqual(provisioner_missing_terraform.terraform, "./terraform")
        self.reset_mock_objects()

    def test_setup_security_tf(self):
        """
        Testing setup_security_tf creates security.tf file
        """
        key_name = self.config["infrastructure_provisioning"]["tfvars"]["ssh_key_name"]
        key_file = self.config["infrastructure_provisioning"]["tfvars"]["ssh_key_file"]
        master_tf_str = (
            'provider "aws" {{    '
            'access_key = "test_aws_access_key"    '
            'secret_key = "test_aws_secret_key"    '
            "region = var.region"
            'version = "test_aws_version" }}'
            'variable "key_name" {{    '
            'default = "{}"}}'
            'variable "key_file" {{    '
            'default = "{}"}}'
        ).format(key_name, key_file)
        master_tf_str = master_tf_str.replace("\n", "").replace(" ", "")
        provisioner = ip.Provisioner(self.config, provisioning_file=self.provision_log_path)
        provisioner.aws_access_key = "test_aws_access_key"
        provisioner.aws_secret_key = "test_aws_secret_key"

        # Creating 'security.tf' file in current dir to test, reading to string
        provisioner.setup_security_tf()
        test_tf_str = ""
        with open("security.tf", "r") as test_tf_file:
            test_tf_str = test_tf_file.read().replace("\n", "").replace(" ", "")
        self.assertEqual(test_tf_str, master_tf_str)

        # Removing created file
        os.remove("security.tf")

    def test_setup_terraform_tf(self):
        """
        Test setup_terraform_tf creates the correct directories and files
        """
        # Create temporary directory and get correct paths
        directory = "temp_test"
        if os.path.exists(directory):
            shutil.rmtree(directory)
        os.mkdir(directory)
        cluster_path = os.path.join(self.dsi_path, "clusters", "default")
        remote_scripts_path = os.path.join(self.dsi_path, "clusters", "remote-scripts")
        remote_scripts_target = os.path.join(directory, "remote-scripts")
        modules_path = os.path.join(self.dsi_path, "clusters", "modules")
        modules_target = os.path.join(directory, "modules")

        # Check files copied correctly
        with patch("dsi.infrastructure_provisioning.os.getcwd", return_value="temp_test"):
            provisioner = ip.Provisioner(self.config, provisioning_file=self.provision_log_path)
            provisioner.setup_terraform_tf()
        for filename in glob.glob(os.path.join(cluster_path, "*")):
            self.assertTrue(os.path.exists(os.path.join(directory, filename.split("/")[-1])))
        for filename in glob.glob(os.path.join(remote_scripts_path, "*")):
            self.assertTrue(
                os.path.exists(os.path.join(remote_scripts_target, filename.split("/")[-1]))
            )
        for filename in glob.glob(os.path.join(modules_path, "*")):
            self.assertTrue(os.path.exists(os.path.join(modules_target, filename.split("/")[-1])))

        # Remove temporary directory
        shutil.rmtree(directory)

    @patch("dsi.infrastructure_provisioning.run_pre_post_commands")
    @patch("dsi.infrastructure_provisioning.Provisioner.setup_terraform_tf")
    @patch("dsi.infrastructure_provisioning.Provisioner.setup_security_tf")
    @patch("dsi.infrastructure_provisioning.TerraformOutputParser")
    @patch("dsi.infrastructure_provisioning.TerraformConfiguration")
    @patch("dsi.infrastructure_provisioning.run_and_save_output")
    @patch("dsi.infrastructure_provisioning.subprocess")
    def test_setup_cluster(
        self,
        mock_subprocess,
        mock_save_output,
        mock_terraform_configuration,
        mock_terraform_output_parser,
        mock_setup_security_tf,
        mock_setup_terraform_tf,
        mock_pre_post_commands,
    ):
        """
        Test Provisioner.setup_cluster
        """
        # NOTE: This tests the majority of the functionality of the infrastructure_provisioning.py
        # mock.mock_open is needed to effectively mock out the open() function in python
        mock_open_file = mock_open()
        with patch("dsi.infrastructure_provisioning.open", mock_open_file, create=True):
            provisioner = ip.Provisioner(self.config, provisioning_file=self.provision_log_path)
            provisioner.cluster = "initialsync-logkeeper"
            provisioner.hostnames_method = None
            provisioner.setup_cluster()
            mock_setup_security_tf.assert_called()
            mock_setup_terraform_tf.assert_called()
            mock_terraform_configuration.return_value.to_json.assert_called_with(
                file_name="cluster.json"
            )
            # __enter__ and __exit__ are checked to see if the files were opened
            # as context managers.
            open_file_calls = [call("infrastructure_provisioning.out.yml", "r"), call().read()]
            mock_open_file.assert_has_calls(open_file_calls, any_order=True)
            # If the cluster is initialsync-logkeeper, then terraform should be run twice
            terraform = self.os_environ["TERRAFORM"]
            check_call_calls = [
                call(
                    [terraform, "init", "-upgrade"],
                    stdout=provisioner.stdout,
                    stderr=provisioner.stderr,
                ),
                call(
                    [
                        terraform,
                        "apply",
                        "-var-file=cluster.json",
                        provisioner.parallelism,
                        "-auto-approve",
                        "-var=mongod_ebs_instance_count=0",
                        "-var=workload_instance_count=0",
                    ],
                    stdout=provisioner.stdout,
                    stderr=provisioner.stderr,
                ),
                call(
                    [
                        terraform,
                        "apply",
                        "-var-file=cluster.json",
                        provisioner.parallelism,
                        "-auto-approve",
                    ],
                    stdout=provisioner.stdout,
                    stderr=provisioner.stderr,
                ),
                call(
                    [terraform, "refresh", "-var-file=cluster.json"],
                    stdout=provisioner.stdout,
                    stderr=provisioner.stderr,
                ),
                call(
                    [terraform, "plan", "-detailed-exitcode", "-var-file=cluster.json"],
                    stdout=provisioner.stdout,
                    stderr=provisioner.stderr,
                ),
            ]
            mock_subprocess.check_call.assert_has_calls(check_call_calls)
            mock_save_output.assert_called_with([terraform, "output"])
            self.assertTrue(mock_terraform_output_parser.return_value.write_output_files.called)
            mock_pre_post_commands.assert_called()
        self.reset_mock_objects()

    @patch("dsi.infrastructure_provisioning.Provisioner.setup_terraform_tf")
    @patch("dsi.infrastructure_provisioning.TerraformOutputParser")
    @patch("dsi.infrastructure_provisioning.TerraformConfiguration")
    @patch("dsi.infrastructure_provisioning.subprocess")
    def test_setup_cluster_failure(
        self,
        mock_subprocess,
        mock_terraform_configuration,
        mock_terraform_output_parser,
        mock_setup_terraform_tf,
    ):
        """
        Test Provisioner.setup_cluster when an error happens. Ensure that the cluster is torn
        down.
        """
        # NOTE: This tests the majority of the functionality of the infrastructure_provisioning.py
        mock_open_file = mock_open()
        with patch("dsi.infrastructure_provisioning.open", mock_open_file, create=True):
            with patch("dsi.infrastructure_provisioning.destroy_resources") as mock_destroy:
                provisioner = ip.Provisioner(self.config, provisioning_file=self.provision_log_path)
                mock_subprocess.check_call.side_effect = [1, CalledProcessError(1, ["cmd"]), 1]
                with self.assertRaises(CalledProcessError):
                    provisioner.setup_cluster()
            mock_setup_terraform_tf.assert_called()
            mock_destroy.assert_called()
            self.assertFalse(mock_terraform_output_parser.return_value.write_output_files.called)
            mock_terraform_configuration.return_value.to_json.assert_called_with(
                file_name="cluster.json"
            )
        self.reset_mock_objects()

    @patch("dsi.infrastructure_provisioning.os.path.exists", return_value=False)
    @patch("dsi.infrastructure_provisioning.shutil.rmtree")
    def test_rmtree_when_not_present(self, mock_rmtree, mock_exists):
        """
        Test infrastructure_provisioning.rmtree_when_present fail path
        """
        # pylint: disable=no-self-use
        # self.assertLogs(logger='infrastructure_provisioning')

        with LogCapture(level=logging.INFO) as capture:
            ip.rmtree_when_present("")
            capture.check(
                (
                    "dsi.infrastructure_provisioning",
                    "INFO",
                    "[info     ] rmtree_when_present: No such path "
                    "[dsi.infrastructure_provisioning] arg=",
                ),
            )

    @patch("dsi.infrastructure_provisioning.os.path.exists", return_value=True)
    @patch("dsi.infrastructure_provisioning.shutil.rmtree", side_effect=OSError)
    def test_rmtree_when_present_error(self, mock_rmtree, mock_exists):
        """
        Test infrastructure_provisioning.rmtree_when_present unexpected error
        """
        with LogCapture(level=logging.INFO) as capture:
            with self.assertRaises(OSError):
                ip.rmtree_when_present("")
            capture.check()

    @patch("dsi.infrastructure_provisioning.os.path.exists", return_value=True)
    @patch("dsi.infrastructure_provisioning.shutil.rmtree")
    def test_rmtree_when_present(self, mock_rmtree, mock_exists):
        """
        Test infrastructure_provisioning.rmtree_when_present success path
        """
        with LogCapture(level=logging.INFO) as capture:
            ip.rmtree_when_present("")
            capture.check()

    @patch("dsi.infrastructure_provisioning.os.path.exists", return_value=False)
    def test_rmtree_when_present_nopath(self, mock_exists):
        """
        Test infrastructure_provisioning.rmtree_when_present path not found
        """
        with LogCapture() as capture:
            ip.rmtree_when_present("")
            capture.check(
                (
                    "dsi.infrastructure_provisioning",
                    "DEBUG",
                    "[debug    ] rmtree_when_present start      "
                    "[dsi.infrastructure_provisioning] arg=",
                ),
                (
                    "dsi.infrastructure_provisioning",
                    "INFO",
                    "[info     ] rmtree_when_present: No such path "
                    "[dsi.infrastructure_provisioning] arg=",
                ),
            )

    def test_print_terraform_errors(self):
        """
        Test infrastructure_provisioning.print_terraform_errors()
        """
        provisioner = ip.Provisioner(self.config, provisioning_file=self.provision_log_path)
        provisioner.tf_log_path = FIXTURE_FILES.fixture_file_path("terraform.log.short")
        logger = MagicMock(name="logger")
        tailer = MagicMock(name="tailer")
        provisioner.print_terraform_errors(logger, tailer)

        logger_calls = [
            call(
                "2018-03-05T15:45:36.018+0200 [DEBUG] plugin.terraform-provider-aws_v1.6.0_x4: "
                "<Response><Errors><Error><Code>InsufficientInstanceCapacity</Code><Message>"
                "Insufficient capacity.</Message></Error></Errors>"
                "<RequestID>bd5b4071-755d-440e-8381-aa09bad52d69</RequestID></Response>"
            ),
            call(
                "2018-03-05T15:45:36.914+0200 [DEBUG] plugin.terraform-provider-aws_v1.6.0_x4: "
                "<Response><Errors><Error><Code>RequestLimitExceeded</Code><Message>"
                "Request limit exceeded.</Message></Error></Errors>"
                "<RequestID>6280e71d-9be4-442c-8ddf-00265efeafe6</RequestID></Response>"
            ),
            call(
                "2018-03-05T15:48:36.336+0200 [DEBUG] plugin.terraform-provider-aws_v1.6.0_x4: "
                "<Response><Errors><Error><Code>InvalidRouteTableID.NotFound</Code><Message>"
                "The routeTable ID 'rtb-509f1528' does not exist</Message></Error></Errors>"
                "<RequestID>54256eb4-d706-4084-86dc-b7f581006f9f</RequestID></Response>"
            ),
            call(
                "2018-03-05T15:48:47.258+0200 [DEBUG] plugin.terraform-provider-aws_v1.6.0_x4: "
                "<Response><Errors><Error><Code>DependencyViolation</Code><Message>"
                "Network vpc-a9ed8bd0 has some mapped public address(es). Please unmap those public address(es) "
                "before detaching the gateway.</Message></Error></Errors>"
                "<RequestID>cd102bc6-d598-4bae-80f5-25e62103f9a4</RequestID></Response>"
            ),
            call(
                "2018-03-05T15:49:29.084+0200 [DEBUG] plugin.terraform-provider-aws_v1.6.0_x4: "
                "<Response><Errors><Error><Code>InvalidPlacementGroup.Unknown</Code><Message>"
                "The Placement Group 'shard-8665ea69-9e76-483a-937b-af68d41d54dd' is unknown."
                "</Message></Error></Errors><RequestID>4264aef8-ae91-40f0-bc16-d914a8dc2cf8</RequestID></Response>"
            ),
            call(
                "For more info, see:", path=FIXTURE_FILES.fixture_file_path("terraform.log.short")
            ),
        ]

        logger.error.assert_has_calls(logger_calls)

    @patch("paramiko.SSHClient")
    @patch("dsi.common.remote_ssh_host.RemoteSSHHost.create_file")
    @patch("dsi.common.remote_ssh_host.RemoteSSHHost.exec_command")
    def test_setup_hostnames(self, mock_exec_command, mock_create_file, mock_ssh):
        _ = mock_ssh
        real_config_dict = ConfigDict(
            "infrastructure_provisioning", whereami.dsi_repo_path("docs", "config-specs")
        )
        real_config_dict.load()
        real_config_dict.save = MagicMock(name="save")

        provisioner = ip.Provisioner(real_config_dict, provisioning_file=self.provision_log_path)
        provisioner.setup_hostnames()
        out = provisioner.config["infrastructure_provisioning"]["out"]
        self.assertEqual(out["mongod"][0]["private_hostname"], "mongod0.dsitest.dev")
        self.assertEqual(out["configsvr"][2]["private_hostname"], "configsvr2.dsitest.dev")
        self.assertEqual(mock_create_file.call_count, 16)
        self.assertEqual(mock_exec_command.call_count, 16)

    def test_build_hosts_file(self):
        expected = [
            "10.2.1.1\tmd md0 mongod0 mongod0.dsitest.dev",
            "10.2.1.2\tmd1 mongod1 mongod1.dsitest.dev",
            "10.2.1.3\tmd2 mongod2 mongod2.dsitest.dev",
            "10.2.1.4\tmd3 mongod3 mongod3.dsitest.dev",
            "10.2.1.5\tmd4 mongod4 mongod4.dsitest.dev",
            "10.2.1.6\tmd5 mongod5 mongod5.dsitest.dev",
            "10.2.1.7\tmd6 mongod6 mongod6.dsitest.dev",
            "10.2.1.8\tmd7 mongod7 mongod7.dsitest.dev",
            "10.2.1.9\tmd8 mongod8 mongod8.dsitest.dev",
            "10.2.1.100\tms ms0 mongos0 mongos0.dsitest.dev",
            "10.2.1.101\tms1 mongos1 mongos1.dsitest.dev",
            "10.2.1.102\tms2 mongos2 mongos2.dsitest.dev",
            "10.2.1.51\tcs cs0 configsvr0 configsvr0.dsitest.dev",
            "10.2.1.52\tcs1 configsvr1 configsvr1.dsitest.dev",
            "10.2.1.53\tcs2 configsvr2 configsvr2.dsitest.dev",
            "10.2.1.10\twc wc0 workload_client0 workload_client0.dsitest.dev",
        ]

        real_config_dict = ConfigDict(
            "infrastructure_provisioning", whereami.dsi_repo_path("docs", "config-specs")
        )
        real_config_dict.load()
        real_config_dict.save = MagicMock(name="save")

        provisioner = ip.Provisioner(real_config_dict, provisioning_file=self.provision_log_path)
        hosts_contents = provisioner._build_hosts_file()
        self.assertEqual(expected, hosts_contents)


if __name__ == "__main__":
    unittest.main()
