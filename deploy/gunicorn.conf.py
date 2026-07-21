# Gunicorn 生产配置
# 启动：gunicorn -c deploy/gunicorn.conf.py "wsgi:app"
import multiprocessing
import os

bind = os.getenv('GUNICORN_BIND', '0.0.0.0:5000')
workers = int(os.getenv('GUNICORN_WORKERS', str(max(2, multiprocessing.cpu_count()))))
threads = int(os.getenv('GUNICORN_THREADS', '2'))
worker_class = 'gthread'
timeout = int(os.getenv('GUNICORN_TIMEOUT', '120'))
graceful_timeout = 30
keepalive = 5
accesslog = os.getenv('GUNICORN_ACCESSLOG', '-')
errorlog = os.getenv('GUNICORN_ERRORLOG', '-')
loglevel = os.getenv('GUNICORN_LOGLEVEL', 'info')
capture_output = True
preload_app = False
# 上传目录写权限
umask = 0o022
