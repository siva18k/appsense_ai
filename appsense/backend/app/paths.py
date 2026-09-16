from pathlib import Path

APPSENSE_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = APPSENSE_ROOT / "data"
ENV_PATH = APPSENSE_ROOT / ".env"
ENV_EXAMPLE_PATH = APPSENSE_ROOT / ".env.example"


def ensure_data_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "uploads").mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "repos").mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "chroma").mkdir(parents=True, exist_ok=True)
