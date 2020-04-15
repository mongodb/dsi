# input variables
variable topology           {}
variable availability_zone  {}
variable owner              {}
variable expire_on          {}
variable runner_hostname   {} # Hostname of the machine using DSI
variable runner_instance_id {}
variable status             {} # Idle, Running
variable task_id            {}

# constant variables
variable vpc_cidr_block {
    type = string
    default = "10.2.0.0/16"
}

# resource definition
resource "aws_vpc" "main" {
    cidr_block = var.vpc_cidr_block
    enable_dns_support = true
    enable_dns_hostnames = true

    tags = {
        Name               = "dsi-${var.topology}-vpc"
        owner              = var.owner
        expire-on          = var.expire_on
        test_setup         = "dsi"
        test_topology      = var.topology
        runner             = var.runner_hostname
        runner_instance_id = var.runner_instance_id
        status             = var.status
        task_id            = var.task_id
    }
}


resource "aws_internet_gateway" "gw" {
    vpc_id = aws_vpc.main.id
}

resource "aws_subnet" "main" {
    vpc_id = aws_vpc.main.id
    cidr_block = "10.2.0.0/24"
    availability_zone = var.availability_zone

    tags = {
        Name               = "dsi-${var.topology}-subnet"
        owner              = var.owner
        expire-on          = var.expire_on
        test_setup         = "dsi"
        test_topology      = var.topology
        runner             = var.runner_hostname
        runner_instance_id = var.runner_instance_id
        status             = var.status
        task_id            = var.task_id
    }
}

resource "aws_route_table" "r" {
    vpc_id = aws_vpc.main.id
    route {
        cidr_block = "0.0.0.0/0"
        gateway_id = aws_internet_gateway.gw.id
    }

    tags = {
        Name               = "dsi-dsi-routing"
        owner              = var.owner
        expire-on          = var.expire_on
        test_setup         = "dsi"
        test_topology      = var.topology
        runner             = var.runner_hostname
        runner_instance_id = var.runner_instance_id
        status             = var.status
        task_id            = var.task_id
    }
}

resource "aws_route_table_association" "a" {
    subnet_id = aws_subnet.main.id
    route_table_id = aws_route_table.r.id
}

resource "aws_security_group" "default" {
    name = "dsi-${var.topology}-default"
    description = "DSI config for ${var.topology} cluster"
    vpc_id = aws_vpc.main.id

    # SSH access from everywhere.
    ingress {
        from_port = 22
        to_port = 22
        protocol = "tcp"
        cidr_blocks = ["0.0.0.0/0"]
    }

    # mongodb access from VPC.
    ingress {
        from_port = 27016
        to_port = 27019
        protocol = "tcp"
        cidr_blocks = [var.vpc_cidr_block]
    }

    # allow all egress
    egress {
        from_port = 0
        to_port = 0
        protocol = -1
        cidr_blocks = ["0.0.0.0/0"]
    }
}


# output variables
output "aws_subnet_id" { value = aws_subnet.main.id }
output "aws_security_group_id" { value = aws_security_group.default.id }
