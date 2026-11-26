#!/bin/bash
# A6700 (firmware 2.00): A TEST OF OUR OWN: open_gate_apply with the exact 3:2 sensor window (5952x3968 from row 94) in the place of the contributed one (5952x3876), whose picture is 2.4 percent too tall. Nobody has run this window on an A6700. Cannot be mixed with the other applies. NOT YET RUN ON AN A6700 by this project.
# WRITES into the camera's memory (not firmware, not settings). A cold boot (battery out for 10 seconds) returns it to stock; whether the power switch alone does on the A6700 is not known.
cd "$(dirname "$0")" || exit 1
exec "$PWD/run.sh" apply apply32 "$@"
