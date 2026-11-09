@echo off
rem KOZMOSTOK - Sadece PostgreSQL sunucusunu baslatir (pgAdmin icin de once bunu calistirin)
"C:\Program Files\PostgreSQL\17\bin\pg_isready.exe" -q -h 127.0.0.1 -p 5432 >nul 2>&1
if errorlevel 1 (
  echo PostgreSQL baslatiliyor...
  "C:\Program Files\PostgreSQL\17\bin\pg_ctl.exe" -D "C:\Users\co_ta\PostgreSQL\data" -l "C:\Users\co_ta\PostgreSQL\server.log" start
  timeout /t 3 /nobreak >nul
)
"C:\Program Files\PostgreSQL\17\bin\pg_isready.exe" -h 127.0.0.1 -p 5432
echo.
echo Sunucu hazir. Bu pencereyi kapatabilirsiniz.
pause
