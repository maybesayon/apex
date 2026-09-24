"""
JSON-safe conversion for analysis output.

The analysis engine returns pandas/numpy scalars (np.float64, np.bool_) and
occasionally NaN/inf. `json.dumps` accepts some of these and silently emits
invalid JSON for others — NaN and Infinity are not valid JSON, and a browser
JSON.parse rejects them.

Converting here rather than inside the analysis modules keeps the engine
framework-agnostic: it stays usable from Streamlit, the API and the future
worker without knowing about any of them.
"""

import math
from datetime import date, datetime
from typing import Any

import numpy as np
import pandas as pd


def to_jsonable(obj: Any) -> Any:
    """Recursively convert to plain JSON-serialisable Python types."""
    if obj is None or isinstance(obj, (str, bool, int)):
        return obj

    if isinstance(obj, float):
        # NaN and +/-Infinity are not valid JSON. Null is the honest
        # representation of "this indicator has no value here".
        return None if (math.isnan(obj) or math.isinf(obj)) else obj

    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return to_jsonable(float(obj))
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, np.ndarray):
        return [to_jsonable(v) for v in obj.tolist()]

    if isinstance(obj, (datetime, pd.Timestamp)):
        return obj.isoformat()
    if isinstance(obj, date):
        return obj.isoformat()

    if obj is pd.NaT:
        return None
    if isinstance(obj, dict):
        return {str(k): to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [to_jsonable(v) for v in obj]

    if isinstance(obj, pd.Series):
        return to_jsonable(obj.to_dict())
    if isinstance(obj, pd.DataFrame):
        return to_jsonable(obj.to_dict(orient="records"))

    try:
        if pd.isna(obj):
            return None
    except (TypeError, ValueError):
        pass

    return obj


def ohlcv_records(df: pd.DataFrame) -> list[dict]:
    """
    Historical bars as a list of records with ISO dates.

    Shaped for TradingView Lightweight Charts, which wants
    {time, open, high, low, close} per bar.
    """
    if df is None or df.empty:
        return []
    out = []
    for ts, row in df.iterrows():
        rec = {"time": pd.Timestamp(ts).date().isoformat()}
        for col in ("open", "high", "low", "close", "volume"):
            if col in df.columns:
                rec[col] = to_jsonable(row[col])
        out.append(rec)
    return out
