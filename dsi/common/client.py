"""
Classes representing workload clients and their configuration.
"""
from dsi.common import host_factory, mongodb_setup_helpers
from dsi.common.host_utils import ssh_user_and_key_file
from dsi.common.models.host_info import HostInfo
from dsi.delay import HasDelay, DelayGraph


# pylint: disable=too-many-instance-attributes
class ClientConfig:
    """
    Class representing the configuration for a workload client.
    """

    def __init__(self, config):
        """
        :param config: The infrastructure_provisioning ConfigDict
        """
        inf_prov_out = config["infrastructure_provisioning"]
        client_config = inf_prov_out["out"]["workload_client"][0]
        self.use_tls = mongodb_setup_helpers.mongodb_tls_configured(
            config["mongodb_setup"]["mongod_config_file"]
        )
        self.public_ip = client_config["public_ip"]
        self.private_ip = client_config["private_ip"]
        (self.ssh_user, self.ssh_key_file) = ssh_user_and_key_file(config)

        self.delay_node = DelayGraph.client_node

    def compute_host_info(self):
        """Create host wrapper to run commands."""
        return HostInfo(
            public_ip=self.public_ip,
            private_ip=self.private_ip,
            ssh_user=self.ssh_user,
            ssh_key_file=self.ssh_key_file,
        )


class Client(HasDelay):
    """
    Class representing a connection to a workload client.
    """

    def __init__(self, client_config):
        """
        :param client_config: The ClientConfig for this client.
        """

        self.client_config = client_config
        self._host = None
        self.delay_node = client_config.delay_node
        super(Client, self).__init__(self.delay_node)

    @property
    def host(self):
        """Access to remote or local host."""
        if self._host is None:
            host_info = self.client_config.compute_host_info()
            self._host = host_factory.make_host(host_info, use_tls=self.client_config.use_tls)
        return self._host

    def reset_delays(self):
        """
        Resets the client's delay configuration.
        """
        self.delay_node.reset_delays(self.host)

    def establish_delays(self):
        """
        Establishes all delays configured for this client.
        """
        self.delay_node.establish_delays(self.host)
