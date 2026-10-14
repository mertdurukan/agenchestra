@echo off
rem Kanca sarmalayicisi: python3 -> python -> py -3 sirasiyla yorumlayici bulur, hook.py calistirir.
rem stdin ve cikis kodu aynen gecer. WindowsApps altindaki Store kisayollari (calismayan stub) atlanir.
rem Kullanim: hook_python.cmd <OlayAdi>
setlocal
set "HOOK=%~dp0..\scripts\hook.py"
set "PYEXE="
for %%N in (python3 python) do if not defined PYEXE call :bul %%N
if defined PYEXE goto calistir
where py >nul 2>nul
if errorlevel 1 goto yok
py -3 "%HOOK%" %*
exit /b
:calistir
"%PYEXE%" "%HOOK%" %*
exit /b
:yok
echo orkestra hook_python: python3/python/py bulunamadi 1>&2
exit /b 127
:bul
for /f "delims=" %%P in ('where %1 2^>nul') do if not defined PYEXE echo %%P| findstr /i /c:"WindowsApps" >nul || set "PYEXE=%%P"
exit /b 0
