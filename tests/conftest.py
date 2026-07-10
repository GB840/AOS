"""pytest conftest — ensures v5.0 Config won't crash during collection."""
import os

# Must run before ANY import touches utils/config.py
_fields = ["API_KEY_HASH", "ADMIN_USERNAME", "ADMIN_PASSWORD", "POSTGRES_PASSWORD", "AOS_TOKEN_SECRET"]
for f in _fields:
    os.environ.setdefault(f, "conftest-placeholder")

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
except ImportError:
    pass
