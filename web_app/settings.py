
from pathlib import Path


# =========================================================
# BASE DIRECTORY
# =========================================================

BASE_DIR = Path(__file__).resolve().parent.parent


# =========================================================
# SECURITY
# =========================================================

SECRET_KEY = "django-insecure-change-this-later"

DEBUG = True

ALLOWED_HOSTS = []


# =========================================================
# INSTALLED APPS
# =========================================================

INSTALLED_APPS = [

    # Django
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    # Campus Clans
    "campus_clans",

]


# =========================================================
# MIDDLEWARE
# =========================================================

MIDDLEWARE = [

    "django.middleware.security.SecurityMiddleware",

    "django.contrib.sessions.middleware.SessionMiddleware",

    "django.middleware.common.CommonMiddleware",

    "django.middleware.csrf.CsrfViewMiddleware",

    "django.contrib.auth.middleware.AuthenticationMiddleware",

    "django.contrib.messages.middleware.MessageMiddleware",

    "django.middleware.clickjacking.XFrameOptionsMiddleware",

]


# =========================================================
# URL CONFIGURATION
# =========================================================

ROOT_URLCONF = "web_app.urls"


# =========================================================
# TEMPLATES
# =========================================================

TEMPLATES = [

    {
        "BACKEND":
            "django.template.backends.django.DjangoTemplates",

        "DIRS": [],

        "APP_DIRS": True,

        "OPTIONS": {

            "context_processors": [

                "django.template.context_processors.request",

                "django.contrib.auth.context_processors.auth",

                "django.contrib.messages.context_processors.messages",

            ],

        },

    },

]


# =========================================================
# WSGI
# =========================================================

WSGI_APPLICATION = "web_app.wsgi.application"


# =========================================================
# DATABASE
# =========================================================

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": "campus_clans",
        "USER": "buggu",
        "PASSWORD": "an290967mb",
        "HOST": "localhost",
        "PORT": "3306",
    }
}


# =========================================================
# PASSWORD VALIDATION
# =========================================================

AUTH_PASSWORD_VALIDATORS = [

    {
        "NAME":
            "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },

    {
        "NAME":
            "django.contrib.auth.password_validation.MinimumLengthValidator",
    },

    {
        "NAME":
            "django.contrib.auth.password_validation.CommonPasswordValidator",
    },

    {
        "NAME":
            "django.contrib.auth.password_validation.NumericPasswordValidator",
    },

]


# =========================================================
# INTERNATIONALIZATION
# =========================================================

LANGUAGE_CODE = "en-us"

TIME_ZONE = "Asia/Kolkata"

USE_I18N = True

USE_TZ = True


# =========================================================
# STATIC FILES
# =========================================================

STATIC_URL = "static/"


# =========================================================
# DEFAULT PRIMARY KEY
# =========================================================

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# =========================================================
# EMAIL CONFIGURATION
# =========================================================

# We will fill these values once you provide
# the email provider/account details.

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"

EMAIL_HOST = "smtp.gmail.com"

EMAIL_PORT = 587

EMAIL_USE_TLS = True

EMAIL_HOST_USER = "campusclans@gmail.com"

EMAIL_HOST_PASSWORD = "rjofficwyzviohgi"

DEFAULT_FROM_EMAIL = EMAIL_HOST_USER


# =========================================================
# LOGIN / LOGOUT
# =========================================================

LOGIN_URL = "/"

LOGIN_REDIRECT_URL = "/student-dashboard/"

LOGOUT_REDIRECT_URL = "/"


# =========================================================
# SESSION
# =========================================================

SESSION_COOKIE_AGE = 60 * 60 * 24

SESSION_EXPIRE_AT_BROWSER_CLOSE = False

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"