@echo off
rem Abre o Brawl SENAI. Usa o pygame instalado na .venv do projeto.
cd /d "%~dp0"
set PYTHONPATH=%~dp0.venv\Lib\site-packages
python -m brawl %*
if errorlevel 1 pause
