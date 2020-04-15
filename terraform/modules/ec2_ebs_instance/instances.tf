# define list of variables
variable "key_file"             {}
variable "key_name"             {}
variable "ssh_user"             { default = "ec2-user" }
variable "instance_type"        {}
variable "image"                { default = "amazon2" }
variable "instance_count"        {}
variable "subnet_id"            {}
variable "owner"                {}
variable "security_groups"      {}
variable "availability_zone"    {}
variable "region"               {}
variable "placement_group"      {}
variable "expire_on"            {}
variable "provisioner_file"     {}
variable "topology"             {}
variable "type"                 {}
variable "runner"               {}
variable "runner_instance_id"   {}
variable "status"               {}
variable "task_id"              {}
variable "ebs_type"             { default = "io1" }
variable "ebs_iops"             { default = 10000 }
variable "ebs_size"             { default = 100 }
variable "with_hyperthreading"  { default = "false" }

# AWS instance with placement group for mongod
resource "aws_instance" "ebs_member" {
    ami                 = lookup(var.amis, format("%s-%s", var.region, var.image))
    instance_type       = var.instance_type
    count               = var.instance_count
    subnet_id           = var.subnet_id
    private_ip          = lookup(var.private_ips, format("%s%s", var.type, count.index))

    connection {
        host = self.public_ip
        # The default username for our AMI
        user            = var.ssh_user
        # The path to your keyfile
        private_key        = file(var.key_file)
    }

    vpc_security_group_ids     = [var.security_groups]

    availability_zone   = var.availability_zone
    placement_group     = var.placement_group
    tenancy             = "dedicated"

    key_name = var.key_name
    tags = {
        Name               = "dsi-${var.topology}-${var.type}-${count.index}"
        owner              = var.owner
        expire-on          = var.expire_on
        test_setup         = "dsi"
        test_topology      = var.topology
        runner             = var.runner
        runner_instance_id = var.runner_instance_id
        status             = var.status
        task_id            = var.task_id
    }

    root_block_device {
        volume_size = 16
    }

    ephemeral_block_device {
        device_name     = "/dev/sdc"
        virtual_name    = "ephemeral0"
    }
    ephemeral_block_device {
        device_name     = "/dev/sdd"
        virtual_name    = "ephemeral1"
    }

    ebs_block_device {
        device_name             = "/dev/sde"
        volume_type             = var.ebs_type
        iops                    = var.ebs_iops
        volume_size             = var.ebs_size
        delete_on_termination   = true
        encrypted               = true
    }

    ebs_block_device {
        device_name             = "/dev/sdf"
        volume_type             = var.ebs_type
        iops                    = var.ebs_iops
        volume_size             = var.ebs_size
        delete_on_termination   = true
        encrypted               = true
    }

    associate_public_ip_address = true

    # We run a remote provisioner on the instance after creating it.
    provisioner "file" {
        connection {
            timeout = "10m"
        }
        source      = format("./remote-scripts/%s", var.provisioner_file)
        destination = "/tmp/provision.sh"
    }

    provisioner "remote-exec" {
        connection {
            timeout = "10m"
        }
        inline = [
            "chmod +x /tmp/provision.sh",
            "/tmp/provision.sh with_ebs ${var.with_hyperthreading}"
        ]
    }
}
