output "private_member_ip" {
  value = "${module.cluster.private_mongod_seeded_ebs_ip} ${module.cluster.private_member_ip} ${module.cluster.private_mongod_ebs_ip}"
}

output "public_member_ip" {
  value = "${module.cluster.public_mongod_seeded_ebs_ip} ${module.cluster.public_member_ip} ${module.cluster.public_mongod_ebs_ip}"
}

output "private_ip_mc" {
  value = module.cluster.private_ip_mc
}

output "public_ip_mc" {
  value = module.cluster.public_ip_mc
}

output "total_count" {
  value = module.cluster.total_count
}
output "private_mongos_ip" {
  value = module.cluster.private_mongos_ip
}

output "public_mongos_ip" {
  value = module.cluster.public_mongos_ip
}

output "private_config_ip" {
  value = module.cluster.private_configsvr_ip
}

output "public_config_ip" {
  value = module.cluster.public_configsvr_ip
}

output "public_all_host_ip" {
  value = "${module.cluster.public_mongod_seeded_ebs_ip} ${module.cluster.public_mongod_ebs_ip} ${module.cluster.public_member_ip} ${module.cluster.public_mongos_ip} ${module.cluster.public_configsvr_ip}"
}

output "private_all_host_ip" {
  value = "${module.cluster.private_mongod_seeded_ebs_ip} ${module.cluster.private_mongod_ebs_ip} ${module.cluster.private_member_ip} ${module.cluster.private_mongos_ip} ${module.cluster.private_configsvr_ip}"
}
