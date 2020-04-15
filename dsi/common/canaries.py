"""
Utility functions for canary tests
"""

CANARY_TYPES = ["cpu_noise", "fio", "iperf"]


def should_run(config):
    """
    Checks if canary tests should run.
    """
    if "canaries" in config["bootstrap"] and config["bootstrap"]["canaries"] == "none":
        return False
    if "canaries" in config["test_control"] and config["test_control"]["canaries"] == "none":
        return False
    return True


class _BaseCanary:
    """
    Base class for a canary test.
    """

    def __init__(self, test_id, test_type, output_files, cmd):
        self.test_id = test_id
        self.test_type = test_type
        self.output_files = output_files
        self.cmd = cmd

    def as_dict(self):
        """
        Generate the static YAML representation of the config for the canary.
        Ideally all Python code would use this class directly, but test_control.py currently
        does not, so we need to generate the dict format for backwards compatibility.
        """
        raise ValueError(
            "to_json method must be implemented by the subclass: ", self.__class__.__name__
        )


class CpuNoise(_BaseCanary):
    """
    Class for cpu_noise canary test.
    """

    def __init__(self, config):
        numactl_prefix = config["test_control"]["numactl_prefix_for_workload_client"]
        mongodb_hostname = config["mongodb_setup"]["meta"]["hostname"]
        mongodb_port = config["mongodb_setup"]["meta"]["port"]
        mongodb_sharded = config["mongodb_setup"]["meta"]["is_sharded"]
        mongodb_replica = config["mongodb_setup"]["meta"]["is_replset"]
        mongodb_shell_ssl_options = config["mongodb_setup"]["meta"]["shell_ssl_options"]

        self.config_filename = "workloads.yml"

        base_canary_config = {
            "test_id": "cpu_noise",
            "test_type": "cpu_noise",
            "output_files": ["workloads/workload_timestamps.csv"],
            "cmd": "cd workloads && "
            + numactl_prefix
            + " ./run_workloads.py -c ../"
            + self.config_filename,
        }
        super().__init__(**base_canary_config)

        self.workload_config = {
            "tests": {"default": ["cpu_noise"]},
            "target": mongodb_hostname,
            "port": mongodb_port,
            "sharded": mongodb_sharded,
            "replica": mongodb_replica,
            "shell_ssl_options": mongodb_shell_ssl_options,
        }
        self.skip_validate = True

    def as_dict(self):
        return {
            "id": self.test_id,
            "type": self.test_type,
            "output_files": self.output_files,
            "cmd": self.cmd,
            "config_filename": self.config_filename,
            "workload_config": self.workload_config,
            "skip_validate": self.skip_validate,
        }


class Fio(_BaseCanary):
    """
    Class for fio canary test.
    """

    def __init__(self, config):
        numactl_prefix = config["test_control"]["numactl_prefix_for_workload_client"]
        mongodb_hostname = config["mongodb_setup"]["meta"]["hostname"]

        base_canary_config = {
            "test_id": "fio",
            "test_type": "fio",
            "output_files": ["fio.json", "fio_results.tgz"],
            "cmd": numactl_prefix + " ./fio-test.sh " + mongodb_hostname,
        }
        super().__init__(**base_canary_config)

        self.config_filename = "fio.ini"
        self.skip_validate = True
        self.workload_config = config["test_control"]["common_fio_config"]

    def as_dict(self):
        return {
            "id": self.test_id,
            "type": self.test_type,
            "output_files": self.output_files,
            "cmd": self.cmd,
            "config_filename": self.config_filename,
            "skip_validate": self.skip_validate,
            "workload_config": self.workload_config,
        }


class IPerf(_BaseCanary):
    """
    Class for iperf canary test.
    """

    def __init__(self, config):
        numactl_prefix = config["test_control"]["numactl_prefix_for_workload_client"]
        mongodb_hostname = config["mongodb_setup"]["meta"]["hostname"]

        base_canary_config = {
            "test_id": "iperf",
            "test_type": "iperf",
            "output_files": ["iperf.json"],
            "cmd": numactl_prefix + " ./iperf-test.sh " + mongodb_hostname,
        }
        super().__init__(**base_canary_config)

        self.skip_validate = True

    def as_dict(self):
        return {
            "id": self.test_id,
            "type": self.test_type,
            "output_files": self.output_files,
            "cmd": self.cmd,
            "skip_validate": self.skip_validate,
        }


def get_canary(canary_type, config):
    """
    Get the canary test for a given canary type.

    :return: an instance of a _BaseCanary subclass.
    """

    if canary_type == "cpu_noise":
        return CpuNoise(config)
    if canary_type == "fio":
        return Fio(config)
    if canary_type == "iperf":
        return IPerf(config)
    return None


def get_canaries(config):
    """
    Get all the canaries that should run.

    :return: the list of canary tests as dict that should run.
    """

    canaries = []
    if should_run(config):
        for canary_type in CANARY_TYPES:
            canaries.append(get_canary(canary_type, config).as_dict())
    return canaries
