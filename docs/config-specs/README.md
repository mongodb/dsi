Distributed Performance 2.0 config file format specification
=============================================================

This directory contains files that serve as both an example and a
specification for the configuration files used by DSI modules, as of
Distributed Performance 2.0.

For more context, see https://docs.google.com/document/d/1QdVoSnvoqA1CBQRZNzrDFTJ7REAml3cq4bgWZi9qaPQ/edit#
These files add more detail to that high level specification.

The python library reading these files is found in [dsi/common/config.py](../../dsi/common/config.py).
The unit tests [dsi/tests/test_config.py](../../dsi/tests/test_config.py) can be a useful read too.
The actual config files we use in production can be found under [clusters/*/*.yml](../../clusters/).
(These locations are subject to change, sorry if the links are outdated when you read this.)

A design goal is that these files contain the entire end-to-end configuration for a test run. For
example, a subsection of mongodb_setup.yml is a valid mongod config file.
The mongodb_setup module will copy that section, store it into a new file, and pass to a mongod
process when deploying mongodb.

Conventions
------------

* Keys and values are generally the values mandated by this spec.
* Some values are examples only. For example the prefix "my" is used for user defined values: "myrs0".
* ${module_name.key_name} are variables that can reference the value of another key in the 
  configuration. The library that reads the config files will automatically substitute the
  variables for their values.
* Paths (example: ../keys/aws.pem) are relative to a work directory where the user has cd into 
  before executing the DP2.0 modules. These configuration files also reside in that work directory.
* Values associated with the key 'id' must be unique in a given file, and cannot be equivalent
  to any reserved strings (enumerated in [dsi/common/config.py](../../dsi/common/config.py)).

Empty values (python None)
--------------------------

* Empty values are mostly not allowed.
  * For mongod options such as `fork`, you must specify `true`.
  * Note: To some degree this requirement arises from implementation that reads the config files.
    A None value is interpreted as no value and causes us to lookup the defaults.yml value or
    sometimes can cause an Exception due to calling .get() on a NoneType.
* In `overrides.yml` file empty values are allowed.
  * The interpretation in this case means that this particular value is not overridden, rather
    the value from the regular `MODULE_NAME.yml` file will be used.
  * This is needed for example when overriding a value in a list. Say you want to change the storage
    engine for the 3rd mongod in a replica set. The `overrides.yml` file would then contain:
    `[None, None, { storage : engine : ... }]`
* Note that if the application tries to read a value that doesn't exist, the config library will
  (in python) raise a `KeyError`.

Overview of files
-----------------

* `MODULE_NAME.yml`: The input configuration file for `MODULE_NAME`, such as
  `mongodb_setup.yml`. Note that other modules can use config values from this
  file if needed, but the main context for these config options is the module
  called `module_name`.
* `MODULE_NAME.out.yml`: Output from a module, can be used as input by other
   modules. In practice there's only 1 of these:
   `infrastrucutre_provisioning.out.yml` will contain an ordered list of private
   and public ip addresses assigned to the requested resources.
* `overrides.yml`: Optional file that can specify keys that override
  values from the previous files. Use case is if you want to run a test using
  the standard set of files stored in this repo, but override one config option.
  For example: Give me a regular 3-shard cluster, but one shard should use
  inMemory engine.

A common library [dsi/common/config.py](../../dsi/common/config.py) knows how to read each file in 
the correct order and how to override values when needed. Modules will simply get/set keys in a 
dictionary.

Use cases and requirements
--------------------------

I've tried to think about the following use cases when designing the spec:

* Support current set of variants and tests.
  * There will be a directory with common configurations. Roughly we will need
    * for each variant a set of `infrastructure_provisioning.yml`,
      `system_setup.yml` and `mongodb_setup.yml`.
    * for each task a set of `workload_setup.yml`,
      `test_control.yml` and `analysis.yml`
  * At the beginning of each evergreen task, we copy the relevant ones
    of these files into a working directory (PERF-434). This working directory 
    is what we need to cd into in system_perf.yml.
  * Note: as each module does its work, the working directory is further populated
    by .out.yml files, at most one for each module.

* Support more options than the rather fixed set of variants as of end of 2015
  * Support for specifying arbitrary MongoDB configuration file
  * Support for specifying arbitrary mongo shell commands
  * Support for specifying additional Terraform resources (e.g. EBS disk)
  * Etc...

* Support reconfiguration within a build.
  * For example, we already need to reconfigure mongodb cluster to use
    different storage engine. In this case you could reuse the other
    files, but provide a `overrides.yml` file to override
    the storage engine.
  * How exactly the implementation activates such a changed configuration, is 
    out of scope for this discussion. But a reconfiguration would again use these 
    input files.

* Support reconfigurations during a running test.
  * As a general case this is out of scope for DP2.0.
  * We only support the case like initialsync does currently, where the starting
    point is that all AWS resources exist, and mongod is installed and running
    on all servers, but some additional `rs.add()` or `sh.addShard()` commands
    can be called in the mongo shell during the test.
  * I do believe that this same configuration file spec can be used also for
    such within-test reconfigurations, but the more interesting question is
    how a test can trigger such a reconfiguration to happen. We need some kind
    of API for that.
