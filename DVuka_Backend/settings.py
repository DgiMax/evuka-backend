import os
from pathlib import Path
from datetime import timedelta
from dotenv import load_dotenv
from corsheaders.defaults import default_headers

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.getenv("SECRET_KEY", "django-insecure-test-key-change-in-prod")
DEBUG = os.getenv("DEBUG", "True").lower() == "true"
ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "127.0.0.1,localhost").split(",")

INSTALLED_APPS = [
    "daphne",
    "corsheaders",
    "django_filters",
    "storages",
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    'users',
    'core',
    'organizations',
    'courses',
    'payments',
    'events',
    'marketplace',
    'orders',
    'announcements',
    'notifications',
    'revenue',
    'students',
    'live',
    'org_community',
    'ai_assistant',
    'help_center',
    'books',
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'users.middleware.ActiveOrganizationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'DVuka_Backend.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'DVuka_Backend.wsgi.application'
ASGI_APPLICATION = "DVuka_Backend.asgi.application"

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

REDIS_HOST = os.getenv("REDIS_HOST", None)

if REDIS_HOST:
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {
                "hosts": [(REDIS_HOST, 6379)]
            },
        },
    }
else:
    CHANNEL_LAYERS = {
        "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
    }

AUTH_USER_MODEL = "users.User"
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {
            'min_length': 10,
        }
    },
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
    {'NAME': 'users.validators.ComplexPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Africa/Nairobi'
USE_I18N = True
USE_TZ = True
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

USE_S3 = os.environ.get("USE_S3", "False").lower() == "true"

BUNNY_USERNAME = os.environ.get('AWS_ACCESS_KEY_ID')
BUNNY_PASSWORD = os.environ.get('AWS_SECRET_ACCESS_KEY')
BUNNY_REGION = os.environ.get('BUNNY_REGION', 'uk')
BUNNY_PULL_ZONE_URL = os.environ.get('BUNNY_PULL_ZONE_URL')

if USE_S3:
    STATIC_URL = '/static/'
    STATIC_ROOT = BASE_DIR / "static"

    STORAGES = {
        "default": {
            "BACKEND": "DVuka_Backend.custom_storage.ConnectedBunnyStorage",
        },
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    }

    BUNNY_URL = os.environ.get('BUNNY_PULL_ZONE_URL')
    if BUNNY_URL:
        MEDIA_URL = f"{BUNNY_URL}/" if not BUNNY_URL.endswith("/") else BUNNY_URL
    else:
        MEDIA_URL = '/media/'
else:
    STATIC_URL = '/static/'
    MEDIA_URL = '/media/'
    STATIC_ROOT = BASE_DIR / "staticfiles"
    MEDIA_ROOT = BASE_DIR / "media"

    STORAGES = {
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    }

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "users.authentication.CookieJWTAuthentication",
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PARSER_CLASSES": [
        'rest_framework.parsers.JSONParser',
        'rest_framework.parsers.FormParser',
        'rest_framework.parsers.MultiPartParser',
    ],
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=int(os.getenv("ACCESS_TOKEN_LIFETIME", 15))),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=int(os.getenv("REFRESH_TOKEN_LIFETIME", 60))),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "AUTH_COOKIE": "access_token",
    "AUTH_COOKIE_SECURE": os.getenv("AUTH_COOKIE_SECURE", "False").lower() == "true",
    "AUTH_COOKIE_HTTP_ONLY": True,
    "AUTH_COOKIE_PATH": "/",
    "AUTH_COOKIE_SAMESITE": "Lax",
}

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'loggers': {
        '': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': True,
        },
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'ai_assistant': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}


EMAIL_BACKEND = os.environ.get("EMAIL_BACKEND")
EMAIL_HOST = os.environ.get("EMAIL_HOST")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", 587))
EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS") == "True"
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD")
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL")

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://127.0.0.1:3000")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

PAYSTACK_PUBLIC_KEY = os.getenv("PAYSTACK_PUBLIC_KEY")
PAYSTACK_SECRET_KEY = os.getenv("PAYSTACK_SECRET_KEY")
PAYSTACK_CALLBACK_URL = os.getenv("PAYSTACK_CALLBACK_URL", f"{FRONTEND_URL}/order-confirmation")

JITSI_DOMAIN = os.getenv("JITSI_DOMAIN")
JITSI_APP_ID = os.getenv("JITSI_APP_ID")
JITSI_APP_SECRET = os.getenv("JITSI_APP_SECRET")
JITSI_USE_SSL = os.getenv("JITSI_USE_SSL", "True").lower() == "true"

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")

CORS_ALLOW_CREDENTIALS = True
CORS_ALLOWED_ORIGINS = os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",")
CSRF_TRUSTED_ORIGINS = os.getenv("CSRF_TRUSTED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",")

CORS_ALLOW_HEADERS = list(default_headers) + [
    "x-organization-slug",
]

SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = True

BUNNY_LIBRARY_ID = 576084
BUNNY_API_KEY = "ad887a2c-493d-481b-9799ca4975e5-fe45-4f6f"
BUNNY_PULL_ZONE = "vz-2a442acc-7d2"

LIVE_SOCKET_URL = "ws://127.0.0.1:8001"

CELERY_BROKER_URL = f"redis://{REDIS_HOST or 'localhost'}:6379/0"
CELERY_RESULT_BACKEND = f"redis://{REDIS_HOST or 'localhost'}:6379/0"
CELERY_ACCEPT_CONTENT = ['application/json']
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TASK_SERIALIZER = 'json'
CELERY_TIMEZONE = 'UTC'


X_FRAME_OPTIONS = 'SAMEORIGIN'