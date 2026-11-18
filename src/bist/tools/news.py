"""get_news_events / get_speech_features.

Optional, last-priority data layers. Until a legally accessible, timestamped dataset is placed in data/processed
(news_events.parquet / speech_features.parquet) both tools return SOURCE_NOT_AVAILABLE, so the model learns to report the gap
instead of inventing news. Expected columns:
  news_events.parquet    : ts (publication timestamp), ticker (nullable), topic, title, source, url, kind (disclosure|news)
  speech_features.parquet: source_id, ts, topics (list), claims (list), stance, speaker, source_url
"""
from __future__ import annotations

from datetime import date

import pandas as pd
from pydantic import BaseModel, Field

from ..paths import PROCESSED
from . import store
from .envelope import ToolError, tool, warn


class NewsParams(BaseModel):
    ticker: str | None = Field(default=None, description="BIST ticker (optional if topic is given).")
    topic: str | None = Field(default=None, description="Topic keyword (optional if ticker is given).")
    start: date | None = Field(default=None, description="First date; default 30 days before as_of.")
    end: date | None = Field(default=None, description="Last date; default and maximum: as_of.")
    as_of: date | None = Field(default=None, description="Analysis date; only items published before it are returned.")
    max_items: int = Field(default=10, ge=1, le=30, description="Most recent items to return.")


@tool("get_news_events", NewsParams,
      "Timestamped, legally accessible news/disclosure metadata for a ticker or topic (title, time, source). Returns SOURCE_NOT_AVAILABLE while no dataset is installed.")
def get_news_events(p: NewsParams):
    f = PROCESSED / "news_events.parquet"
    if not f.exists():
        raise ToolError("SOURCE_NOT_AVAILABLE", "No news/disclosure dataset is installed in this system; news context cannot be provided. Do not infer news.")
    if not (p.ticker or p.topic):
        raise ToolError("INVALID_PARAMS", "provide ticker or topic")
    as_of, w = store.resolve_as_of(p.as_of)
    df = pd.read_parquet(f)
    df = df[df["ts"] < as_of + pd.Timedelta(days=1)]
    end = min(pd.Timestamp(p.end) + pd.Timedelta(days=1), as_of + pd.Timedelta(days=1)) if p.end else as_of + pd.Timedelta(days=1)
    start = pd.Timestamp(p.start) if p.start else as_of - pd.Timedelta(days=30)
    df = df[(df["ts"] >= start) & (df["ts"] < end)]
    if p.ticker:
        df = df[df["ticker"] == store.resolve_ticker(p.ticker)[0]]
    if p.topic:
        df = df[df["topic"].fillna("").str.contains(p.topic, case=False) | df["title"].fillna("").str.contains(p.topic, case=False)]
    df = df.sort_values("ts").tail(p.max_items)
    if df.empty:
        w.append(warn("NO_ITEMS", "No news/disclosure items in the window."))
    return {"n_items": len(df), "items": df.to_dict("records")}, w, {"as_of": as_of, "sources": ["news_events.parquet"]}


class SpeechParams(BaseModel):
    source_id: str = Field(description="Id of an approved video/audio source whose transcript features were pre-computed.")
    as_of: date | None = Field(default=None, description="Analysis date; sources published after it are not returned.")


@tool("get_speech_features", SpeechParams,
      "Transcript-derived topics, claims and stance of an approved public video/source, with timestamps. Returns SOURCE_NOT_AVAILABLE while no dataset is installed.")
def get_speech_features(p: SpeechParams):
    f = PROCESSED / "speech_features.parquet"
    if not f.exists():
        raise ToolError("SOURCE_NOT_AVAILABLE", "No speech/transcript feature dataset is installed in this system; do not make statements about video or speech content.")
    as_of, w = store.resolve_as_of(p.as_of)
    df = pd.read_parquet(f)
    df = df[(df["source_id"] == p.source_id) & (df["ts"] < as_of + pd.Timedelta(days=1))]
    if df.empty:
        raise ToolError("UNKNOWN_SOURCE", f"source_id '{p.source_id}' not found (or published after as_of)")
    return {"source_id": p.source_id, "segments": df.to_dict("records")}, w, {"as_of": as_of, "sources": ["speech_features.parquet"]}
