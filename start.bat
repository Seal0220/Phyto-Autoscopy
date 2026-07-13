@echo off
setlocal EnableExtensions DisableDelayedExpansion

rem This launcher starts the backend and frontend in independent terminals,
rem then exits without supervising either process.
set "ROOT=%~dp0"
set "BACKEND_DIR=%ROOT%backend"
set "FRONTEND_DIR=%ROOT%frontend"
set "ROOT_ENV=%ROOT%.env"
set "BACKEND_HOST=127.0.0.1"
set "BACKEND_PORT=22222"
set "FRONTEND_HOST=127.0.0.1"
set "FRONTEND_PORT=22223"
set "MODE=production"
set "MOCK=0"
set "SETUP=0"
set "BACKEND_PID="
set "FRONTEND_PID="
set "EXIT_CODE=1"

:parse_arguments
if "%~1"=="" goto arguments_ready
if /I "%~1"=="--help" goto usage
if /I "%~1"=="-h" goto usage
if /I "%~1"=="--setup" (
  set "SETUP=1"
  shift
  goto parse_arguments
)
if /I "%~1"=="--mock" (
  set "MOCK=1"
  shift
  goto parse_arguments
)
if /I "%~1"=="--mode" (
  if "%~2"=="" goto usage_error
  if /I "%~2"=="development" (
    set "MODE=development"
    shift
    shift
    goto parse_arguments
  )
  if /I "%~2"=="production" (
    set "MODE=production"
    shift
    shift
    goto parse_arguments
  )
  goto usage_error
)
echo Unknown argument: %~1
goto usage_error

:arguments_ready
if not exist "%BACKEND_DIR%\run.py" (
  echo Missing backend runner: %BACKEND_DIR%\run.py
  goto finish
)
if not exist "%FRONTEND_DIR%\package.json" (
  echo Missing frontend package: %FRONTEND_DIR%\package.json
  goto finish
)
if "%SETUP%"=="1" goto setup_environment

if not exist "%ROOT_ENV%" (
  echo Missing root .env. Run start.bat --setup first.
  goto finish
)

call :require_configured_env PHYTO_AUTOSCOPY_OPERATOR_PASSWORD
if errorlevel 1 goto finish
call :require_configured_env PHYTO_AUTOSCOPY_BFF_TOKEN
if errorlevel 1 goto finish
call :require_configured_env PHYTO_AUTOSCOPY_SESSION_SECRET
if errorlevel 1 goto finish

where powershell.exe >nul 2>&1
if errorlevel 1 (
  echo PowerShell is required to create independent backend and frontend terminals.
  goto finish
)
where npm.cmd >nul 2>&1
if errorlevel 1 (
  echo npm is required to start frontend\.
  goto finish
)

if not exist "%ROOT%.venv\Scripts\python.exe" (
  echo Missing backend virtual environment. Run start.bat --setup first.
  goto finish
)
set "PYTHON=%ROOT%.venv\Scripts\python.exe"

if not exist "%FRONTEND_DIR%\node_modules" (
  echo Missing frontend dependencies. Run start.bat --setup first.
  goto finish
)

call :port_in_use %BACKEND_PORT%
if errorlevel 1 goto backend_port_available
echo Port %BACKEND_PORT% is already in use. Stop the existing backend first.
goto finish

:backend_port_available
call :port_in_use %FRONTEND_PORT%
if errorlevel 1 goto frontend_port_available
echo Port %FRONTEND_PORT% is already in use. Stop the existing frontend first.
goto finish

:frontend_port_available
if /I "%MODE%"=="production" (
  echo Building Next.js frontend...
  pushd "%FRONTEND_DIR%"
  call npm.cmd run build
  if errorlevel 1 (
    popd
    echo Frontend build failed.
    goto finish
  )
  popd
)

set "BACKEND_COMMAND=call "%PYTHON%" "%BACKEND_DIR%\run.py" --host %BACKEND_HOST% --port %BACKEND_PORT%"
if /I "%MODE%"=="development" set "BACKEND_COMMAND=%BACKEND_COMMAND% --reload"
if "%MOCK%"=="1" set "BACKEND_COMMAND=%BACKEND_COMMAND% --mock"

if /I "%MODE%"=="production" (
  set "FRONTEND_COMMAND=call npm.cmd run start"
) else (
  set "FRONTEND_COMMAND=call npm.cmd run dev"
)

call :start_child BACKEND_PID "%BACKEND_DIR%" BACKEND_COMMAND
if not defined BACKEND_PID (
  echo Failed to start backend process.
  goto finish
)
call :start_child FRONTEND_PID "%FRONTEND_DIR%" FRONTEND_COMMAND
if not defined FRONTEND_PID (
  echo Failed to start frontend process.
  goto finish
)

echo Backend:  http://%BACKEND_HOST%:%BACKEND_PORT% ^(private BFF boundary^)
echo Frontend: http://%FRONTEND_HOST%:%FRONTEND_PORT%
echo Backend PID: %BACKEND_PID%
echo Frontend PID: %FRONTEND_PID%
echo Backend and frontend terminals started. The launcher will now close.
goto launch_complete

:setup_environment
if not exist "%ROOT%.env.example" (
  echo Missing environment template: %ROOT%.env.example
  goto finish
)
if not exist "%BACKEND_DIR%\requirements.txt" (
  echo Missing backend requirements: %BACKEND_DIR%\requirements.txt
  goto finish
)

where npm.cmd >nul 2>&1
if errorlevel 1 (
  echo npm is required to install frontend dependencies.
  goto finish
)

if not exist "%ROOT%.venv\Scripts\python.exe" (
  where python >nul 2>&1
  if errorlevel 1 (
    echo Python is required to create the backend virtual environment.
    goto finish
  )
)

if not exist "%ROOT_ENV%" (
  copy /Y "%ROOT%.env.example" "%ROOT_ENV%" >nul
  if errorlevel 1 (
    echo Failed to create root .env.
    goto finish
  )
  echo Created .env from .env.example.
) else (
  echo Root .env already exists; leaving it unchanged.
)

if not exist "%ROOT%.venv\Scripts\python.exe" (
  echo Creating backend virtual environment...
  python -m venv "%ROOT%.venv"
  if errorlevel 1 (
    echo Backend virtual environment creation failed.
    goto finish
  )
) else (
  echo Backend virtual environment already exists; synchronizing dependencies.
)

echo Installing backend dependencies...
call "%ROOT%.venv\Scripts\python.exe" -m pip install -r "%BACKEND_DIR%\requirements.txt"
if errorlevel 1 (
  echo Backend dependency installation failed.
  goto finish
)

echo Installing frontend dependencies...
pushd "%FRONTEND_DIR%"
call npm.cmd install
if errorlevel 1 (
  popd
  echo Frontend dependency installation failed.
  goto finish
)
popd

echo Setup complete. Configure the three private values in .env before starting.
set "EXIT_CODE=0"
goto finish

:usage
echo Usage: start.bat [--setup] [--mock] [--mode development^|production]
echo.
echo   --setup                Create .env and install backend and frontend dependencies.
echo   --mock                 Start FastAPI with mock cameras and motor.
echo   --mode development     Next dev and FastAPI reload.
echo   --mode production      Build Next, then Next start and FastAPI without reload ^(default^).
set "EXIT_CODE=0"
goto finish

:usage_error
echo Usage: start.bat [--setup] [--mock] [--mode development^|production]
set "EXIT_CODE=2"
goto finish

:finish
call :stop_process %BACKEND_PID%
call :stop_process %FRONTEND_PID%
endlocal & exit /b %EXIT_CODE%

:launch_complete
endlocal & exit /b 0

:require_configured_env
findstr /R /C:"^%~1=" "%ROOT_ENV%" >nul
if errorlevel 1 (
  echo Missing %~1 in .env.
  exit /b 1
)
findstr /I /R /C:"^%~1=.*replace-with" /C:"^%~1=.*choose-a-strong" "%ROOT_ENV%" >nul
if not errorlevel 1 (
  echo Replace the placeholder value for %~1 in .env.
  exit /b 1
)
exit /b 0

:port_in_use
netstat -ano -p TCP | findstr /C:":%~1 " | findstr /I /C:"LISTENING" >nul
exit /b %ERRORLEVEL%

:start_child
set "%~1="
set "CHILD_WORKING_DIR=%~2"
set "CHILD_PID_FILE=%TEMP%\phyto-autoscopy-%RANDOM%-%RANDOM%.pid"
powershell.exe -NoProfile -Command "$p = Start-Process -FilePath $env:ComSpec -ArgumentList @('/d', '/s', '/c', $env:%~3) -WorkingDirectory $env:CHILD_WORKING_DIR -PassThru; Set-Content -LiteralPath $env:CHILD_PID_FILE -Value $p.Id"
if exist "%CHILD_PID_FILE%" (
  for /F "usebackq delims=" %%P in ("%CHILD_PID_FILE%") do set "%~1=%%P"
  del /Q "%CHILD_PID_FILE%" >nul 2>&1
)
set "CHILD_WORKING_DIR="
set "CHILD_PID_FILE="
exit /b 0

:stop_process
if "%~1"=="" exit /b 0
taskkill /PID %~1 /T /F >nul 2>&1
exit /b 0
