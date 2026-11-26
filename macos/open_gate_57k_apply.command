#!/bin/bash
# A6700 (firmware 2.00): the 5.76K state: 5760x3840 files at 24p (25p on PAL), 260 Mbps. Cannot be mixed with open_gate_apply; 5.76K clips do not play in the camera. NOT YET RUN ON AN A6700 by this project (a contributed port; its author reports that it works).
# WRITES into the camera's memory (not firmware, not settings). A cold boot (battery out for 10 seconds) returns it to stock; whether the power switch alone does on the A6700 is not known.
cd "$(dirname "$0")" || exit 1
exec "$PWD/run.sh" apply apply57 "$@"
