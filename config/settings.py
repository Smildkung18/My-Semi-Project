from pathlib import Path
import os
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# โหลด .env จาก root ของ project (เฉพาะเมื่อไฟล์มีอยู่จริง)
env_path = BASE_DIR / '.env'
if env_path.exists():
    load_dotenv(env_path)

SECRET_KEY = os.environ['SECRET_KEY']

DEBUG = os.environ.get('DEBUG', 'False') == 'True'

ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', '').split(',')

# ── Apps ──────────────────────────────────────────────────────────────────
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',          # ← allauth ต้องการ
    # allauth
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.google',
    # apps
    'projects',
    'tasks',
    'schedules',                     # ← Schedule feature
]

SITE_ID = 1

# ── Middleware ────────────────────────────────────────────────────────────
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'allauth.account.middleware.AccountMiddleware',  # ← allauth ต้องการ
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
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

WSGI_APPLICATION = 'config.wsgi.application'

# ── Database ──────────────────────────────────────────────────────────────
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# ── Password validation ───────────────────────────────────────────────────
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# ── Internationalisation ──────────────────────────────────────────────────
LANGUAGE_CODE = 'en-us'
TIME_ZONE     = 'Asia/Bangkok'
USE_I18N      = True
USE_TZ        = True

# ── Static / Media ────────────────────────────────────────────────────────
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
MEDIA_URL  = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ── Authentication backends ───────────────────────────────────────────────
AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',            # username/password เดิม
    'allauth.account.auth_backends.AuthenticationBackend',  # Google OAuth
]

# ── Redirect URLs ─────────────────────────────────────────────────────────
LOGIN_URL           = '/login/'
LOGIN_REDIRECT_URL  = '/'
LOGOUT_REDIRECT_URL = '/login/'

# ── django-allauth ────────────────────────────────────────────────────────
ACCOUNT_EMAIL_VERIFICATION          = 'none'
ACCOUNT_LOGIN_ON_EMAIL_CONFIRMATION = True
ACCOUNT_AUTHENTICATION_METHOD       = 'username_email'
ACCOUNT_EMAIL_REQUIRED              = True
ACCOUNT_USERNAME_REQUIRED           = True
SOCIALACCOUNT_AUTO_SIGNUP           = True
SOCIALACCOUNT_QUERY_EMAIL           = True
SOCIALACCOUNT_LOGIN_ON_GET          = True
SOCIALACCOUNT_EMAIL_AUTHENTICATION  = True

SOCIALACCOUNT_PROVIDERS = {
    'google': {
        'SCOPE':       ['profile', 'email'],
        'AUTH_PARAMS': {'access_type': 'online'},
    }
}

# ── Email (Gmail SMTP — ส่ง OTP) ─────────────────────────────────────────
EMAIL_BACKEND       = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST          = 'smtp.gmail.com'
EMAIL_PORT          = 587
EMAIL_USE_TLS       = True
EMAIL_HOST_USER     = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
DEFAULT_FROM_EMAIL  = os.environ.get('DEFAULT_FROM_EMAIL', f'KanFlow <{EMAIL_HOST_USER}>')

# ── Production / Railway ──────────────────────────────────────────────────
import sys

# Whitenoise — serve static files โดยไม่ต้องมี nginx
if 'whitenoise.middleware.WhiteNoiseMiddleware' not in MIDDLEWARE:
    MIDDLEWARE.insert(1, 'whitenoise.middleware.WhiteNoiseMiddleware')

STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# Railway inject RAILWAY_ENVIRONMENT เมื่อ deploy จริง
ON_RAILWAY = os.environ.get('RAILWAY_ENVIRONMENT') is not None

if ON_RAILWAY:
    DEBUG = False
    # Railway inject RAILWAY_PUBLIC_DOMAIN ให้อัตโนมัติ
    RAILWAY_HOST = os.environ.get('RAILWAY_PUBLIC_DOMAIN', '')
    if RAILWAY_HOST and RAILWAY_HOST not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(RAILWAY_HOST)