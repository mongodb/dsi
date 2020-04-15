#!/bin/bash

BUILDIR=$(dirname $0)

source ${BUILDIR}/test-common.sh

failed=0

run_test ${BUILDIR}/check-format-python.sh
run_test ${BUILDIR}/lint-python.sh
run_test ${BUILDIR}/lint-yml.sh
run_test ${BUILDIR}/run-nosetest.sh
run_test ${BUILDIR}/compare_coverage.py # Depends on run-nosetest.sh

if [ $failed -eq 0 ]; then
    echo "All tests passed"
else
    echo "Tests Failed! Failing tests: $failed"
fi
exit $failed
