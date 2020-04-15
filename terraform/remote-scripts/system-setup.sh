#!/bin/bash
#
# System setup script (run on each instance after launch by terraform)
#
# ./system-setup.sh [WITH_EBS] [WITH_HT]
#
# WITH_EBS:       "with_ebs" or "with_seeded_ebs" to add EBS partition
# WITH_HT:        "yes" to leave hyper-threaded cores online. Default is to disable ht.
#
WITH_EBS="${1:-false}"
WITH_HT="${2:-false}"

# set -e

sudo yum update -y
sudo yum remove -y iptables iptables-libs
sudo yum -y install tmux git wget sysstat dstat perf fio xfsprogs krb5-libs openldap-devel cyrus-sasl cyrus-sasl-devel cyrus-sasl-gssapi cyrus-sasl-lib cyrus-sasl-md5 net-snmp net-snmp-devel net-snmp-libs net-snmp-utils python2-pip numactl iproute-tc

# Make sure we actually have pip
if ! [ -x "$(command -v pip)" ]; then
    echo "pip not installed. Installing now"
    curl "https://bootstrap.pypa.io/get-pip.py" -o "get-pip.py"
    python get-pip.py
fi

disable_hyperthreading() {
    if [[ "${WITH_HT}" == "yes" ]]; then
        return
    fi

    # Disable hyperthreading.
    #
    # This involves turning off cpus tied to extra threads.  Cores is the
    # total number of real cores per socket in the system. Cpus is the
    # number of cpus linux thinks it has. We want to leave on one cpu per
    # real core.  On existing systems, cpus 0 through $total_cores all map
    # to different physical cores. We are turning off all cpus beyond
    # that.

    cores=$(lscpu | grep -E Core | grep -E socket | cut -d : -f 2)
    sockets=$(lscpu | grep -E Socket |  cut -d : -f 2)
    cpus=$(lscpu | grep -E "CPU\(s\)" | head -1 | cut -d : -f 2)
    total_cores=$((cores*sockets))
    for i in $(seq $total_cores "$cpus"); do echo 0 | sudo tee /sys/devices/system/cpu/cpu"$i"/online; done
}

prepare_disk() {
    # Mount $1 at $2, if $3 == "true" (default), also format (XFS)
    disk=$1;  shift;
    mount_path=$1; shift;
    format="${1:-yes}"

    sudo mkdir -p "$mount_path"
    sudo umount "$disk"
    if [[ "$format" == "yes" ]]; then
        sudo mkfs.xfs -f "$disk"
    fi
    # Set noatime, readahead: https://docs.mongodb.com/manual/administration/production-notes/#recommended-configuration
    sudo mount "$disk" "$mount_path" -o noatime
    sudo blockdev --setra 32 "$disk"
    sudo chmod 777 "$mount_path"
    sudo chown -R ec2-user:ec2-user "$mount_path"
}

create_required_directories() {
    sudo chmod 777 /data
    mkdir -p /data/mci
    mkdir -p /data/tmp
    # Tests are designed to access things with relative paths, which on EC2 is relative to $HOME.
    ln -s /data ~/data
}

##
# Prepare Disks
##
if [[ -e /dev/xvdc ]]; then
    prepare_disk "/dev/xvdc" "/media/ephemeral0"
fi
if [[ -e /dev/xvdd ]]; then
    prepare_disk "/dev/xvdd" "/media/ephemeral1"
fi

# Prepare empty EBS volume
if [ "${WITH_EBS}" == "with_ebs" ]; then
    if [[ -e /dev/xvde ]]; then
        prepare_disk "/dev/xvde" "/media/ebs"
    fi
    if [[ -e /dev/xvdf ]]; then
        prepare_disk "/dev/xvdf" "/media/ebs2"
    fi
    if [[ -e /dev/nvme1n1 ]]; then
        prepare_disk "/dev/nvme1n1" "/media/ebs"
    fi
    if [[ -e /dev/nvme2n1 ]]; then
        prepare_disk "/dev/nvme2n1" "/media/ebs2"
    fi
    sudo ln -s /media/ebs /data
# Will not format disk for seeded EBS partition.
elif [ "${WITH_EBS}" == "with_seeded_ebs" ]; then
    prepare_disk "/dev/xvde" "/media/ebs" "no"
    prepare_disk "/dev/xvdf" "/media/ebs2"
    sudo ln -s /media/ebs /data
# Default to SSD only instance
else
    if [[ -e /dev/nvme0n1 ]]; then
        prepare_disk "/dev/nvme0n1" "/media/ephemeral0"
        prepare_disk "/dev/nvme1n1" "/media/ephemeral1"
    fi
    if [[ -e /media/ephemeral0 ]]; then
        sudo ln -s /media/ephemeral0 /data
    else
        echo
        echo
        echo "WARNING: Did not find any mounted disks for /data. Creating /data on root partition."
        echo
        echo
        sudo mkdir -p /data
    fi
fi


##
# Set up directories
##
create_required_directories

##
# Disable Hyperthreading
##
disable_hyperthreading


##
# Run FIO to warm up disk
##
if [[ "${WITH_EBS}" == "with_seeded_ebs" ]]; then
    # Warm up EBS partition in order to get better read performance. This is due to this EBS
    # is created via snapshot.
    # See doc: http://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ebs-initialize.html
    sudo fio --filename=/dev/xvde --rw=randread --bs=128k --iodepth=32 --ioengine=libaio --direct=1 --name=volume-initialize --status-interval=300
fi


echo 'ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQCmHUZLsuGvNUlCiaZ83jS9f49S0plAtCH19Z2iATOYPH1XE2T8ULcHdFX2GkYiaEqI+fCf1J1opif45sW/5yeDtIp4BfRAdOu2tOvkKvzlnGZndnLzFKuFfBPcysKyrGxkqBvdupOdUROiSIMwPcFgEzyLHk3pQ8lzURiJNtplQ82g3aDi4wneLDK+zuIVCl+QdP/jCc0kpYyrsWKSbxi0YrdpG3E25Q4Rn9uom58c66/3h6MVlk22w7/lMYXWc5fXmyMLwyv4KndH2u3lV45UAb6cuJ6vn6wowiD9N9J1GS57m8jAKaQC1ZVgcZBbDXMR8fbGdc9AH044JVtXe3lT shardtest@test.mongo' | tee -a ~/.ssh/authorized_keys


# Install programs
cd ~/data/tmp

install_java() {
    curl -O --retry 10 -fsS \
      https://s3-us-west-2.amazonaws.com/dsi-donot-remove/java/jdk-8u162-linux-x64.rpm
    sudo rpm -i jdk-8u162-linux-x64.rpm
    sudo /usr/sbin/alternatives --install /usr/bin/java java /usr/java/jdk1.8.0_162/bin/java 20000
}

# This is temporary until all of genny's metrics parsing and uploading is moved
# off of genny itself (in the workload client) and into the DSI runner (evergreen)
# machine.
install_curator() {
    curl -o curator.tar.gz --retry 10 -LsS https://s3.amazonaws.com/boxes.10gen.com/build/curator/curator-dist-rhel70-ac7e518bd8c8d18188330413db79704f9f0eb8a3.tar.gz
    tar xvf curator.tar.gz

    sudo cp ./curator /usr/local/bin/curator
    curator --version
}

install_java
install_curator

exit 0
