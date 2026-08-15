@echo off
setlocal
cd /d "%~dp0"
title PAL-AI In-Place Update
if "%~1"=="" (
  echo Drag a newer PAL-AI ZIP onto this file.
  pause
  exit /b 1
)
if not exist "%~1" (
  echo ZIP not found: %~1
  pause
  exit /b 1
)
set "TMPDIR=%TEMP%\palai_manual_update_%RANDOM%"
mkdir "%TMPDIR%" >nul 2>&1
powershell -NoProfile -Command "Expand-Archive -LiteralPath '%~1' -DestinationPath '%TMPDIR%' -Force"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
 "$root='%TMPDIR%'; $items=Get-ChildItem -LiteralPath $root; if($items.Count -eq 1 -and $items[0].PSIsContainer){$src=$items[0].FullName}else{$src=$root}; $preserve=@('config.json','data','knowledge','screenshots','.venv'); Get-ChildItem -LiteralPath $src | Where-Object {$preserve -notcontains $_.Name} | ForEach-Object {$dst=Join-Path '%CD%' $_.Name; if(Test-Path -LiteralPath $dst){Remove-Item -LiteralPath $dst -Recurse -Force}; Copy-Item -LiteralPath $_.FullName -Destination $dst -Recurse -Force}"
if exist ".venv\Scripts\python.exe" if exist "requirements.txt" .venv\Scripts\python.exe -m pip install -r requirements.txt
rmdir /s /q "%TMPDIR%" >nul 2>&1
echo Update applied. Your local data was preserved.
pause
