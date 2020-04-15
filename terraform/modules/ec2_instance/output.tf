output "private_ips" {
  value = join(" ", aws_instance.member.*.private_ip)
}

output "public_ips" {
  value = join(" ", aws_instance.member.*.public_ip)
}
