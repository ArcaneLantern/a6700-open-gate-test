#!/bin/bash
# A6700 (firmware 2.00): TEST 2: test 1 plus the output size 3840x2560 (L13 + L5 + L16), then one read-only session. Expected: a steady picture; a recording may stop (the encoder is still set for 2,160 rows). NOT YET RUN ON AN A6700 by this project (a contributed port; its author reports that it works).
# WRITES into the camera's memory (not firmware, not settings). A cold boot (battery out for 10 seconds) returns it to stock; whether the power switch alone does on the A6700 is not known.
cd "$(dirname "$0")" || exit 1
exec "$PWD/run.sh" apply test2 "$@"
