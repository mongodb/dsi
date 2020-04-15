# DSI AWS Tools

Tools to cleanup EC2 resources left behind by Evergreen.

## Setup

### Install

You MUST install these tools with setup.py:

    ./setup.py install --user

Alternatively, to install symlinks that point back to these files in this repo:

    ./setup.py develop --user

### Credentials

You need an `~/.aws/credentials` file. If you don't have one, execute
[`aws configure`](https://docs.aws.amazon.com/cli/latest/userguide/cli-chap-getting-started.html) to
create it.

## Usage

Most of the tools you just execute and they will find and clean up stranded EC2 resources:

    delete-stranded-vpcs
    delete-placement-groups

The `delete-cluster` family of executables however need input to know which hosts will be deleted.
You can use
[our New Relic dashboard](https://insights.newrelic.com/accounts/1728883/dashboards/417811) which
has a "Stranded Hosts" widget. This widget will only show you ec2 hostnames and evergreen task_ids
mixed into the same list. You typically use the task_id:

    delete-task-cluster -t TASK_ID

Alternatively, you can use:

    delete-runner-cluster -r RUNNER
    delete-cluster --key ANY_TAG --value VALUE

## TODO

See PERF-1685 for streamlining the `delete-cluster`