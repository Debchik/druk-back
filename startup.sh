#!/bin/bash
set -e

exec gunicorn main:app --bind 0.0.0.0:8000 --worker-class uvicorn.workers.UvicornWorker --workers 1
