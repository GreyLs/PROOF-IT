from pathlib import Path
import os


def secret(name, default=None):
    if path := os.getenv(name + '_FILE'):
        return Path(path).read_text(encoding='utf-8').strip()
    return os.getenv(name, default)


def database_url():
    value = secret('WORKER_DATABASE_URL') or secret('DATABASE_URL')
    if not value:
        raise ValueError('Missing worker database configuration')
    return value
