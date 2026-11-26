#!/bin/bash
# A6700 (firmware 2.00): apply only the four open-gate steps (raw write buffer, sensor, output size, encoder), without the screen step.
# WRITES into the camera's memory (not firmware, not settings). A cold boot (battery out for 10 seconds) returns it to stock; whether the power switch alone does on the A6700 is not known.
cd "$(dirname "$0")" || exit 1
exec "$PWD/run.sh" apply apply --no-screen "$@"
