#!/usr/bin/env python3
import os
import sys
from pathlib import Path


def main():
    """Run administrative tasks or launch development server."""
    # Virtual environment avtomatik aniqlash va ishga tushirish
    base_dir = Path(__file__).resolve().parent
    venv_python = base_dir / "venv" / "bin" / "python"
    if venv_python.exists() and sys.executable != str(venv_python):
        try:
            import django
        except ImportError:
            os.execv(str(venv_python), [str(venv_python)] + sys.argv)

    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    
    # If run directly (e.g. green Run button in PyCharm), launch runserver
    args = sys.argv
    if len(args) == 1:
        args = ['manage.py', 'runserver', '127.0.0.1:8000']
    
    execute_from_command_line(args)


if __name__ == '__main__':
    main()
