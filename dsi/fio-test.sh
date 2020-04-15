#!/usr/bin/env sh

set -e

HOSTNAME=$1

# Heuristic to detect Atlas clusters from the hostname, which have the form
# *.mongodb-dev.net or *.mongodb.net
domain=$(echo "$HOSTNAME" | cut -d. -f2)
tld=$(echo "$HOSTNAME" | cut -d. -f3)

if [ "$tld" == "net" ]
then
  if [ "$domain" == "mongodb-dev" -o "$domain" == "mongodb" ]
  then
    echo "Detected Atlas cluster, skipping fio."
    exit 0
  fi
fi

scp -o StrictHostKeyChecking=no fio.ini "${HOSTNAME}":./
ssh -A "${HOSTNAME}" "mkdir -p ./data/fio && fio --output-format=json --output=fio.json fio.ini"
scp "${HOSTNAME}":./fio.json .
ssh -A "${HOSTNAME}" "tar czvf fio_results.tgz fio*.log"
scp "${HOSTNAME}":./fio_results.tgz .
ssh -A "${HOSTNAME}" "rm -r data/fio fio_results.tgz fio*.log"