#!/bin/bash
# A6700 (firmware 2.00): apply the open-gate state: a 3840x2560 file of the 5952x3876 sensor window in XAVC HS 4K and XAVC S 4K (24p, 25p on PAL), MP4 headers at 3840x2560, and the rear screen at 3:2 (five steps, then one read-only session). NOT YET RUN ON AN A6700 by this project (a contributed port; its author reports that it works).
# WRITES into the camera's memory (not firmware, not settings). A cold boot (battery out for 10 seconds) returns it to stock; whether the power switch alone does on the A6700 is not known.
cd "$(dirname "$0")" || exit 1
exec "$PWD/run.sh" apply apply "$@"
