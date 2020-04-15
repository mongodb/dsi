#!/bin/bash
# fail early
set -eou pipefail

BUILDIR=$(dirname $0)
source ${BUILDIR}/test-common.sh

# Perform pylint with the correct .pylintrc file.
# Please convert this to python if it becomes any more complex!

# Put new directories into one of the existing _paths arrays below
# Note we only do '-maxdepth 1' so subdirectories won't be traversed
# (this is how we have dsi/* and dsi/tests/* use different .pylintrc files).

# this set of directories uses /.pylintrc
top_paths=(
    .
    aws_tools
    dsi
    dsi/common
    dsi/evergreen
)

# this set of directories uses /dsi/tests/.pylintrc
test_paths=(
    dsi/tests
    testscripts
    test_lib
)

run_pylint() {
    # first arg is rcfile
    # rest is directories to call `find` on
    local rcfile="$1"
    shift
    local files=("$@")
    set -x
    # `-j N` runs N parallel pylint procs. Set N to 0 to get # of cores
    run_test pylint -j 0 --rcfile "$rcfile" \
        $(find "${files[@]}" -maxdepth 1 -name '*.py')
    set +x
}

failed=0
run_pylint .pylintrc "${top_paths[@]}"
run_pylint dsi/tests/.pylintrc "${test_paths[@]}"

exit $failed
