from . import create_app

# WSGI entrypoint for production servers (e.g., gunicorn)
app = create_app()
