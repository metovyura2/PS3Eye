@echo off
rem ============================================================
rem  Запуск PSEyes (из исходников) — просто двойной клик по файлу
rem ============================================================
setlocal
cd /d "%~dp0"

rem 1. Ищем Python: сначала launcher py, потом python из PATH
set PY=
where py >nul 2>nul && set PY=py
if not defined PY (
  where python >nul 2>nul && set PY=python
)
if not defined PY (
  echo [ОШИБКА] Python не найден.
  echo Установите Python 3.11+ с https://www.python.org/downloads/windows/
  echo и поставьте галочку "Add python.exe to PATH" при установке.
  echo.
  pause
  exit /b 1
)

rem 2. Проверяем зависимости (PyQt6, opencv, numpy)
%PY% -c "import PyQt6, cv2, numpy" >nul 2>nul
if errorlevel 1 (
  echo Первый запуск: устанавливаю зависимости из requirements.txt...
  echo.
  %PY% -m pip install --upgrade pip
  %PY% -m pip install -r requirements.txt
  if errorlevel 1 (
    echo.
    echo [ОШИБКА] Не удалось установить зависимости.
    echo Проверьте интернет и выполните вручную:
    echo     %PY% -m pip install -r requirements.txt
    echo.
    pause
    exit /b 1
  )
)

rem 3. Предупреждение, если нет ffmpeg (нужен для сборки MP4)
if not exist "C:\ffmpeg\bin\ffmpeg.exe" (
  where ffmpeg >nul 2>nul
  if errorlevel 1 (
    echo [ВНИМАНИЕ] ffmpeg не найден. Съёмка кадров будет работать,
    echo но собрать MP4 не получится. См. README.md, раздел "Требования".
    echo.
  )
)

rem 4. Запуск приложения
echo Запуск PSEyes...
start "" /wait %PY% main.py
if errorlevel 1 (
  echo.
  echo [ОШИБКА] Приложение завершилось с ошибкой (код %errorlevel%).
  echo Журнал: temp\pseyes.log
  pause
)
endlocal
