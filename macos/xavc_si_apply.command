#!/bin/bash
# A6700 (firmware 2.00): OPTIONAL, after open_gate_apply: XAVC S-I 4K at 24p (25p on PAL), one more encoder step. NOT YET RUN ON AN A6700 by this project (a contributed port; its author reports that it works).
# WRITES into the camera's memory (not firmware, not settings). A cold boot (battery out for 10 seconds) returns it to stock; whether the power switch alone does on the A6700 is not known.
cd "$(dirname "$0")" || exit 1
exec "$PWD/run.sh" apply si "$@"
