@echo off
rem KOZMOSIZE - Supabase (PostgreSQL) modunda baslatir; ayarlar config.ini dosyasindan okunur
cd /d %~dp0
set DB_MODE=postgres
python main.py
