#!/bin/bash
# A6700 (firmware 2.00): put back the XAVC S-I 4K step (run it before open_gate_putback).
# WRITES into the camera's memory (not firmware, not settings). A cold boot (battery out for 10 seconds) returns it to stock; whether the power switch alone does on the A6700 is not known.
cd "$(dirname "$0")" || exit 1
exec "$PWD/run.sh" apply si-putback "$@"
