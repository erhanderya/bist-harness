import pandas as pd
from .paths import UNIVERSE_CSV


def load_universe() -> pd.DataFrame:
    return pd.read_csv(UNIVERSE_CSV)


def build_sector_peer_groups() -> dict[str, list[str]]:
    u = load_universe()
    return {g: df["ticker"].tolist() for g, df in u.groupby("peer_group")}
