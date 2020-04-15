variable mongod_instance_count      { default = 3 }
variable mongod_ebs_instance_count  { default = 0 }
variable mongod_seeded_ebs_instance_count  { default = 0 }
variable workload_instance_count    { default = 1 }
variable mongos_instance_count          { default = 0 }
variable configsvr_instance_count       { default = 0 }

variable owner      {}

variable workload_instance_type                 {}
variable mongod_instance_type                   { default = "c3.8xlarge" }
variable mongod_ebs_instance_type               { default = "c3.8xlarge" }
variable mongod_seeded_ebs_instance_type        { default = "c3.8xlarge" }
variable mongos_instance_type                   { default = "c3.8xlarge" }
variable configsvr_instance_type                { default = "m5.xlarge" }
variable image                                  { default = "amazon2" }
variable "ssh_user"                             { default = "ec2-user" }

variable with_hyperthreading                    { default = "false" }

# This is the value used to create the placement group itself
variable placement_group                        { default = "" }
# This is the same value (or empty string) for each node type
variable workload_placement_group               { default = "" }
variable mongod_placement_group                 { default = "" }
variable mongod_ebs_placement_group             { default = "" }
variable mongod_seeded_ebs_placement_group      { default = "" }
variable mongos_placement_group                 { default = "" }
variable configsvr_placement_group              { default = "" }

variable cluster_name               {}
variable availability_zone          {}
variable region                     {}
variable expire_on                  { default = "2016-12-31" }

variable mongod_seeded_ebs_snapshot_id     { default = "snap-98bea565" }
variable mongod_seeded_ebs_iops            { default = 240 }

variable mongod_ebs_size            { default = 100 }
variable mongod_ebs_iops            { default = 240 }

variable runner_hostname            { default = "missing" }
variable runner_instance_id         { default = "none" }
variable status                     { default = "idle" }
variable task_id                    { default = "none" }

# These are unused, but for diagnostic purposes it's nice to keep them in the cluster.json file.
# (...which gets printed to stdout.) Terraform 0.12 however requires that all incoming variables are
# declared. Note that these are already written to security.tf, but it cannot take runtime variables.
variable ssh_key_name               {}
variable ssh_key_file               {}


# A placement group causes the cluster nodes to be placed near each other in terms of networking
# It should also help in getting assigned more homogeneous type of hardware
# https://console.aws.amazon.com/support/home?region=us-east-1#/case/?displayId=4495027801
#
# We need to create this here at the top level, because depends_on doesn't work in modules.
# Similarly, we will use -target in terraform destroy to destroy things in right order
resource "aws_placement_group" "dsi_placement_group" {
  name     = var.placement_group
  strategy = "cluster"
}


module "cluster" {
    source = "./modules/cluster"

    # cluster details
    mongod_instance_type    = var.mongod_instance_type
    mongod_instance_count   = var.mongod_instance_count
    workload_instance_count = var.workload_instance_count
    workload_instance_type  = var.workload_instance_type

    # shard special instances
    mongos_instance_type        = var.mongos_instance_type
    mongos_instance_count       = var.mongos_instance_count
    configsvr_instance_type     = var.configsvr_instance_type
    configsvr_instance_count    = var.configsvr_instance_count

    # Instances with 2 EBS disks attached
    mongod_ebs_instance_type    = var.mongod_ebs_instance_type
    mongod_ebs_instance_count   = var.mongod_ebs_instance_count
    mongod_ebs_iops             = var.mongod_ebs_iops
    mongod_ebs_size             = var.mongod_ebs_size

    # Seeded EBS instance support
    mongod_seeded_ebs_instance_type    = var.mongod_seeded_ebs_instance_type
    mongod_seeded_ebs_instance_count   = var.mongod_seeded_ebs_instance_count
    mongod_seeded_ebs_iops             = var.mongod_seeded_ebs_iops
    mongod_seeded_ebs_snapshot_id      = var.mongod_seeded_ebs_snapshot_id

    image                              = var.image
    ssh_user                           = var.ssh_user

    workload_placement_group           = var.workload_placement_group
    mongod_placement_group             = var.mongod_placement_group
    mongod_ebs_placement_group         = var.mongod_ebs_placement_group
    mongod_seeded_ebs_placement_group  = var.mongod_seeded_ebs_placement_group
    mongos_placement_group             = var.mongos_placement_group
    configsvr_placement_group          = var.configsvr_placement_group

    topology            = var.cluster_name

    # AWS details
    availability_zone   = var.availability_zone
    region              = var.region
    expire_on           = var.expire_on

    owner               = var.owner

    key_file            = var.key_file
    key_name            = var.key_name

    runner_hostname     = var.runner_hostname
    runner_instance_id  = var.runner_instance_id
    status              = var.status
    task_id             = var.task_id

    with_hyperthreading = var.with_hyperthreading
}
