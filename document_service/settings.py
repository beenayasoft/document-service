"""
Django settings for Document Service avec schémas séparés
"""

import os
from pathlib import Path
from decouple import config
from corsheaders.defaults import default_headers

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.0/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = config('SECRET_KEY', default='django-insecure-document-service-dev-key')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = config('DEBUG', default=True, cast=bool)

ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1,document-service').split(',')

# Configuration des services SOA
CRM_SERVICE_URL = config('CRM_SERVICE_URL', default='http://localhost:8003')
AUTH_SERVICE_URL = config('AUTH_SERVICE_URL', default='http://localhost:8001')
TENANT_SERVICE_URL = config('TENANT_SERVICE_URL', default='http://localhost:8002')


# Application definition

# Configuration django-tenants
SHARED_APPS = [
    'django_tenants',  # Obligatoire en premier
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    
    # REST API
    "rest_framework",
    "corsheaders",
    "django_filters",
    "drf_spectacular",
    
    # Cache Django simple (pas Redis)
    
    # Apps partagées (contient les modèles Client et Domain)
    'tenant_schema',  # Modèles tenant partagés
]

TENANT_APPS = [
    # Apps spécifiques aux tenants (modèles métier isolés)
    'documents',  # Modèles métier des documents (isolés par schéma)
]

INSTALLED_APPS = list(SHARED_APPS) + [app for app in TENANT_APPS if app not in SHARED_APPS]

# Configuration django-tenants (MANQUAIT!)
TENANT_MODEL = "tenant_schema.Client"
TENANT_DOMAIN_MODEL = "tenant_schema.Domain"

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'documents.camel_case_middleware.CamelCaseToSnakeCaseMiddleware',  # CONVERSION CAMELCASE -> SNAKE_CASE
    'django.middleware.csrf.CsrfViewMiddleware',
    'documents.middleware_django_tenants.HeaderTenantMiddleware',  # DJANGO-TENANTS: Middleware correct avec connection.set_tenant()
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = "document_service.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
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

WSGI_APPLICATION = "document_service.wsgi.application"


# Database
# https://docs.djangoproject.com/en/5.0/ref/settings/#databases

# Database avec django-tenants
DATABASES = {
    'default': {
        'ENGINE': 'django_tenants.postgresql_backend',  # Engine django-tenants
        'NAME': config('DB_NAME'),
        'USER': config('DB_USER', default='postgres'),
        'PASSWORD': config('DB_PASSWORD'),
        'HOST': config('DB_HOST', default='localhost'),
        'PORT': config('DB_PORT', default='5432'),
    }
}

# Configuration pour django-tenants
DATABASE_ROUTERS = ['django_tenants.routers.TenantSyncRouter']


# Password validation
# https://docs.djangoproject.com/en/5.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.0/topics/i18n/

LANGUAGE_CODE = 'fr-fr'

TIME_ZONE = 'Europe/Paris'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.0/howto/static-files/

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Default primary key field type
# https://docs.djangoproject.com/en/5.0/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# REST Framework configuration
REST_FRAMEWORK = {
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.AllowAny',
    ],
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_FILTER_BACKENDS': ['django_filters.rest_framework.DjangoFilterBackend'],
}

# API Documentation
SPECTACULAR_SETTINGS = {
    'TITLE': 'Document Service API',
    'DESCRIPTION': 'Service unifié pour la gestion des documents commerciaux (devis et factures)',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
}

# API Configuration
API_PORT = config('API_PORT', default=8004, cast=int)
API_HOST = config('API_HOST', default='0.0.0.0')

# CORS settings
CORS_ALLOW_ALL_ORIGINS = DEBUG
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",  # React frontend
    "http://127.0.0.1:3000",
    "http://localhost:8000",  # API Gateway
    "http://localhost:8080",  # Frontend alternatif
] if not DEBUG else []

CORS_ALLOW_HEADERS = list(default_headers) + [
    'X-Tenant-ID',
]

# Cache Redis
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'document-service-cache',
        'OPTIONS': {
            'MAX_ENTRIES': 1000,  # Nombre maximum d'entrées en cache
            'CULL_FREQUENCY': 3,  # Fraction à supprimer quand MAX_ENTRIES est atteint
        }
    }
}

# Créer le dossier logs s'il n'existe pas
LOGS_DIR = BASE_DIR / 'logs'
LOGS_DIR.mkdir(exist_ok=True)

# Logging
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
        'file': {
            'class': 'logging.FileHandler',
            'filename': LOGS_DIR / 'document.log',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': config('LOG_LEVEL', default='INFO'),
    },
    'loggers': {
        'documents': {
            'handlers': ['console', 'file'],
            'level': config('LOG_LEVEL', default='INFO'),
            'propagate': False,
        },
    },
}

# Configuration spécifique au service de documents
DOCUMENT_SERVICE = {
    # Configuration générales (non tenant-specific)
    'DEFAULT_VALIDITY_PERIOD': 30,  # jours
    'PDF_STORAGE_PATH': BASE_DIR / 'media' / 'pdfs',
    'MAX_ITEMS_PER_DOCUMENT': 1000,
    'CACHE_TIMEOUT': 300,  # 5 minutes
}

# Configuration tenant-service pour récupérer les configurations tenant
TENANT_SERVICE_URL = os.getenv('TENANT_SERVICE_URL', 'http://localhost:8001')
TENANT_SERVICE_TIMEOUT = int(os.getenv('TENANT_SERVICE_TIMEOUT', '10'))  # Augmenté à 10s
TENANT_CONFIG_CACHE_TIMEOUT = int(os.getenv('TENANT_CONFIG_CACHE_TIMEOUT', '900'))  # 15 minutes
TENANT_NUMBERING_CACHE_TIMEOUT = int(os.getenv('TENANT_NUMBERING_CACHE_TIMEOUT', '1800'))  # 30 minutes

# Performance optimizations
ENABLE_CACHE_WARMUP = config('ENABLE_CACHE_WARMUP', default=True, cast=bool)
ENABLE_BATCH_TENANT_CALLS = config('ENABLE_BATCH_TENANT_CALLS', default=True, cast=bool)

# Créer le dossier media s'il n'existe pas
MEDIA_ROOT = BASE_DIR / 'media'
MEDIA_ROOT.mkdir(exist_ok=True)
DOCUMENT_SERVICE['PDF_STORAGE_PATH'].mkdir(exist_ok=True)

MEDIA_URL = '/media/'

# Configuration django-tenants
TENANT_MODEL = 'tenant_schema.Client'
TENANT_DOMAIN_MODEL = 'tenant_schema.Domain'

# Configuration tenant schema (garder pour compatibilité)
TENANT_SCHEMA_PREFIX = 'tenant_'
