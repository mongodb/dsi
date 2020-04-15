"""
Helper functions related to mongodb_setup.
"""


from collections import namedtuple

import jinja2

from dsi.common.config import copy_obj

MongoDBAuthSettings = namedtuple("MongoDBAuthSettings", ["mongo_user", "mongo_password"])
MongoDBTLSSettings = namedtuple("MongoDBTLSSettings", ["ca_file", "pem_key_file"])


def mongodb_auth_configured(config):
    """
    Determine if authentication should be enabled.

    :param ConfigDict config: The configuration object.
    :returns: True if authentication should be enabled, otherwise false.
    :rtype: boolean.
    """

    return config["mongodb_setup"]["authentication"]["enabled"]


def mongodb_auth_settings(config):
    """
    Read the config file and return a namedtuple with the authentication settings.

    :param ConfigDict config: The configuration.
    :returns: The mongo user and password information.
    :rtype: MongoDBAuthSettings.
    """

    if not mongodb_auth_configured(config):
        return None
    return MongoDBAuthSettings(
        config["mongodb_setup"]["authentication"]["username"],
        config["mongodb_setup"]["authentication"]["password"],
    )


def mongodb_tls_configured(config_file):
    """
    Is TLS configured in the mongo node config file.

    The common case is for the argument to be a mongo node config file from mongodb_setup.topology.

    :param config_file: ConfigDict key mongodb_setup.topology.*.config_file or equivalent structure
    :return: if tls is enabled
    """
    if "net" in config_file:
        net = config_file["net"]
        return "ssl" in net and net["ssl"]["mode"] in {"requireSSL", "allowSSL", "preferSSL"}
    return False


def mongodb_tls_settings(config_file):
    """
    Parse TLS settings from a mongo node config file.

    The common case is for the argument to be a mongo node config file from mongodb_setup.topology.

    :param config_file: ConfigDict key mongodb_setup.topology.*.config_file or equivalent structure
    :return: None if not configured for ssl else MongoDBTLSSettings
    """
    if not mongodb_tls_configured(config_file):
        return None

    ssl = config_file["net"]["ssl"]
    return MongoDBTLSSettings(ssl["CAFile"], ssl["PEMKeyFile"])


def add_user(cluster, auth_settings, write_concern=1):
    """
    Database command to add a root user to the given cluster. The username and password of the user
    are found in the config file.

    :param MongoCluster cluster: The cluster to which the user will be added.
    :param int write_concern: The number of nodes in the cluster that should acknowlege write
    operations requested by the client. The default is 1.
    """
    script_template = jinja2.Template(
        """
        db.getSiblingDB("admin").createUser(
          {
            user: {{user|tojson}},
            pwd: {{password|tojson}},
            roles: [ { role: "root", db: "admin" } ]
          },
          {
            w: {{wc|tojson}},
            wtimeout: 10000
          });"""
    )

    add_user_script = script_template.render(
        user=auth_settings.mongo_user, password=auth_settings.mongo_password, wc=write_concern
    )
    cluster.run_mongo_shell(add_user_script)


def merge_dicts(base, override):
    """
    Recursively merges nested dictionaries.

    We use this in MongodbSetup to merge a ConfigDict and a dict, and return a dict.
    """
    copy = copy_obj(base)
    # update takes care of overriding non-dict values
    copy.update(override)
    for key in copy:
        if key in base and isinstance(copy[key], dict) and isinstance(base[key], dict):
            copy[key] = merge_dicts(base[key], copy[key])
    return copy
