"""Low-memory Gunicorn defaults; every value can be overridden by environment."""

import os

bind = f"{os.environ.get('WORKLOG_ADDRESS', '127.0.0.1')}:{os.environ.get('WORKLOG_PORT', '8501')}"
workers = int(os.environ.get("WORKLOG_WORKERS", "1"))
threads = int(os.environ.get("WORKLOG_THREADS", "2"))
worker_class = "gthread"
timeout = 30
graceful_timeout = 15
keepalive = 5
max_requests = 1000
max_requests_jitter = 100
accesslog = "-"
errorlog = "-"
capture_output = True
