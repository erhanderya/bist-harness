from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
RAW = DATA / "raw"
PROCESSED = DATA / "processed"
DB = DATA / "db"
UNIVERSE_CSV = DATA / "universe.csv"
