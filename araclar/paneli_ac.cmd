@echo off
rem Orkestra HTML canli panelini acar. Kullanim: paneli_ac.cmd [proje klasoru]  (bos: bu klasor)
if not "%~1"=="" cd /d "%~1"
python "%~dp0..\plugins\orkestra\scripts\orkestra.py" panel --ac
if errorlevel 1 pause
