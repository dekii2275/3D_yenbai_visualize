@echo off
cd /d "%~dp0"
echo Dang build va khoi chay container...
docker compose up --build -d
echo.
docker compose ps
echo.
echo Mo trinh duyet tai http://localhost:18087
pause
