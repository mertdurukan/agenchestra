@echo off
rem orkestra CLI sarmalayicisi (cmd / PowerShell)
rem Yorumlayici sirasi hook_python.cmd ile ayni: ORKESTRA_PYTHON > python3 > python > py -3 (WindowsApps Store kisayollari atlanir).
setlocal
set "CLI=%~dp0..\scripts\orkestra.py"
if defined ORKESTRA_PYTHON if exist "%ORKESTRA_PYTHON%" (
  "%ORKESTRA_PYTHON%" "%CLI%" %*
  exit /b
)
set "PYEXE="
for %%N in (python3 python) do if not defined PYEXE call :bul %%N
if defined PYEXE goto calistir
where py >nul 2>nul
if errorlevel 1 goto yok
py -3 "%CLI%" %*
exit /b
:calistir
"%PYEXE%" "%CLI%" %*
exit /b
:yok
echo orkestra: python3/python/py bulunamadi (ORKESTRA_PYTHON ile yorumlayici goster) 1>&2
exit /b 127
:bul
for /f "delims=" %%P in ('where %1 2^>nul') do if not defined PYEXE echo %%P| findstr /i /c:"WindowsApps" >nul || set "PYEXE=%%P"
exit /b 0
