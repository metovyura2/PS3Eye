@echo off
rem Build PSEyes.exe with PyInstaller (single file, no console) and log the result
rem Usage: tools\build_exe.bat
setlocal
cd /d "%~dp0.."
set ROOT=%CD%
set LOG=%ROOT%\temp\build_exe.log
if not exist "%ROOT%\temp" mkdir "%ROOT%\temp"
echo build started %time%> "%LOG%"

if not exist "%ROOT%\assets\pseyes.ico" python "%ROOT%\assets\make_icon.py" >> "%LOG%" 2>&1

python -m PyInstaller --noconfirm --clean --distpath "%ROOT%\dist" --workpath "%ROOT%\temp\build" --specpath "%ROOT%\temp\build" --name PSEyes --onefile --windowed --icon "%ROOT%\assets\pseyes.ico" --add-data "%ROOT%\assets\pseyes.ico;assets" "%ROOT%\main.py" >> "%LOG%" 2>&1

if exist "%ROOT%\dist\PSEyes.exe" (
  echo EXE OK %time%>> "%LOG%"
) else (
  echo EXE FAILED %time%>> "%LOG%"
)
endlocal
