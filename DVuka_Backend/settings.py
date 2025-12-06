import os
from pathlib import Path
from datetime import timedelta
from dotenv import load_dotenv
from corsheaders.defaults import default_headers

# ---------------------------------------
# Load environment variables
# ---------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# ---------------------------------------
# Core Security
# ---------------------------------------
# If SECRET_KEY is missing, it warns you but doesn't crash (good for testing)
SECRET_KEY = os.getenv("SECRET_KEY", "django-insecure-test-key-change-in-prod")

# We keep this strictly explicit for now
DEBUG = os.getenv("DEBUG", "True").lower() == "true"

ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "127.0.0.1,localhost").split(",")

# ---------------------------------------
# Installed Apps (Restored Full List)
# ---------------------------------------
INSTALLED_APPS = [
    "daphne",  # Channels (Must be top)
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
    'help_center'
]

# ---------------------------------------
# Middleware (Restored Full List)
# ---------------------------------------
MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'users.middleware.ActiveOrganizationMiddleware',  # Your custom middleware
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

# ------------------------------------------------
# 1. DATABASE CONFIGURATION
# ------------------------------------------------
# If POSTGRES_DB is set in .env, use PostgreSQL. Otherwise, use SQLite (Local).
if os.environ.get('POSTGRES_DB'):
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.environ.get('POSTGRES_DB'),
            'USER': os.environ.get('POSTGRES_USER'),
            'PASSWORD': os.environ.get('POSTGRES_PASSWORD'),
            'HOST': os.environ.get('POSTGRES_HOST'),
            'PORT': os.environ.get('POSTGRES_PORT'),
        }
    }
else:
    # Fallback to SQLite for local testing if no Postgres config is found
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }


# ---------------------------------------
# Channels / Redis
# ---------------------------------------
# We stick to InMemory for testing if Redis isn't found
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


# ---------------------------------------
# Auth
# ---------------------------------------
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
    {'NAME': 'users.validators.ComplexPasswordValidator',},
]

# ---------------------------------------
# Localization
# ---------------------------------------
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Africa/Nairobi'
USE_I18N = True
USE_TZ = True
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ------------------------------------------------
# 2. FILE STORAGE (Bunny.net Native)
# ------------------------------------------------
USE_S3 = os.environ.get("USE_S3", "False").lower() == "true"

# --- DEFINE THESE GLOBALLY (Critical Fix) ---
# The library looks for these in global settings, not inside the conditional block.
BUNNY_USERNAME = os.environ.get('AWS_ACCESS_KEY_ID')
BUNNY_PASSWORD = os.environ.get('BUNNY_API_KEY')
BUNNY_REGION = os.environ.get('BUNNY_REGION', 'uk')

if USE_S3:
    # --- STATIC FILES (Keep Local for Admin Speed) ---
    STATIC_URL = '/static/'
    STATIC_ROOT = BASE_DIR / "staticfiles"

    # --- MEDIA FILES (Bunny.net) ---
    # Configure Django 4.2+ STORAGES dictionary
    STORAGES = {
        "default": {
            "BACKEND": "django_bunny_storage.storage.BunnyStorage",
            # No OPTIONS block needed here; it reads the Global BUNNY_* vars above
        },
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    }

    # Set the MEDIA_URL so Django knows how to display images
    BUNNY_URL = os.environ.get('BUNNY_PULL_ZONE_URL')
    if BUNNY_URL:
        # Ensure it ends with a slash
        MEDIA_URL = f"{BUNNY_URL}/" if not BUNNY_URL.endswith("/") else BUNNY_URL
    else:
        MEDIA_URL = '/media/'

else:
    # --- LOCAL DEVELOPMENT ---
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

# ---------------------------------------
# REST & JWT
# ---------------------------------------
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

# ---------------------------------------
# Logging (Restored your previous config)
# ---------------------------------------
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

# ---------------------------------------
# CORS / CSRF / Proxy
# ---------------------------------------
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOWED_ORIGINS = os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",")
CSRF_TRUSTED_ORIGINS = os.getenv("CSRF_TRUSTED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",")

CORS_ALLOW_HEADERS = list(default_headers) + [
    "x-organization-slug",
]

SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = True