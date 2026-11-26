@echo off
rem A6700 (firmware 2.00): OPTIONAL, after open_gate_apply, open_gate_contributed_apply or open_gate_50p_apply: in-camera playback of 3840x2560 clips (three steps that change 7 instructions and 1 table word of av-cam.bin in memory, each refusing unless the caches can be made to fetch them, and one instruction of libmpr.so). NOT YET RUN ON AN A6700 by this project (a contributed port; its author reports that it works).
rem WRITES into the camera's memory (not firmware, not settings). A cold boot (battery out for 10 seconds) returns it to stock; whether the power switch alone does on the A6700 is not known.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Python environment missing: run setup.cmd first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -I -B "tools\camera_tests\CT6_memory_read_check\a6700_apply.py" playback %*
echo.
pause
