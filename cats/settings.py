"""Django settings for Welcome System."""
from pathlib import Path
from django.contrib.auth.apps import AuthConfig

BASE_DIR = Path(__file__).resolve().parent.parent
CATS_VERSION = "0.6.5-alpha"

# Rename the built-in auth app label in admin navigation.
AuthConfig.verbose_name = "Configuration"

SECRET_KEY = "change-me-in-production"
DEBUG = True
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "jazzmin",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "core.apps.CoreConfig",
]

JAZZMIN_SETTINGS = {
    "site_title": f"Welcome System v{CATS_VERSION}",
    "site_header": f"Welcome System v{CATS_VERSION}",
    "site_brand": "Welcome System",
    "welcome_sign": "Welcome System Administration",
    "search_model": "core.Person",
    "order_with_respect_to": ["core", "auth"],
    "icons": {
        "auth.User": "fas fa-user",
        "core.Person": "fas fa-users",
        "core.Family": "fas fa-house-user",
        "core.Service": "fas fa-calendar-day",
        "core.Tag": "fas fa-tags",
    },
    "custom_links": {
        "auth": [
            {
                "name": "System settings",
                "url": "admin:core_systemsetting_bulk",
                "icon": "fas fa-gear",
                "permissions": ["core.change_systemsetting"],
            },
            {
                "name": "Audit log",
                "url": "audit_log_report",
                "icon": "fas fa-list-check",
                "permissions": ["core.view_service"],
            },
            {
                "name": "Log out",
                "url": "admin_quick_logout",
                "icon": "fas fa-sign-out-alt",
                "permissions": ["auth.view_user"],
            },
        ],
        "core": [
            {
                "name": "Missing members",
                "url": "missing_members_report",
                "icon": "fas fa-user-clock",
                "permissions": ["core.view_service"],
            },
        ]
    },
    "hide_models": [
        "auth.Group",
        "core.Attendance",
        "core.SystemSetting",
        "core.AuditLog",
    ],
    "show_sidebar": True,
    "navigation_expanded": True,
    "custom_css": "css/admin_theme.css",
    "custom_js": "js/admin_darkmode_toggle.js",
    "changeform_format_overrides": {
        "core.family": "single",
    },
    "topmenu_links": [
        {"name": "View site", "url": "/", "permissions": ["auth.view_user"]},
        {"model": "auth.User"},
    ],
    "usermenu_links": [
        {"name": "Change password", "url": "admin:password_change"},
        {"name": "Log out", "url": "admin_quick_logout"},
    ],
}

JAZZMIN_UI_TWEAKS = {
    "theme": "default",
    "dark_mode_theme": "darkly",
}

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "core.middleware.AdminSkinMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "cats.urls"

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

WSGI_APPLICATION = "cats.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "cats.sqlite3",
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "America/New_York"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
WHITENOISE_USE_FINDERS = True
WHITENOISE_AUTOREFRESH = DEBUG
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

LOGIN_URL = "/admin/login/"
LOGIN_REDIRECT_URL = "/admin/"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
