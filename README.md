# DSI: distributed system test infrastructure

> > This project uses GitHub PRs for changes. See below section on patch-testing if you're new.

## Intro

The big picture of system performance is as follows:

-   Evergreen uses a project file to run a task, where each task may represent multiple tests.
-   As part of executing this task, Evergreen will prepare a host on which DSI will be executed.
-   When DSI is executed on this host, the DSI node itself will spin up a variety of hosts, depending on the exact task being run.
-   Some of these hosts will contain mongod instances, while others will act as workload clients. (At the moment only a single workload client is supported.)
-   A workload client is a node that performs some workload designed to stress the system of mongod instances. After executing, the cluster set up by the DSI node is closed down and the data stored.
-   While many different hosts may be used in a given run of sys-perf, **DSI itself is only ever executed on Evergreen hosts**. Other operations, such as setting up mongod instances, are performed using SSH on nodes spun up by DSI.

## DSI in Evergreen and `system_perf.yml`

System performance testing, or "sys-perf", is [an Evergreen project][waterfall] whose goal is detecting inabilities of the mongodb server to live up to certain performance guarantees, or to detect abrupt changes in performance. For background on Evergreen, check out the [Evergreen wiki][evgwiki], particularly the article describing [project files][evgprx].

This project is controlled by the [etc/system_perf.yml][pyml] file. Each task will execute a series of functions, which we will discuss in order. Each function assumes the previous have been executed.

The [etc/system_perf.yml][pyml] file has a few high-level functions.

1.  [`prepare environment`][prep]  
    Does everything needed to prepare the DSI node for execution. It will download all git repositories, then output a `bootstrap.yml` that is dynamically generated to contain all the values needed for DSI to run correctly. For example, if a task specifies a certain `mongodb_setup.*.yml` file, then that file is stated in the `bootstrap.yml` file. It will also prepare the AWS secret keys. Finally, the `bootstrap` script in DSI is executed.

2.  [`deploy cluster`][deploy]  
    Does everything needed to deploy the cluster of mongodb nodes and workload client. It executes the DSI scripts `infrastructure_provisioning`, `workload_setup`, and `mongodb_setup`.

3.  [`run test`][runtest]  
    Actually runs the tests (workloads), now that the cluster has been properly established. This involves executing the `test_control` script of DSI.

4.  [`analyze`][analyze]  
    Detects outliers and runs regressions against past performances.

The stages are discussed in order in the [Running Locally Doc](./RUNNING_LOCALLY.md).

  [waterfall]: https://evergreen.mongodb.com/waterfall/sys-perf
  [evgwiki]: https://github.com/evergreen-ci/evergreen/wiki
  [evgprx]: https://github.com/evergreen-ci/evergreen/wiki/Project-Files
  [pyml]: https://github.com/mongodb/mongo/blob/master/etc/system_perf.yml
  [prep]: https://github.com/mongodb/mongo/blob/ec0bf809b1b60c4edc32146ed971222c30f9d8fa/etc/system_perf.yml#L199
  [deploy]: https://github.com/mongodb/mongo/blob/ec0bf809b1b60c4edc32146ed971222c30f9d8fa/etc/system_perf.yml#L298
  [runtest]: https://github.com/mongodb/mongo/blob/ec0bf809b1b60c4edc32146ed971222c30f9d8fa/etc/system_perf.yml#L310
  [analyze]: https://github.com/mongodb/mongo/blob/ec0bf809b1b60c4edc32146ed971222c30f9d8fa/etc/system_perf.yml#L325


## Running DSI (and Workloads) Locally

Please consult the [Running Locally documentation](./RUNNING_DSI_LOCALLY.md) for more information about installing required binaries and dependencies.

## Developing on DSI

To get started, run the `setup` command:

```sh
./run-dsi setup
```

This will create a `dsi_venv` python virtualenv (using [the built-in venv module](https://docs.python.org/3.7/library/venv.html)) for the purposes of local development. You can activate this environment in your shell with the following:

```sh
source ./dsi_venv/bin/activate
```

You may also need to install development dependencies to run some tests:

```sh
source ./dsi_venv/bin/activate
python3 -m pip install -r ./requirements-dev.txt
```

## Testing Changes

The repo's tests are all packaged into `/testscripts/runtests.sh`, which must be run from the repo root. It requires: a `config.yml` file in the DSI repo root (see `example_config.yml`).

-   *Evergreen credentials*:

    Found in your local `~/.evergreen.yml` file.(Instructions [here](http://evergreen.mongodb.com/settings) if you are missing this file.)

-   *Github authentication token*:

    ```sh
    curl -i -u <USERNAME> \
        -H 'X-GitHub-OTP: <2FA 6-DIGIT CODE>' \
        -d '{"scopes": ["repo"], "note": "get full git hash"}' \
        https://api.github.com/authorizations
    ```

    (You only need `-H 'X-GitHub-OTP: <2FA 6-DIGIT CODE>` if you have 2-factor authentication on.) 

If you don't have a `config.yml` file, you will see failures in tests that use the evergreen client.

**Unit testing** is orchestrated using [nose](https://pypi.org/project/nose/).

Run all the unit tests:

```sh
./run-dsi ./testscripts/run-nosetest.sh
```

Run a specific test:

```sh
./run-dsi ./testscripts/run-nosetest.sh ./dsi/tests/test_config.py
```


## Patch-Testing DSI

Github will automatically run self-tests on evergreen when you submit a PR, but it does not run any "real" DSI workloads (yet). To ensure you don't break any workloads, you must schedule a number of patch-builds against various mongodb performance projects.

```sh
cd mongo

# Unless you're changing the mongo server repo, these patches will be "empty".
evergreen patch -p sys-perf
evergreen patch -p sys-perf-4.4
evergreen patch -p sys-perf-4.2
evergreen patch -p sys-perf-4.0

evergreen patch -p performance
evergreen patch -p performance-4.4
evergreen patch -p performance-4.2
evergreen patch -p performance-4.0

# For each of the above patches, set the DSI module
cd /path/to/dsi
evergreen set-module -m dsi -i <your-build-id>
```

**Notes**:

1. Don't just schedule every task and variant. Speak with members of the STM or Perf team if you have questions.
2. You may not need any branches other than master.
3. The above list was accurate as of 2020-03-12, but new branches are cut regularly.

## Patch-Testing DSI Without Compile

It can be painful to iterate on evergreen yaml files or DSI itself because workload tasks in Evergreen depend on a task that compiles the entirety of mongodb. This can take around 30 minutes. If you don't care about using the latest (tip/master) version of the server, you can force an older, pre-compiled version and skip the compile task.

There are two options.

1.  Repeating a task with a different DSI module. This is the easy way.
2.  Skipping compile entirely. This is the slightly harder way.

**The Easy Way**

You still have to suffer compile once but *only* once.

1.  Create a patch of sys-perf and do the usual `evergreen set-module -m dsi` step.

    ```sh
    cd mongo
    evergreen patch -p sys-perf

    cd /path/to/dsi
    evergreen set-module -m dsi -i <id>
    # ... make changes
    evergreen set-module -m dsi -i <id>
    # reschedule any tasks you want to run again with updated DSI
    ```

2.  Schedule the tasks you want.

You can call `evergreen set-module -m dsi` multiple times on the same patch-build and re-schedule your tasks. The compile task isn't re-run.

**The Slightly Harder Way**

This is the fastest way to run real workloads with your DSI changes, but it requires modifying the yaml code that runs DSI.

Use a hard-coded asset path and remove the compile-task dependency

1.  Replace [this line](https://github.com/mongodb/mongo/blob/ce3261545db4767f18e390c50d59c6530e948655/etc/system_perf.yml#L231) with a static URL e.g.:

    ```yaml
    mongodb_binary_archive: "https://s3.amazonaws.com/mciuploads/dsi/5c8685d3850e61268dd41be1/447847d93d6e0a21b018d5df45528e815c7c13d8/linux/mongodb-5c8685d3850e61268dd41be1.tar.gz"
    ```

    (This is the artifact URL from a previous waterfall run. Update it if tests fail to run because of new server features, etc.)

2.  Remove the `depends_on` blocks for the build-variants you want to run e.g. remove [these lines](https://github.com/mongodb/mongo/blob/ce3261545db4767f18e390c50d59c6530e948655/etc/system_perf.yml#L1007-L10090).

3.  Submit this as your patch-build and then do the usual `set-module` dance (per above).

Here too you can use the same patch-build multiple times like the example above.

