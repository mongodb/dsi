#!/usr/bin/env bash
# Surprise! We're actually bash. This is for backward-compatibility
# TODO: kill with SERVER-46464.

set -eou pipefail



MYDIR=$(dirname "$0")
pushd "$MYDIR" >/dev/null
    MYDIR=$(pwd -P)
popd >/dev/null

"$MYDIR/../run-dsi" analysis "$@"

