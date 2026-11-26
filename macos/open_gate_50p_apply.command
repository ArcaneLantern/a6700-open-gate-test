#!/bin/bash
# A6700 (firmware 2.00): PAL ONLY, the state the contributor's kit applies on a PAL camera: open gate at 25p and 50p in XAVC HS, S and S-I (the 50p drive mode reads 5612x3732; the contributed encoder design in the place of ours). Cannot be mixed with open_gate_apply. NOT YET RUN ON AN A6700 by this project (a contributed port; its author reports that it works).
# WRITES into the camera's memory (not firmware, not settings). A cold boot (battery out for 10 seconds) returns it to stock; whether the power switch alone does on the A6700 is not known.
cd "$(dirname "$0")" || exit 1
exec "$PWD/run.sh" apply apply50 "$@"
