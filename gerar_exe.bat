@echo off
setlocal
chcp 65001 >nul
echo === Baixador de Videos: gerando o .exe ===

rem Procura um Python de verdade (o "py" vem com o instalador do python.org).
set PY=
py -3 --version >nul 2>&1 && set PY=py -3
if not defined PY (
  python --version >nul 2>&1 && set PY=python
)
if not defined PY (
  echo.
  echo Nao encontrei o Python neste computador.
  echo 1. Baixe em https://www.python.org/downloads/ e instale.
  echo 2. Na primeira tela do instalador, marque "Add python.exe to PATH".
  echo 3. Rode este arquivo de novo.
  echo.
  echo Alternativa sem instalar nada: use o workflow do GitHub ^(veja o README^).
  goto fim
)

%PY% -m pip install -r requirements.txt pyinstaller || goto erro
set EXTRA=
if exist apoio.json set EXTRA=--add-data "apoio.json;."
%PY% -m PyInstaller --noconfirm --clean --onefile --windowed --name Baixador ^
  --add-data "web;web" %EXTRA% --collect-all yt_dlp main.py || goto erro
echo.
echo Pronto: dist\Baixador.exe
goto fim
:erro
echo Algo deu errado. Veja a mensagem acima.
:fim
pause
