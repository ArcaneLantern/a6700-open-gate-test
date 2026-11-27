@echo off
rem A6700 (firmware 2.00): DIAGNOSTIC 1, NOT A STATE TO SHOOT WITH (for open gate itself run open_gate_apply): raw write buffer and sensor side only (L13 + L5), then one read-only session. It shows whether the sensor takes the taller window. Expected: a steady picture and 3840x2160 clips holding the 3:2 window squeezed. A tester's A6700 gave this result on 2026-11-27.
rem WRITES into the camera's memory (not firmware, not settings). A cold boot (battery out for 10 seconds) returns it to stock; whether the power switch alone does on the A6700 is not known.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Python environment missing: run setup.cmd first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -I -B "tools\camera_tests\CT6_memory_read_check\a6700_apply.py" test1 %*
echo.
pause
