"""
A thin client around Atlas REST API calls we use.

Not complete, rather add calls as you need them.
"""


import os
import shutil
import time

import requests
import requests.auth as auth
import structlog

from dsi.common.utils import mkdir_p

LOG = structlog.get_logger(__name__)

DEFAULT_ROOT_URL = "https://cloud.mongodb.com/api/atlas/v1.0/"
PRIVATE_ROOT_URL = "https://cloud.mongodb.com/api/private/"


class AtlasTimeout(RuntimeError):
    """
    Raised when Atlas HTTP requests return ok but a desired state was not reached within a timeout.
    """

    def __init__(self, operation, target_state, last_state, timeout_seconds):
        """
        Instantiate the exception.

        :param str operation: What operation timed out. Ex: "get_one_cluster"
        :param str target_state: What target state wasn't reached. Ex: "IDLE"
        :param str last_state: Last returned state (that wasn't the target state). Ex: "CREATING"
        :param int timeout_seconds: The timeout in seconds.
        """
        super(AtlasTimeout, self).__init__()
        self.operation = operation
        self.target_state = target_state
        self.last_state = last_state
        self.timeout_seconds = timeout_seconds

    def __repr__(self):
        msg = (
            "Atlas operation '{}' didn't reach '{}' state within {} seconds. "
            + "Last state was: '{}'."
        )
        return msg.format(self.operation, self.target_state, self.timeout_seconds, self.last_state)


class AtlasClient:
    """
    A thin client around Atlas REST API calls we use.

    TODO: Especially for delete of cluster, would be nice to support retries on http/network failure

    :raises HTTPError: As raised by requests.Response.raise_for_status()
    """

    def __init__(self, configuration, credentials):
        """
        Initiate an object with configuration and credentials.

        The initialized client will then operate within the given Atlas group, and the given user.
        Other than this, it is stateless: methods are merely HTTP wrappers.

        Note: credentials passed in as a separate object to keep them from being accidentally
        dumped to logs.

        :param dict configuration: group_id (required) and api root url (optional)
        :param dict credentials: user and key (required)
        """
        self.group_id = configuration["group_id"]
        self.root = configuration.get("root", DEFAULT_ROOT_URL)
        self.root += "/" if self.root[-1] != "/" else ""
        self.private_root = configuration.get("private", PRIVATE_ROOT_URL)
        self.private_root += "/" if self.private_root[-1] != "/" else ""

        # Check and fail early if credentials missing
        assert credentials["public_key"]
        assert credentials["private_key"]
        self.auth = auth.HTTPDigestAuth(credentials["public_key"], credentials["private_key"])

    ### CLUSTER CREATION / LIFECYCLE

    def create_cluster(self, configuration):
        """
        Create new Atlas cluster using `configuration` as the request body.

        For creating a cluster using a custom build,
        see :method: `AtlasClient.create_custom_cluster`.

        `POST groups/{GROUP-ID}/clusters`

        https://docs.atlas.mongodb.com/reference/api/clusters-create-one/

        :param dict configuration: Dictionary to use as json request body.
        :return: Response object as dictionary.
        """
        url = "{}groups/{}/clusters".format(self.root, self.group_id)
        response = requests.post(url, json=configuration, auth=self.auth)
        LOG.debug(
            "After create cluster request",
            headers=response.request.headers,
            body=response.request.body,
        )
        if not response.ok:
            LOG.error("HTTP error in create_cluster", response=response.json())
            return response.raise_for_status()
        return response.json()

    def get_one_cluster(self, cluster_name):
        """
        Get status for cluster_name.

        `GET groups/{GROUP-ID}/clusters/{CLUSTER-NAME}`

        https://docs.atlas.mongodb.com/reference/api/clusters-get-one/

        :param str cluster_name: The Atlas CLUSTER-NAME in GROUP-ID from init.
        :return: The Atlas response, which contains state and meta-data about the cluster.
        """
        url = "{}groups/{}/clusters/{}".format(self.root, self.group_id, cluster_name)
        response = requests.get(url, auth=self.auth)
        LOG.debug("After get one cluster request", headers=response.request.headers)
        if not response.ok:
            LOG.error("HTTP error in get_one_cluster", response=response.json())
            return response.raise_for_status()
        return response.json()

    # pylint: disable=assign-to-new-keyword
    def await_idle(self, cluster_name):
        """
        Wait until cluster creation is considered finished.

        Current implementation is to wait for status == IDLE.

        :param str cluster_name: The Atlas CLUSTER-NAME in GROUP-ID from init.
        :return: The Atlas response, which contains state and meta-data about the cluster.
        """
        return self.await_state(cluster_name, "IDLE")

    def await_state(self, cluster_name, target_state, timeout_seconds=2000):
        """
        Periodically poll cluster_name. Return when stateName == target_state.

        :param str cluster_name: The Atlas CLUSTER-NAME in GROUP-ID from init.
        :param str target_state: The Atlas stateName to wait for. Ex: "IDLE".
        :param int timeout_seconds: Seconds after which to raise AtlasTimeout.
        :raises: AtlasTimeout if Atlas fails to arrive at the target_state.
        :return: The Atlas response, which contains state and meta-data about the cluster.
        """
        end_time = time.time() + timeout_seconds
        while True:
            # The await_idle state occassionaly fails it's query, particularly in
            # cluster types that take longer to spawn (e.g., NVMe).
            try:
                cluster = self.get_one_cluster(cluster_name)
                LOG.info(
                    "Await state",
                    cluster_name=cluster_name,
                    status=cluster["stateName"],
                    target_state=target_state,
                )
                if cluster["stateName"] == target_state:
                    return cluster
            except requests.exceptions.HTTPError:
                LOG.exception(
                    "In await_idle state and self.get_one_cluster threw. Catching and moving on."
                )
            time.sleep(30)
            if time.time() > end_time:
                raise AtlasTimeout(
                    "get_one_cluster", target_state, cluster["stateName"], timeout_seconds
                )

    def delete_cluster(self, cluster_name):
        """
        Delete a cluster with the given cluster_name.

        DELETE groups/{GROUP-ID}/clusters/{CLUSTER-NAME}

        https://docs.atlas.mongodb.com/reference/api/clusters-delete-one/

        :param str cluster_name: The Atlas CLUSTER-NAME in GROUP-ID from init.
        :return: The created jobId as string.
        """
        url = "{}groups/{}/clusters/{}".format(self.root, self.group_id, cluster_name)
        response = requests.delete(url, auth=self.auth)
        LOG.debug("After delete cluster request", headers=response.request.headers)
        if not response.ok:
            LOG.error("HTTP error in delete_cluster", response=response.json())
            return response.raise_for_status()
        return True

    ### LOG COLLECTION

    def create_log_collection_job(self, options=None):
        """
        Create a "job" which can later be accessed to download mongod.log and ftdc.

        POST groups/{GROUP-ID}/logCollectionJobs

        options = {
            "resourceType": "replicaset",
            "resourceName": "clustername-shard-0",
            "sizeRequestedPerFileBytes": 1000,
            "redacted": false,
            "logTypes": ["FTDC", "MONGODB", "AUTOMATION_AGENT", "BACKUP_AGENT", "MONITORING_AGENT"]
        }

        https://wiki.corp.mongodb.com/pages/viewpage.action?spaceKey=MMS&title=Atlas+Performance+Testing+Support#AtlasPerformanceTestingSupport-CollectandDownloadLogs  # pylint: disable=line-too-long

        :param dict options: A dict with options, see above. REQUIRED.
        :return: The logCollectionJob id as string.
        """
        url = "{}groups/{}/logCollectionJobs".format(self.root, self.group_id)
        response = requests.post(url, json=options, auth=self.auth)
        LOG.debug(
            "After create logCollectionJob request",
            headers=response.request.headers,
            body=response.request.body,
        )
        if not response.ok:
            LOG.error("HTTP error in create_log_collection_job", response=response.json())
            return response.raise_for_status()
        result = response.json()
        return result["id"]

    def get_log_collection_job(self, log_job_id):
        """
        Get status for a (previously created) logCollectionJob.

        GET groups/{GROUP-ID}/logCollectionJobs/{JOB-ID}

        :param str log_job_id: ID of the job to poll.
        :return: The logCollectionJob status as dict.
        """
        url = "{}groups/{}/logCollectionJobs/{}".format(self.root, self.group_id, log_job_id)
        response = requests.get(url, auth=self.auth)
        LOG.debug("After get logCollectionJob request", headers=response.request.headers)
        if not response.ok:
            LOG.error("HTTP error in get_log_collection_job", response=response.json())
            return response.raise_for_status()
        return response.json()

    def await_log_job(self, log_job_id):
        """
        Wait until a logCollectionJob is ready for download.

        Wait for status == SUCCESS.

        :param str log_job_id: ID of the job to poll.
        :return: The Atlas response, which contains state about the logCollectionJob.
        """
        return self.await_log_job_state(log_job_id, "SUCCESS")

    def await_log_job_state(self, log_job_id, target_state, timeout_seconds=2500):
        """
        Periodically poll log_job_id. Return when status == target_state.

        :param str log_job_id: The Atlas logCollectionJobs ID.
        :param str target_state: The Atlas stateName to wait for. Ex: "IDLE".
        :param int timeout: Seconds after which to raise AtlasTimeout.
        :raises: AtlasTimeout if Atlas fails to arrive at the target_state.
        :return: The Atlas response, which contains state about the logCollectionJob.
        """
        end_time = time.time() + timeout_seconds
        while True:
            try:
                job_status = self.get_log_collection_job(log_job_id)
                LOG.info(
                    "Await logCollectionJobs state",
                    log_job_id=log_job_id,
                    status=job_status["status"],
                    target_state=target_state,
                )
                if job_status["status"] == target_state:
                    return job_status
            except requests.exceptions.HTTPError:
                LOG.exception(
                    "In await_idle state and get_log_collection_job() threw. "
                    "Catching and moving on."
                )
            time.sleep(10)
            if time.time() > end_time:
                raise AtlasTimeout(
                    "get_log_collection_job", target_state, job_status["stateName"], timeout_seconds
                )

    def download_logs(self, log_job_id, local_path):
        """
        Download a tar.gz file with logs from the given job id.

        GET groups/{groupId}/logCollectionJobs/{jobId}/download

        :param str log_job_id: A string previously returned by create_log_collection_job().
        :param str local_path: The local file where to store the downloaded file.
        """
        url = "{}groups/{}/logCollectionJobs/{}/download".format(
            self.root, self.group_id, log_job_id
        )
        with requests.get(url, auth=self.auth, stream=True) as response:
            if not response.ok:
                LOG.error("HTTP error in download_logs", response=response.json())
                response.raise_for_status()
            else:
                LOG.info("Downloading Atlas log file.", local_path=local_path)
                mkdir_p(os.path.dirname(local_path))
                with open(local_path, "w") as file_handle:
                    shutil.copyfileobj(response.raw, file_handle)

    ### CUSTOM BUILD

    def create_custom_build(self, configuration):
        """
        Add new custom build using `configuration` as the request body.

        `POST /api/private/nds/customMongoDbBuild`

        https://wiki.corp.mongodb.com/pages/viewpage.action?spaceKey=MMS&title=Atlas+Performance+Testing+Support

        :param dict configuration: Dictionary to use as json request body.
        """
        url = "{}nds/customMongoDbBuild".format(self.private_root)
        LOG.debug("customMongoDbBuild input", json=configuration, url=url)
        response = requests.post(url, json=configuration, auth=self.auth)
        LOG.debug(
            "After customMongoDbBuild request",
            headers=response.request.headers,
            body=response.request.body,
        )
        if not response.ok:
            response_body = response.json()
            # If build already exists, then all is well.
            if response_body.get("errorCode") == "DUPLICATE_MONGODB_BUILD_NAME":
                existing_configuration = self.get_custom_build(configuration["trueName"])
                if configuration["url"] == existing_configuration["url"]:
                    LOG.info(
                        "Custom build already exists. (This is ok.)",
                        trueName=configuration["trueName"],
                    )
                else:
                    LOG.error(
                        "Custom build already exists for this trueName, but your "
                        + "URL is different.",
                        trueName=configuration["trueName"],
                        your_url=configuration["url"],
                        existing_url=existing_configuration["url"],
                    )
                    LOG.error("HTTP error in create_custom_build", response=response_body)
                    response.raise_for_status()
            else:
                LOG.error("HTTP error in create_custom_build", response=response_body)
                response.raise_for_status()

    def get_custom_build(self, true_name):
        """
        Get custom build.

        `GET /api/private/nds/customMongoDbBuild/{trueName}`

        :param str true_name: The trueName of the custom build.
        :return: Response json as dict.
        """
        url = "{}nds/customMongoDbBuild/{}".format(self.private_root, true_name)
        response = requests.get(url, auth=self.auth)
        LOG.debug("After GET customMongoDbBuild request", headers=response.request.headers)
        if not response.ok:
            LOG.error("HTTP error in get_custom_build", response=response.json())
            return response.raise_for_status()
        return response.json()

    def create_custom_cluster(self, configuration):
        """
        Create new cluster from custom build.

        This is used instead of :method: `AtlasClient.create_cluster` when
        deploying a custom build.

        configuration["mongoDBVersion"] should match trueName of a previously added custom build.

        `POST /api/private/nds/groups/{groupId}/clusters`

        https://wiki.corp.mongodb.com/pages/viewpage.action?spaceKey=MMS&title=Atlas+Performance+Testing+Support

        :param dict configuration: Dictionary to use as json request body.
        :return: Atlas response as dict.
        """
        url = "{}nds/groups/{}/clusters".format(self.private_root, self.group_id)
        response = requests.post(url, json=configuration, auth=self.auth)
        LOG.debug(
            "After create_custom_cluster request",
            headers=response.request.headers,
            body=response.request.body,
        )
        if not response.ok:
            LOG.error("HTTP error in create_custom_cluster", response=response.json())
            return response.raise_for_status()
        return response.json()
