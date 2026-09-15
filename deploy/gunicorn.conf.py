"""gunicorn settings for e-Shajara (used by deploy/e-shajara.service)."""

import multiprocessing

# nginx talks to gunicorn through a socket file, so no TCP port can clash
# with another site on the same server.
bind = "unix:/run/e-shajara/gunicorn.sock"
umask = 0o007          # the socket is readable by the www-data group (nginx)

# 2 cores, 4 GB RAM, shared with another site: three workers is a comfortable
# ceiling (each ~70–100 MB).
workers = min(3, multiprocessing.cpu_count() * 2 + 1)
worker_class = "sync"

# Building a big PDF book can take a while.
timeout = 120
graceful_timeout = 30

# Recycle workers now and then so memory never creeps up.
max_requests = 1000
max_requests_jitter = 100

accesslog = "-"
errorlog = "-"
loglevel = "warning"
