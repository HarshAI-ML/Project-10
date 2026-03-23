#!/bin/bash
cd /home/azureuser/auto-invest-ai/backend
set -a
source /home/azureuser/auto-invest-ai/backend/.env
set +a
source venv/bin/activate
gunicorn --workers 2 --timeout 300 \
  --bind unix:/home/azureuser/auto-invest-ai/backend/autoinvest.sock \
  auto_invest.wsgi:application