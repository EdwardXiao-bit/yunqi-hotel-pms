"""云栖酒店客房预订与入住管理系统 —— Django 工程配置。

设计要点（与 AGENTS.md §4.2 一致）：
- 服务端渲染、单进程 runserver，不写 JSON API。
- 数据库结构由 `sql/00_database.sql` → `01_schema.sql` → `02_constraints.sql` 唯一决定，
  Django 模型一律 `managed = False`，**不用 migrations 建表**。
- 鉴权用自定义用户模型 `core.AppUser`（表 `app_user`）+ `role` 列 + `role_required`，
  不用 Django 的 Group/Permission。
"""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent          # src/
PROJECT_ROOT = BASE_DIR.parent                              # 仓库根


def _load_dotenv() -> None:
    """极简 .env 读取（不引第三方依赖）。

    查找顺序：仓库根 `.env` → `src/.env`；已存在的真实环境变量优先，绝不覆盖。
    支持 `KEY=VALUE`、`#` 注释、值两端引号。
    """
    for candidate in (PROJECT_ROOT / ".env", BASE_DIR / ".env"):
        if not candidate.is_file():
            continue
        for raw in candidate.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


_load_dotenv()

# ---------------------------------------------------------------- 基础

SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    # 仅开发默认值；部署/演示前用 .env 覆盖
    "dev-only-insecure-key-change-me-9f2c1b6a7d4e8f03",
)
DEBUG = os.environ.get("DJANGO_DEBUG", "1") not in ("0", "false", "False", "")
ALLOWED_HOSTS = [
    h.strip()
    for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost,[::1]").split(",")
    if h.strip()
]

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "core",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
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
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.navigation",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# ---------------------------------------------------------------- 数据库
# 结构由 sql/ 脚本维护；Django 只读写给已有表，不做 migration。

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("DB_NAME", "yunqi_hotel"),
        "USER": os.environ.get("DB_USER", "postgres"),
        "PASSWORD": os.environ.get("DB_PASSWORD", os.environ.get("PGPASSWORD", "")),
        "HOST": os.environ.get("DB_HOST", "127.0.0.1"),
        "PORT": os.environ.get("DB_PORT", "5432"),
        "OPTIONS": {
            # 时间一律 timestamptz；连接级时区与库一致，便于 psql 与页面结果对齐
            "options": "-c timezone=Asia/Shanghai -c search_path=public",
            "connect_timeout": 5,
        },
        "CONN_MAX_AGE": 0,
        "ATOMIC_REQUESTS": False,
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------- 鉴权

AUTH_USER_MODEL = "core.AppUser"
AUTHENTICATION_BACKENDS = ["core.backends.AppUserBackend"]

LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/login/"

SESSION_COOKIE_NAME = "yunqi_sessionid"
SESSION_COOKIE_AGE = 60 * 60 * 8          # 前台一班 8 小时
SESSION_EXPIRE_AT_BROWSER_CLOSE = False
CSRF_COOKIE_NAME = "yunqi_csrftoken"

# 密码哈希：种子数据用的是 Django 默认 pbkdf2_sha256，保持默认即可
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.BCryptSHA256PasswordHasher",
]

# ---------------------------------------------------------------- 国际化

LANGUAGE_CODE = "zh-hans"
TIME_ZONE = "Asia/Shanghai"
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------- 静态与媒体

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = PROJECT_ROOT / "work" / "static_collect"

MEDIA_URL = "/media/"
MEDIA_ROOT = PROJECT_ROOT / "work" / "media"

# ---------------------------------------------------------------- 消息样式

from django.contrib.messages import constants as message_constants  # noqa: E402

MESSAGE_TAGS = {
    message_constants.DEBUG: "secondary",
    message_constants.INFO: "info",
    message_constants.SUCCESS: "success",
    message_constants.WARNING: "warning",
    message_constants.ERROR: "danger",
}

# ---------------------------------------------------------------- 日志

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {"format": "[{asctime}] {levelname} {name}: {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "simple"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        # 让 SQLSTATE 映射的告警在控制台可见
        "core": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}
