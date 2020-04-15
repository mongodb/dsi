#!/usr/bin/env python3.7

"""
Consolidates infrastructure_provisioning, workload_setup, mongodb_setup commands
"""

from dsi.infrastructure_provisioning import main as infrastructure_provisioning
from dsi.mongodb_setup import main as mongodb_setup
from dsi.workload_setup import main as workload_setup


def main():
    """ Main function """
    infrastructure_provisioning()
    workload_setup()
    mongodb_setup()


if __name__ == "__main__":
    main()
