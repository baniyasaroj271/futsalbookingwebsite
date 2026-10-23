import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-change-me")
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL", f"sqlite:///{BASE_DIR / 'futsalhub.db'}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    TESSERACT_CMD = os.getenv("TESSERACT_CMD", "")
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024
    UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", str(BASE_DIR / "instance" / "uploads" / "receipts"))
    MAP_TILE_URL = os.getenv(
        "MAP_TILE_URL",
        "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
    )
    MAP_ATTRIBUTION = os.getenv(
        "MAP_ATTRIBUTION",
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    )
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "0") == "1"
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 24 * 7
