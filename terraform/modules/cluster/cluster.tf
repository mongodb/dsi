variable owner                          { default = "perf-terraform-alerts@10gen.com" }
variable topology                       {}
variable runner_hostname                { default = "missing" } # Hostname of the machine using DSI
variable runner_instance_id             { default = "none" }
variable status                         { default = "idle" } #Idle, running
variable task_id                        { default = "none" }

# define instance types
variable mongod_instance_type                   {}
variable mongod_ebs_instance_type               { default = "c3.8xlarge" }
variable mongod_seeded_ebs_instance_type        { default = "c3.8xlarge" }
variable mongos_instance_type                   { default = "c3.4xlarge" }
variable workload_instance_type                 {}
variable configsvr_instance_type                { default = "m3.2xlarge" }
variable image                                  { default = "amazon2" }

# define instance count
variable mongod_instance_count                  { default = 0 }
variable mongod_ebs_instance_count              { default = 0 }
variable mongod_seeded_ebs_instance_count       { default = 0 }
variable mongos_instance_count                  { default = 0 }
variable workload_instance_count                { default = 0 }
variable configsvr_instance_count               { default = 0 }

variable workload_placement_group               { default = "" }
variable mongod_placement_group                 { default = "" }
variable mongod_ebs_placement_group             { default = "" }
variable mongod_seeded_ebs_placement_group      { default = "" }
variable mongos_placement_group                 { default = "" }
variable configsvr_placement_group              { default = "" }


# AWS details
variable region                         {}
variable availability_zone              {}
variable key_file                       {}
variable key_name                       {}
variable ssh_user                       { default = "ec2-user" }

variable expire_on                      { default = "2016-12-31" }

# variables EBS support
variable mongod_ebs_size                       { default = 100 }
variable mongod_ebs_iops                       { default = 1500 }

# variable for seeded_ebs
variable mongod_seeded_ebs_snapshot_id         { default = "" }
variable mongod_seeded_ebs_iops                { default = 1500 }
variable with_hyperthreading                   { default = "false" }

# define VPC and related network resources
module "VPC" {
    source = "../vpc"

    # parameter for module
    topology            = var.topology
    availability_zone   = var.availability_zone
    owner               = var.owner
    expire_on           = var.expire_on
    runner_hostname     = var.runner_hostname
    runner_instance_id  = var.runner_instance_id
    status              = var.status
    task_id             = var.task_id
}

# AWS instance with placement group for mongod
module "mongod_instance" {
    source = "../ec2_instance"

    # parameters for module
    instance_type       = var.mongod_instance_type
    image               = var.image
    ssh_user            = var.ssh_user
    instance_count      = var.mongod_instance_count
    with_hyperthreading = var.with_hyperthreading
    subnet_id           = module.VPC.aws_subnet_id
    key_file            = var.key_file
    security_groups     = module.VPC.aws_security_group_id
    availability_zone   = var.availability_zone
    region              = var.region
    placement_group     = var.mongod_placement_group
    key_name            = var.key_name
    owner               = var.owner
    expire_on           = var.expire_on
    provisioner_file    = "system-setup.sh"
    topology            = var.topology
    type                = "mongod"
    runner              = var.runner_hostname
    runner_instance_id  = var.runner_instance_id
    status              = var.status
    task_id             = var.task_id
}

# AWS instance with placement group, and EBS volume for mongod
module "mongod_ebs_instance" {
    source = "../ec2_ebs_instance"

    # parameters for module
    instance_type       = var.mongod_ebs_instance_type
    image               = var.image
    ssh_user            = var.ssh_user
    instance_count      = var.mongod_ebs_instance_count
    with_hyperthreading = var.with_hyperthreading
    subnet_id           = module.VPC.aws_subnet_id
    key_file            = var.key_file
    security_groups     = module.VPC.aws_security_group_id
    availability_zone   = var.availability_zone
    region              = var.region
    placement_group     = var.mongod_ebs_placement_group
    key_name            = var.key_name
    owner               = var.owner
    expire_on           = var.expire_on
    provisioner_file    = "system-setup.sh"
    topology            = var.topology
    type                = "mongod_ebs"
    runner              = var.runner_hostname
    runner_instance_id  = var.runner_instance_id
    status              = var.status
    task_id             = var.task_id
    ebs_size            = var.mongod_ebs_size
    ebs_iops            = var.mongod_ebs_iops
}

# AWS instance with placement group, and seeded EBS volume for mongod
module "mongod_seeded_ebs_instance" {
    source = "../ec2_seeded_ebs_instance"

    # parameters for module
    instance_type           = var.mongod_seeded_ebs_instance_type
    image                   = var.image
    ssh_user                = var.ssh_user
    instance_count          = var.mongod_seeded_ebs_instance_count
    with_hyperthreading     = var.with_hyperthreading
    subnet_id               = module.VPC.aws_subnet_id
    key_file                = var.key_file
    security_groups         = module.VPC.aws_security_group_id
    availability_zone       = var.availability_zone
    region              = var.region
    placement_group         = var.mongod_seeded_ebs_placement_group
    key_name                = var.key_name
    owner                   = var.owner
    expire_on               = var.expire_on
    provisioner_file        = "system-setup.sh"
    topology                = var.topology
    type                    = "mongod_seeded_ebs"
    runner                  = var.runner_hostname
    runner_instance_id      = var.runner_instance_id
    status                  = var.status
    task_id                 = var.task_id
    seeded_ebs_snapshot_id  = var.mongod_seeded_ebs_snapshot_id
    seeded_ebs_iops         = var.mongod_seeded_ebs_iops
    ebs_size                = var.mongod_ebs_size
    ebs_iops                = var.mongod_ebs_iops
}

# AWS instance with placement group for mongos
module "mongos_instance" {
    source = "../ec2_instance"

    # parameters for module
    instance_type       = var.mongos_instance_type
    image               = var.image
    ssh_user            = var.ssh_user
    instance_count      = var.mongos_instance_count
    with_hyperthreading = var.with_hyperthreading
    subnet_id           = module.VPC.aws_subnet_id
    key_file            = var.key_file
    security_groups     = module.VPC.aws_security_group_id
    availability_zone   = var.availability_zone
    region              = var.region
    placement_group     = var.mongos_placement_group
    key_name            = var.key_name
    owner               = var.owner
    expire_on           = var.expire_on
    provisioner_file    = "system-setup.sh"
    topology            = var.topology
    type                = "mongos"
    runner              = var.runner_hostname
    runner_instance_id  = var.runner_instance_id
    status              = var.status
    task_id             = var.task_id
}

# AWS instance with placement group for config server
module "configsvr_instance" {
    source = "../ec2_instance"

    # parameters for module
    instance_type       = var.configsvr_instance_type
    image               = var.image
    ssh_user            = var.ssh_user
    instance_count      = var.configsvr_instance_count
    subnet_id           = module.VPC.aws_subnet_id
    key_file            = var.key_file
    security_groups     = module.VPC.aws_security_group_id
    availability_zone   = var.availability_zone
    region              = var.region
    placement_group     = var.configsvr_placement_group
    key_name            = var.key_name
    owner               = var.owner
    expire_on           = var.expire_on
    provisioner_file    = "system-setup.sh"
    topology            = var.topology
    type                = "configsvr"
    runner              = var.runner_hostname
    runner_instance_id  = var.runner_instance_id
    status              = var.status
    task_id             = var.task_id
}

# AWS instance for workload generator
module "workload_instance" {
    source = "../ec2_instance"

    # parameters for module
    instance_type       = var.workload_instance_type
    image               = var.image
    ssh_user            = var.ssh_user
    instance_count      = var.workload_instance_count
    with_hyperthreading = var.with_hyperthreading
    subnet_id           = module.VPC.aws_subnet_id
    key_file            = var.key_file
    security_groups     = module.VPC.aws_security_group_id
    availability_zone   = var.availability_zone
    region              = var.region
    placement_group     = var.workload_placement_group
    key_name            = var.key_name
    owner               = var.owner
    expire_on           = var.expire_on
    provisioner_file    = "system-setup.sh"
    topology            = var.topology
    type                = "workloadclient"
    runner              = var.runner_hostname
    runner_instance_id  = var.runner_instance_id
    status              = var.status
    task_id             = var.task_id
}
