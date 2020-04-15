#!/bin/bash

TERRAFORM="${TERRAFORM:-./terraform}"

# Update the tags to mark the cluster as idle
$TERRAFORM apply -var-file=cluster.json --var 'status=idle' -auto-approve
