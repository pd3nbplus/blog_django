import os
from copy import deepcopy
from typing import Any, cast

from .base import *  # noqa
from .base import LOGGING as BASE_LOGGING

DEBUG = False

raw_hosts = os.getenv("DJANGO_ALLOWED_HOSTS") or os.getenv("ALLOWED_HOSTS") or ""
ALLOWED_HOSTS = [item.strip() for item in raw_hosts.split(",") if item.strip()]

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

prod_logging = cast(dict[str, Any], deepcopy(BASE_LOGGING))
handlers = cast(dict[str, Any], prod_logging.setdefault("handlers", {}))
handlers["file"] = {
    "class": "logging.FileHandler",
    "filename": "/var/log/django/app.log",
    "formatter": "verbose",
    "level": "WARNING",
}
root_logger = prod_logging.setdefault("root", {"handlers": ["console"], "level": "INFO"})
if isinstance(root_logger, dict):
    handlers = root_logger.setdefault("handlers", [])
    if isinstance(handlers, list) and "file" not in handlers:
        handlers.append("file")

LOGGING = prod_logging
