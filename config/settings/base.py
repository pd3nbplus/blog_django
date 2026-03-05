from __future__ import annotations

import logging
import logging.handlers
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BASE_DIR / ".env")


def _env_bool(*names: str, default: bool = False) -> bool:
    for name in names:
        raw = os.getenv(name)
        if raw is None:
            continue
        return str(raw).strip().lower() in {"1", "true", "yes", "y", "on"}
    return default


def _env_list(*names: str, default: list[str] | None = None) -> list[str]:
    for name in names:
        raw = os.getenv(name)
        if raw is None:
            continue
        return [item.strip() for item in str(raw).split(",") if item.strip()]
    return list(default or [])


def _env_int(*names: str, default: int) -> int:
    for name in names:
        raw = os.getenv(name)
        if raw is None:
            continue
        try:
            return int(str(raw).strip())
        except ValueError:
            continue
    return default


SECRET_KEY = os.getenv("DJANGO_SECRET_KEY") or os.getenv("SECRET_KEY") or "django-insecure-change-me"
DEBUG = _env_bool("DJANGO_DEBUG", "DEBUG", default=False)
ALLOWED_HOSTS = _env_list("DJANGO_ALLOWED_HOSTS", "ALLOWED_HOSTS", default=["127.0.0.1", "localhost"])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party
    "corsheaders",
    "rest_framework",
    "rest_framework.authtoken",
    "drf_spectacular",
    # Local apps
    "apps.common",
    "apps.users",
    "apps.articles",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.common.middleware.ApiAuditLogMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": os.getenv("DB_NAME", "blog_project"),
        "USER": os.getenv("DB_USER", "root"),
        "PASSWORD": os.getenv("DB_PASSWORD", "ubuntu2002"),
        "HOST": os.getenv("DB_HOST", "127.0.0.1"),
        "PORT": os.getenv("DB_PORT", "3307"),
        "OPTIONS": {
            "charset": "utf8mb4",
            "use_unicode": True,
            "init_command": "SET sql_mode='STRICT_TRANS_TABLES',default_storage_engine=INNODB",
        },
        "CONN_MAX_AGE": _env_int("DB_CONN_MAX_AGE", default=600),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "zh-hans"
TIME_ZONE = "Asia/Shanghai"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.TokenAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticatedOrReadOnly",
    ],
    "DEFAULT_PAGINATION_CLASS": "apps.common.pagination.StandardPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "apps.common.exceptions.custom_exception_handler",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Blog Project API",
    "DESCRIPTION": "基于 Django 4.2 + DRF 的规范化 API 文档",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "TAGS": [
        {"name": "users", "description": "用户认证与管理"},
        {"name": "articles", "description": "文章与内容管理"},
    ],
}

CORS_ALLOW_CREDENTIALS = True
CORS_ALLOWED_ORIGINS = _env_list(
    "CORS_ALLOWED_ORIGINS",
    default=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    ],
)
CORS_ALLOWED_ORIGIN_REGEXES = _env_list(
    "CORS_ALLOWED_ORIGIN_REGEXES",
    default=[],
)

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "blog-api-cache",
    }
}

LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[%(levelname)s][%(asctime)s][%(filename)s:%(lineno)d:%(funcName)s] %(message)s",
        },
        "simple": {
            "format": "[%(levelname)s] %(message)s",
        },
    },
    "handlers": {
        "file": {
            "level": "INFO",
            "class": "logging.handlers.TimedRotatingFileHandler",
            "filename": str(LOG_DIR / "blog_api.log"),
            "when": "midnight",
            "backupCount": 30,
            "formatter": "verbose",
            "encoding": "utf-8",
        },
        "error_file": {
            "level": "WARNING",
            "class": "logging.handlers.TimedRotatingFileHandler",
            "filename": str(LOG_DIR / "blog_api_error.log"),
            "when": "midnight",
            "backupCount": 30,
            "formatter": "verbose",
            "encoding": "utf-8",
        },
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "django": {
            "handlers": ["file", "console"],
            "level": "WARNING",
            "propagate": False,
        },
        "django.server": {
            "handlers": ["file", "console"],
            "level": "WARNING",
            "propagate": False,
        },
        "blog_api": {
            "handlers": ["file", "console"],
            "level": "INFO",
            "propagate": False,
        },
        "blog_api.audit": {
            "handlers": ["file", "console"],
            "level": "INFO",
            "propagate": False,
        },
        "blog_api.error": {
            "handlers": ["error_file", "file", "console"],
            "level": "WARNING",
            "propagate": False,
        },
    },
}

logger = logging.getLogger("blog_api")
