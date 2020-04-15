#!/bin/bash

# Run all tests
if ! [ -f config.yml ]; then
    echo "The tests require an evergreen/github config file called config.yml in the repo root."
    echo "See /example_config.yml for an example."
    exit 1
fi

function run_test {
    "$@"
    if [ $? -ne 0 ]; then
        ((failed++))
        echo "DSI TEST FAILED" "$@"
    fi
}


