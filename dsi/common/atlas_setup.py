"""
MongoDB Setup but for Atlas clusters

Instead of creating our own MongoDB clusters, we make REST calls to Atlas instead.
"""

import copy
import random

import pymongo
import structlog
from six.moves import range

from dsi.common import atlas_client

LOG = structlog.get_logger(__name__)


class AtlasSetup:
    """
    MongodbSetup for Atlas.
    """

    # pylint: disable=too-many-instance-attributes

    def __init__(self, config):
        """
        Initialize the object from config.

        :param ConfigDict config: The DSI config.
        """
        self.config = config
        self.mongodb_setup = self.config["mongodb_setup"]
        # Note that both for api and api_credentials, they will only exist
        self.api = {}
        if "atlas" in self.mongodb_setup and "api" in self.mongodb_setup["atlas"]:
            self.api = self.mongodb_setup["atlas"]["api"].as_dict()
            LOG.debug("Atlas api config", api_config=self.api)
            self.custom_build = self.mongodb_setup["atlas"].as_dict().get("custom_build")
            LOG.debug("Atlas custom build config", custom_build=self.custom_build)

        self.api_credentials = {}
        if (
            "atlas_api_public_key" in self.config["runtime_secret"]
            and "atlas_api_private_key" in self.config["runtime_secret"]
        ):

            self.api_credentials["public_key"] = self.config["runtime_secret"].get(
                "atlas_api_public_key", ""
            )
            self.api_credentials["private_key"] = self.config["runtime_secret"].get(
                "atlas_api_private_key", ""
            )
            LOG.debug(
                "Atlas credentials",
                user=self.api_credentials["public_key"],
                key=(
                    self.api_credentials["private_key"][0:5]
                    if self.api_credentials["private_key"]
                    else ""
                ),
            )

        self.atlas_client = None
        if "root" in self.api and "group_id" in self.api and self.api_credentials:
            self.atlas_client = atlas_client.AtlasClient(self.api, self.api_credentials)

    def _init_config_out(self):
        if not "out" in self.mongodb_setup:
            self.mongodb_setup["out"] = {}
        if not "atlas" in self.mongodb_setup["out"]:
            self.mongodb_setup["out"]["atlas"] = {}
        if not "clusters" in self.mongodb_setup["out"]["atlas"]:
            self.mongodb_setup["out"]["atlas"]["clusters"] = []

    def start(self):
        """
        Deploy cluster(s) as given in mongodb_setup.yml configuration.

        :return: True if all clusters succeeded.
        """
        # The intended use is to deploy as many clusters as specified in
        # mongodb_setup.atlas.clusters and then later shut them down via destroy().
        # Repeated calls to start() would generate new cluster(s) with new unique name(s).
        # I decided that would probably be a bad thing, so not supporting repeated start() without
        # calling destroy() in between.
        if self.mongodb_setup.get("out", {}).get("atlas", {}).get("clusters", []):
            LOG.error("Clusters already exist in mongodb_setup.out.atlas.clusters.")
            LOG.error("Please shutdown existing clusters first with infrastructure_teardown.py.")
            LOG.debug("Start atlas cluster", out=self.mongodb_setup["out"])
            raise RuntimeError("Clusters already exist in mongodb_setup.out.atlas.clusters.")

        if "atlas" in self.mongodb_setup and "clusters" in self.mongodb_setup["atlas"]:
            LOG.info("AtlasSetup.start")
            if not self.atlas_client:
                LOG.error("Trying to start Atlas Clusters, but self.atlas_client not initialized")
                raise UserWarning
            return all(
                self.create_cluster(atlas_cluster)
                for atlas_cluster in self.mongodb_setup["atlas"]["clusters"]
            )

        # else
        LOG.debug("AtlasSetup.start: Nothing to do.")
        return True

    def destroy(self):
        """
        Destroy the cluster(s) listed in `mongodb_setup.out.atlas.clusters`.
        """
        clusters_list = self.mongodb_setup.get("out", {}).get("atlas", {}).get("clusters", [])
        LOG.info(
            "About to shutdown Atlas clusters",
            clusters=[atlas_cluster["name"] for atlas_cluster in clusters_list],
        )
        return all(self.delete_cluster(atlas_cluster) for atlas_cluster in clusters_list)

    def create_cluster(self, atlas_cluster):
        """
        Deploy single cluster.

        Waits until a cluster is ready (stateName). Generates and stores a unique cluster name to
        `mongodb_setup.out.atlas.clusters.*.name`.

        :param ConfigDict atlas_cluster: One cluster from mongodb_setup.atlas.clusters.*
        :return: True if successful.
        :raises HTTPError: As raised by requests.Response.raise_for_status().
        """
        name = self._generate_unique_name(atlas_cluster)
        body = atlas_cluster.as_dict()
        body["name"] = name

        LOG.debug("Atlas custom build config", custom_build=self.custom_build)
        if self.custom_build is not None:
            LOG.info(
                "Create Atlas CUSTOM BUILD Cluster",
                instance_size_name=body["providerSettings"]["instanceSizeName"],
                cluster_type=body["clusterType"],
                name=body["name"],
                custom_build_config=self.custom_build,
            )
            self.atlas_client.create_custom_build(self.custom_build)
            body.pop("mongoDBMajorVersion", None)
            body["mongoDBVersion"] = self.custom_build["trueName"]
            response = self.atlas_client.create_custom_cluster(body)
        else:
            LOG.info(
                "Create Atlas Cluster",
                instance_size_name=body["providerSettings"]["instanceSizeName"],
                cluster_type=body["clusterType"],
                name=body["name"],
            )
            response = self.atlas_client.create_cluster(body)

        LOG.debug("Create cluster response", response=response)
        # This response still lacks meta data, but we want to persist the cluster name asap
        self._save_create_response(response)
        response = self.atlas_client.await_idle(body["name"])
        LOG.debug("After cluster await_idle", response=response)
        # Save MongoDB URI and such to mongodb_setup.out.yml
        self._save_create_response(response)
        LOG.info(
            "Done creating Atlas cluster",
            instance_size_name=body["providerSettings"]["instanceSizeName"],
            cluster_type=body["clusterType"],
            name=body["name"],
        )
        return True

    @staticmethod
    def _generate_unique_name(atlas_cluster):
        chars = "abcdefghijklmnopqrstuvwxyz"
        unique = "".join([random.choice(chars) for _ in range(7)])
        return "dsi-{}-{}".format(
            atlas_cluster["providerSettings"]["instanceSizeName"].replace("_", ""), unique
        )

    def _save_create_response(self, response):
        self._init_config_out()
        new_object = {}
        save_fields = (
            "log_job_id",
            "mongoURI",
            "mongoURIWithOptions",
            "mongoURIUpdated",
            "name",
            "stateName",
            "clusterType",
        )
        prefix = len("mongodb://")
        for key in save_fields:
            if key in response:
                new_object[key] = response[key]
                # Store a couple things without mongodb:// prefix. These are useful as building
                # blocks in the config file.
                if key == "mongoURIWithOptions":
                    new_object["mongodb_url"] = response[key][prefix:]
                    # Get hostname and port of the primary, since benchrun doesn't support uri
                    hostname, port = self._get_primary(new_object["mongodb_url"])
                    new_object["hostname"] = hostname
                    new_object["port"] = port
                if key == "mongoURI":
                    new_object["hosts"] = response[key][prefix:]

        LOG.debug("_save_create_response", new_cluster=new_object)
        # While this is a list, we actually lookup by cluster name.
        # An alternative design would have been for mongodb_setup.out.atlas.clusters to be a dict
        # keyed on name. That is really what this code is doing. But I wanted to keep it a list so
        # that it matches the list user provides in mongodb_setup.atlas.clusters.
        index = self._find_cluster_in_list(new_object)
        # assign and append() won't work in a ConfigDict, but works if I take out the list first
        clusters_list = self.mongodb_setup["out"]["atlas"]["clusters"]
        if index is not None:
            # Replace existing entry
            clusters_list[index] = new_object
        else:
            # New cluster / first save
            clusters_list.append(new_object)
        # Then assign the entire list back to the ConfigDict
        self.mongodb_setup["out"]["atlas"]["clusters"] = clusters_list

        LOG.debug("Mongodb_setup output", out=self.mongodb_setup["out"])
        self.config.save()  # Creates mongodb_setup.out.yml

    def delete_cluster(self, atlas_cluster):
        """
        Shutdown given cluster, using its name.

        :param ConfigDict atlas_cluster: An object from `mongodb_setup.out.atlas.clusters`. Must
                                         contain a `name` field.
        :return: True if successful.
        :raises HTTPError: As raised by requests.Response.raise_for_status().
        """
        if not "name" in atlas_cluster:
            LOG.error("Cannot delete cluster without a name in the meta data!")
            return False

        name = atlas_cluster["name"]
        LOG.info("Shutting down Atlas cluster", name=name)
        if self.atlas_client.delete_cluster(name):
            LOG.info("Shutting down Atlas cluster succeeded.", name=name)
            # Bookkeeping: delete this cluster from `mongodb_setup.out.atlas.clusters`
            self._remove_cluster_from_list(atlas_cluster)
            LOG.debug("Mongodb_setup.out after shutdown", out=self.mongodb_setup["out"])
            self.config.save()
            return True

        # else:
        LOG.error("Shutting down Atlas cluster FAILED.", name=name)
        return False

    def _remove_cluster_from_list(self, atlas_cluster):
        found = False
        self._init_config_out()
        clusters = copy.copy(self.mongodb_setup["out"]["atlas"]["clusters"])
        for i, cluster in enumerate(self.mongodb_setup["out"]["atlas"]["clusters"]):
            if cluster["name"] == atlas_cluster["name"]:
                del clusters[i]
                found = True
        if not found:
            raise LookupError("Didn't find a cluster with name = {}".format(atlas_cluster["name"]))
        self.mongodb_setup["out"]["atlas"]["clusters"] = clusters

    def _find_cluster_in_list(self, atlas_cluster):
        clusters_list = self.mongodb_setup.get("out", {}).get("atlas", {}).get("clusters", [])
        name = atlas_cluster["name"]
        for index, cluster in enumerate(clusters_list):
            if cluster["name"] == name:
                return index
        return None

    def _get_primary(self, mongodb_url_tail):
        """
        Get hostname and port of the primary (for benchrun).

        :param str mongodb_url_tail: The part of a mongodb url that comes after the @.
        :return: (hostname, port) of the primary at startup time.
        :rtype: tuple(string, int)
        """
        # For mongodb_cluster we use host.py classes to SSH and use mongo shell and javascript.
        # But here it seemed more straightforward to just pymongo straight to the Atlas cluster.
        username = self.config["mongodb_setup"]["authentication"]["username"]
        password = self.config["mongodb_setup"]["authentication"]["password"]
        uri = "mongodb://{}:{}@{}".format(username, password, mongodb_url_tail)
        LOG.debug("Connecting to new Atlas cluster to discover primary node.", uri=uri)
        client = pymongo.MongoClient(uri)
        db = client.admin
        ismaster = db.command("isMaster")
        hostname, port = ismaster["primary"].split(":")
        return hostname, int(port)

    def download_logs(self, dir_in_reports):
        """
        Download mongod.log and ftdc from Atlas.

        Two Atlas API calls are needed: First create the logCollectionJob, then download its file.

        See https://wiki.corp.mongodb.com/display/MMS/Atlas+Performance+Testing+Support#AtlasPerformanceTestingSupport-CollectandDownloadLogs  # pylint: disable=line-too-long
        See https://wiki.corp.mongodb.com/display/PS/Atlas+Tips+and+Tricks

        :param str dir_in_reports: A prefix to use in the path of the downloaded file.
        """
        clusters_list = self.mongodb_setup.get("out", {}).get("atlas", {}).get("clusters", [])
        for atlas_cluster in clusters_list:
            # To request logs for a single node:
            # "resourceType": "PROCESS"
            # "resourceName": "CLUSTERNAME-shard-x-node-y"
            # Example: "Cluster0-shard-1-node-0"
            #
            # To request logs for a replica set or shard:
            # "resourceType": "REPLICASET"
            # "resourceName": "CLUSTERNAME-shard-x"
            # Example: "Cluster0-shard-0"
            #
            # To request logs for a sharded cluster:
            # "resourceType": "CLUSTER"
            # "resourceName": "CLUSTERNAME"
            # Example: "Cluster0"
            options = {
                "resourceType": atlas_cluster["clusterType"],
                "resourceName": atlas_cluster["name"] + "-shard-0",
                "sizeRequestedPerFileBytes": 999999999,
                "redacted": False,
                "logTypes": ["FTDC", "MONGODB", "AUTOMATION_AGENT"],
            }
            log_job_id = self.atlas_client.create_log_collection_job(options)
            self.atlas_client.await_log_job(log_job_id)
            filepath = "reports/{}/{}.tgz".format(dir_in_reports, atlas_cluster["name"])
            self.atlas_client.download_logs(log_job_id, filepath)
