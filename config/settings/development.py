from .base import *  # noqa: F401,F403

DEBUG = True

SECRET_KEY = 'development-only-key-do-not-use-in-production'

# Add your laptop's LAN IP here when testing from a phone
ALLOWED_HOSTS = ['127.0.0.1', 'localhost', '192.168.18.3']