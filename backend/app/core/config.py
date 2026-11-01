from pathlib import Path
import os
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

ROOT = Path(__file__).resolve().parents[3]
if not (ROOT / "frontend").exists():
    ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.getenv("THEO_DATA_DIR", ROOT / "data")).resolve()
UPLOAD_DIR = DATA_DIR / "uploads"
EXPORT_DIR = DATA_DIR / "exports"
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR / 'theo.db'}")
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "100"))
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*").split(",")
for folder in (DATA_DIR, UPLOAD_DIR, EXPORT_DIR):
    folder.mkdir(parents=True, exist_ok=True)
