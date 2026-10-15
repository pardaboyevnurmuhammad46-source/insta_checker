import os
import sys


def main():
    """Run administrative tasks or launch development server."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    
    args = sys.argv
    if len(args) == 1:
        args = ['manage.py', 'runserver', '127.0.0.1:8000']
    
    execute_from_command_line(args)


if __name__ == '__main__':
    main()
