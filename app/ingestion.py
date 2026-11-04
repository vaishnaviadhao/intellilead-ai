from dataclasses import dataclass

import pandas as pd

from .domain import normalize_domain

DOMAIN_COLS = ("domain", "website", "url", "web", "site", "company_domain", "company_website")
NAME_COLS = ("company_name", "company", "name", "organization", "organisation", "account")


@dataclass
class IngestionResult:
    valid: pd.DataFrame
    rejected: pd.DataFrame
    stats: dict


def _find(columns, candidates):
    for c in candidates:
        if c in columns:
            return c
    return None


def load_companies(source, max_rows: int = 5000) -> IngestionResult:
    """Read a CSV of companies. Needs a domain/website/url column, name is optional."""
    df = pd.read_csv(source, dtype=str, keep_default_na=False, encoding_errors="replace")
    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]

    if len(df) == 0:
        raise ValueError("CSV has no data rows")
    if len(df) > max_rows:
        raise ValueError(f"CSV has {len(df)} rows, limit is {max_rows}")

    dcol = _find(df.columns, DOMAIN_COLS)
    if dcol is None:
        raise ValueError(f"No domain column found. Expected one of: {', '.join(DOMAIN_COLS)}")
    ncol = _find(df.columns, NAME_COLS)

    out = pd.DataFrame(
        {
            "input_row": range(2, len(df) + 2),  # row 1 is the header
            "company_name": df[ncol].str.strip() if ncol else "",
            "raw_domain": df[dcol],
        }
    )
    out["domain"] = out["raw_domain"].map(normalize_domain)

    bad = out["domain"].isna()
    rejected = out[bad].copy()
    rejected["reason"] = "invalid_domain"

    good = out[~bad].copy()
    dup = good.duplicated(subset="domain", keep="first")
    dup_rows = good[dup].copy()
    dup_rows["reason"] = "duplicate_domain"
    rejected = pd.concat([rejected, dup_rows], ignore_index=True)
    good = good[~dup].copy()

    blank = good["company_name"].str.strip() == ""
    good.loc[blank, "company_name"] = good.loc[blank, "domain"].str.split(".").str[0].str.title()

    good = good.drop(columns=["raw_domain"]).reset_index(drop=True)
    rejected = (
        rejected.drop(columns=["domain"]).rename(columns={"raw_domain": "value"}).reset_index(drop=True)
    )

    stats = {
        "rows_in": len(df),
        "valid": len(good),
        "invalid": int((rejected["reason"] == "invalid_domain").sum()) if len(rejected) else 0,
        "duplicates": int((rejected["reason"] == "duplicate_domain").sum()) if len(rejected) else 0,
    }
    return IngestionResult(valid=good, rejected=rejected, stats=stats)
