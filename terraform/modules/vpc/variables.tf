
variable "amis" {
    type = map(string)
    default = {

        #
        # AMIs last updated 2020-03-06
        #
        # "Amazon Linux 2 - 7/18/2019 Update"
        # https://aws.amazon.com/amazon-linux-2/release-notes/
        #
        # Get updated AMI IDs at the below URLs.
        # - Search for "Amazon Linux 2 AMI (HVM), SSD Volume Type"
        # - Ensure you copy the "64-bit x86" version.
        #
        # Refer to this PR for other things to consider changing:
        # https://github.com/10gen/dsi/pull/189
        #

        # https://us-west-2.console.aws.amazon.com/ec2/v2/home?region=us-west-2#LaunchInstanceWizard:
        "us-west-2-amazon2" = "ami-0e8c04af2729ff1bb"
        # https://us-west-1.console.aws.amazon.com/ec2/v2/home?region=us-west-1#LaunchInstanceWizard:
        "us-west-1-amazon2" = "ami-01c94064639c71719"
        # https://us-east-1.console.aws.amazon.com/ec2/v2/home?region=us-east-1#LaunchInstanceWizard:
        "us-east-1-amazon2" = "ami-0a887e401f7654935"
        # https://eu-west-1.console.aws.amazon.com/ec2/v2/home?region=eu-west-1#LaunchInstanceWizard:
        "eu-west-1-amazon2" = "ami-099a8245f5daa82bf"

        # CENTOS AMI from Akshay
        "us-east-1-centos7" = "ami-0af2cea0881faa972"
    }
}

variable "private_ips" {
    type = map(string)
    default = {
        "workloadclient0" = "10.2.0.10"
        "workloadclient1" = "10.2.0.11"
        "workloadclient2" = "10.2.0.12"
        "workloadclient3" = "10.2.0.13"
        "workloadclient4" = "10.2.0.14"
        "workloadclient5" = "10.2.0.15"
        "workloadclient6" = "10.2.0.16"
        "workloadclient7" = "10.2.0.17"
        "workloadclient8" = "10.2.0.18"
        "workloadclient9" = "10.2.0.19"


        "configsvr0" = "10.2.0.71"
        "configsvr1" = "10.2.0.72"
        "configsvr2" = "10.2.0.73"


        "mongos0" = "10.2.0.80"
        "mongos1" = "10.2.0.81"
        "mongos2" = "10.2.0.82"
        "mongos3" = "10.2.0.83"
        "mongos4" = "10.2.0.84"
        "mongos5" = "10.2.0.85"
        "mongos6" = "10.2.0.86"
        "mongos7" = "10.2.0.87"
        "mongos8" = "10.2.0.88"
        "mongos9" = "10.2.0.89"
        "mongos10" = "10.2.0.90"
        "mongos11" = "10.2.0.91"
        "mongos12" = "10.2.0.92"
        "mongos13" = "10.2.0.93"
        "mongos14" = "10.2.0.94"
        "mongos15" = "10.2.0.95"
        "mongos16" = "10.2.0.96"
        "mongos17" = "10.2.0.97"
        "mongos18" = "10.2.0.98"
        "mongos19" = "10.2.0.99"


        "mongod0" = "10.2.0.100"
        "mongod1" = "10.2.0.101"
        "mongod2" = "10.2.0.102"
        "mongod3" = "10.2.0.103"
        "mongod4" = "10.2.0.104"
        "mongod5" = "10.2.0.105"
        "mongod6" = "10.2.0.106"
        "mongod7" = "10.2.0.107"
        "mongod8" = "10.2.0.108"
        "mongod9" = "10.2.0.109"
        "mongod10" = "10.2.0.110"
        "mongod11" = "10.2.0.111"
        "mongod12" = "10.2.0.112"
        "mongod13" = "10.2.0.113"
        "mongod14" = "10.2.0.114"
        "mongod15" = "10.2.0.115"
        "mongod16" = "10.2.0.116"
        "mongod17" = "10.2.0.117"
        "mongod18" = "10.2.0.118"
        "mongod19" = "10.2.0.119"
        "mongod20" = "10.2.0.120"
        "mongod21" = "10.2.0.121"
        "mongod22" = "10.2.0.122"
        "mongod23" = "10.2.0.123"
        "mongod24" = "10.2.0.124"
        "mongod25" = "10.2.0.125"
        "mongod26" = "10.2.0.126"
        "mongod27" = "10.2.0.127"
        "mongod28" = "10.2.0.128"
        "mongod29" = "10.2.0.129"
        "mongod30" = "10.2.0.130"
        "mongod31" = "10.2.0.131"
        "mongod32" = "10.2.0.132"
        "mongod33" = "10.2.0.133"
        "mongod34" = "10.2.0.134"
        "mongod35" = "10.2.0.135"
        "mongod36" = "10.2.0.136"
        "mongod37" = "10.2.0.137"
        "mongod38" = "10.2.0.138"
        "mongod39" = "10.2.0.139"
        "mongod40" = "10.2.0.140"
        "mongod41" = "10.2.0.141"
        "mongod42" = "10.2.0.142"
        "mongod43" = "10.2.0.143"
        "mongod44" = "10.2.0.144"
        "mongod45" = "10.2.0.145"
        "mongod46" = "10.2.0.146"
        "mongod47" = "10.2.0.147"
        "mongod48" = "10.2.0.148"
        "mongod49" = "10.2.0.149"
        "mongod50" = "10.2.0.150"
        "mongod51" = "10.2.0.151"
        "mongod52" = "10.2.0.152"
        "mongod53" = "10.2.0.153"
        "mongod54" = "10.2.0.154"
        "mongod55" = "10.2.0.155"
        "mongod56" = "10.2.0.156"
        "mongod57" = "10.2.0.157"
        "mongod58" = "10.2.0.158"
        "mongod59" = "10.2.0.159"


        "mongod_seeded_ebs0" = "10.2.0.190"
        "mongod_seeded_ebs1" = "10.2.0.191"
        "mongod_seeded_ebs2" = "10.2.0.192"
        "mongod_seeded_ebs3" = "10.2.0.193"
        "mongod_seeded_ebs4" = "10.2.0.194"
        "mongod_seeded_ebs5" = "10.2.0.195"


        "mongod_ebs0" = "10.2.0.200"
        "mongod_ebs1" = "10.2.0.201"
        "mongod_ebs2" = "10.2.0.202"
        "mongod_ebs3" = "10.2.0.203"
        "mongod_ebs4" = "10.2.0.204"
        "mongod_ebs5" = "10.2.0.205"
        "mongod_ebs6" = "10.2.0.206"
        "mongod_ebs7" = "10.2.0.207"
        "mongod_ebs8" = "10.2.0.208"
        "mongod_ebs9" = "10.2.0.209"
        "mongod_ebs10" = "10.2.0.210"
        "mongod_ebs11" = "10.2.0.211"
        "mongod_ebs12" = "10.2.0.212"
        "mongod_ebs13" = "10.2.0.213"
        "mongod_ebs14" = "10.2.0.214"
        "mongod_ebs15" = "10.2.0.215"
        "mongod_ebs16" = "10.2.0.216"
        "mongod_ebs17" = "10.2.0.217"
        "mongod_ebs18" = "10.2.0.218"
        "mongod_ebs19" = "10.2.0.219"
        "mongod_ebs20" = "10.2.0.220"
        "mongod_ebs21" = "10.2.0.221"
        "mongod_ebs22" = "10.2.0.222"
        "mongod_ebs23" = "10.2.0.223"
        "mongod_ebs24" = "10.2.0.224"
        "mongod_ebs25" = "10.2.0.225"
        "mongod_ebs26" = "10.2.0.226"
        "mongod_ebs27" = "10.2.0.227"
        "mongod_ebs28" = "10.2.0.228"
        "mongod_ebs29" = "10.2.0.229"
        "mongod_ebs30" = "10.2.0.230"
        "mongod_ebs31" = "10.2.0.231"
        "mongod_ebs32" = "10.2.0.232"
        "mongod_ebs33" = "10.2.0.233"
        "mongod_ebs34" = "10.2.0.234"
        "mongod_ebs35" = "10.2.0.235"
        "mongod_ebs36" = "10.2.0.236"
        "mongod_ebs37" = "10.2.0.237"
        "mongod_ebs38" = "10.2.0.238"
        "mongod_ebs39" = "10.2.0.239"
        "mongod_ebs40" = "10.2.0.240"
        "mongod_ebs41" = "10.2.0.241"
        "mongod_ebs42" = "10.2.0.242"
        "mongod_ebs43" = "10.2.0.243"
        "mongod_ebs44" = "10.2.0.244"
        "mongod_ebs45" = "10.2.0.245"
        "mongod_ebs46" = "10.2.0.246"
        "mongod_ebs47" = "10.2.0.247"
        "mongod_ebs48" = "10.2.0.248"
        "mongod_ebs49" = "10.2.0.249"
        "mongod_ebs50" = "10.2.0.250"
        "mongod_ebs51" = "10.2.0.251"
        "mongod_ebs52" = "10.2.0.252"
        "mongod_ebs53" = "10.2.0.253"
        "mongod_ebs54" = "10.2.0.254"
        "mongod_ebs55" = "10.2.0.255"
        "mongod_ebs56" = "10.2.0.256"
    }
}
