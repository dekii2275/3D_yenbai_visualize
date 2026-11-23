"""Shared paths for the trial landslide model."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'data' / 'du_lieu_phuong_Yen_Bai' / 'du_lieu'
OUT = ROOT / 'model' / 'outputs'
WORK = ROOT / 'model' / 'work'
CONFIG = ROOT / 'model' / 'config.json'
