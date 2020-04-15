"""Helper functions that don't fit anywhere else"""


import requests

NETWORK_TIMEOUT_SECS = 120
GIT_HASH_LEN = 40
GITHUB_API = "https://api.github.com"
GH_USER = "mongodb"
GH_REPO = "mongo"
GH_BASIC_AUTH = "x-oauth-basic"


def get_full_git_commit_hash(prefix, token=None):
    """Use the Github API to search for the full git commit hash
    when only the hash prefix has been submitted.

    :param str prefix: prefix for a git commit hash
    :param str token: github user authentication token
    :rtype: str
    :raises: HTTPError if retrieval of full commit hash has failed.
    """
    if len(prefix) == GIT_HASH_LEN:
        return prefix
    request = "{url}/repos/{user}/{repo}/commits/{prefix}".format(
        url=GITHUB_API, user=GH_USER, repo=GH_REPO, prefix=prefix
    )
    if token is not None:
        if "token" in token:  # sent as a header 'token: OAUTH_TOKEN'
            response = requests.get(request, headers={"Authorization": token})
        else:
            response = requests.get(request, auth=(token, GH_BASIC_AUTH))
    else:  # no authentication token
        response = requests.get(request)

    if response.ok:
        commit_info = response.json()
        return str(commit_info["sha"])

    return response.raise_for_status()


def get_as_json(url, **kwargs):
    """Issue a GET request and return the response as JSON.

    :type url: str
    :param kwargs: Keyword arguments passed to `request.get()`
    :rtype: dict
    :raises: HTTPError if the response is not OK
    """
    response = requests.get(url, timeout=NETWORK_TIMEOUT_SECS, **kwargs)
    if response.ok:
        return response.json()
    return response.raise_for_status()
