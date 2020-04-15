"""
AWS tools for cleaning up stranded EC2 resources deployed by DSI

This may get extended to install all of DSI as part of https://jira.mongodb.org/browse/PERF-1217.
"""
# pylint: disable=no-name-in-module,import-error, invalid-name, E1101
# https://github.com/PyCQA/pylint/issues/73

from setuptools import setup

# pylint: disable=line-too-long
# The minimum set required to run.
# Different from requirements.txt, which is the complete python environment for the project
# including tests etc.
# See 'requires v requirements<https://packaging.python.org/discussions/install-requires-vs-requirements/>'.
# pylint: disable=invalid-name
install_requirements = [
    "boto3==1.9.243",
    "requests~=2.22.0",
]
setup(
    name="AWS tools for DSI",
    version="1.1",
    description="AWS tools for cleaning up stranded EC2 resources deployed by DSI",
    install_requires=install_requirements,
    zip_safe=False,  # Probably not zip_safe due to whereami's reliance on .repo-root but untested.
    use_2to3=True,
    entry_points={
        "console_scripts": [
            "delete-stranded-vpcs = aws_tools.entry_points:delete_stranded_vpcs",
            "delete-cluster = aws_tools.entry_points:delete_cluster_by_tag",
            "delete-runner-cluster = aws_tools.entry_points:delete_cluster_for_runner",
            "delete-task-cluster = aws_tools.entry_points:delete_cluster_for_task",
            "delete-placement-groups = aws_tools.entry_points:delete_placement_groups",
        ]
    },
)
