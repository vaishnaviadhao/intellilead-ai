import io

import pandas as pd

_RISKY = ("=", "+", "-", "@", "\t", "\r")


def _safe_cell(v):
    """Neutralise spreadsheet formula injection from scraped text."""
    if isinstance(v, str) and v[:1] in _RISKY:
        return "'" + v
    return v


def sanitize(df: pd.DataFrame) -> pd.DataFrame:
    return df.apply(
        lambda col: col.map(_safe_cell) if pd.api.types.is_string_dtype(col) or col.dtype == object else col
    )


def to_csv_bytes(results: pd.DataFrame) -> bytes:
    return sanitize(results).to_csv(index=False).encode("utf-8-sig")


def to_excel_bytes(results: pd.DataFrame, rejected: pd.DataFrame | None = None) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        sanitize(results).to_excel(xw, sheet_name="Companies", index=False)
        if rejected is not None and len(rejected):
            sanitize(rejected).to_excel(xw, sheet_name="Rejected", index=False)
    return buf.getvalue()
