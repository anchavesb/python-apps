import sys
from pathlib import Path

# Ensure local src is on sys.path when running directly without installation
PACKAGE_SRC = Path(__file__).resolve().parent / "src"
if PACKAGE_SRC.exists():
    sys.path.insert(0, str(PACKAGE_SRC))

from todo_app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=app.config["PORT"], debug=app.config["DEBUG"]) 
