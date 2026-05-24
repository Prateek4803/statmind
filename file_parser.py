"""
file_parser.py — StatMind Universal File Parser
================================================
Parses CSV, Excel (.xlsx/.xls), TSV, and plain-text files into a
normalized DataFrame with detected numeric columns and statistics.

FIXES IN THIS VERSION
---------------------
1. Smart Excel header detection (_find_excel_header_row):
   Scans first 25 rows; finds first row where ≥2 cells are strings
   followed by ≥50% numeric rows.  Fixes "Unexpected token 'I'" crash
   on MQE-style Excel files that have 9 metadata rows before data.

2. All exceptions now raise ParseError (subclass of ValueError) so the
   FastAPI route can catch them and return structured JSON — never HTML.

3. File-size guard (50 MB) before attempting any parse.

4. Column cleaning: strip whitespace from names, drop fully-empty cols.

5. Numeric detection threshold: ≥10 valid values (was implicit ≥0).
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np
import pandas as pd


# ── Custom exception so callers get a clean string, not a traceback ──────────

class ParseError(ValueError):
    """Raised when a file cannot be parsed into a valid numeric DataFrame."""
    pass


# ── Constants ────────────────────────────────────────────────────────────────

MAX_FILE_BYTES = 50 * 1024 * 1024   # 50 MB
MIN_NUMERIC_VALUES = 10              # column must have at least 10 valid numbers
MAX_HEADER_SCAN_ROWS = 25


# ── Column statistics dataclass ───────────────────────────────────────────────

@dataclass
class ColumnStats:
    name: str
    n: int
    mean: float
    std: float
    min: float
    max: float
    q1: float
    q3: float
    n_missing: int = 0       # blank/NaN cells excluded, NEVER coerced to 0
    pct_missing: float = 0.0   # percentage of total rows that are missing


# ── Parse result dataclass ────────────────────────────────────────────────────

@dataclass
class ParseResult:
    df: pd.DataFrame
    numeric_columns: List[str]
    all_columns: List[str]
    column_stats: List[ColumnStats] = field(default_factory=list)
    filename: str = ""
    n_rows: int = 0
    warnings: List[str] = field(default_factory=list)
    source_format: str = "unknown"   # kept for API compatibility
    metadata: dict = field(default_factory=dict)  # kept for API compatibility


# ── Internal helpers ──────────────────────────────────────────────────────────

def _find_excel_header_row(file_bytes: bytes, sheet: int = 0) -> int:
    """
    Auto-detect the real data header row in Excel files that have
    metadata/intro rows above the actual table.

    Strategy:
      For each candidate row i (rows 0..MAX_HEADER_SCAN_ROWS-1):
        1. Row must have ≥ 2 non-empty string cells (column headers).
        2. The next 3 rows must be ≥ 50% numeric (data confirmation).
      Returns the first row meeting both criteria, else 0.
    """
    try:
        df_raw = pd.read_excel(
            io.BytesIO(file_bytes), header=None, sheet_name=sheet
        )
    except Exception:
        return 0

    n_check = min(MAX_HEADER_SCAN_ROWS, len(df_raw))

    for i in range(n_check):
        row = df_raw.iloc[i]
        non_null = row.dropna()
        if len(non_null) < 2:
            continue

        # Must have ≥ 2 string-like header values
        str_vals = [
            v for v in non_null
            if isinstance(v, str) and len(str(v).strip()) > 0
        ]
        if len(str_vals) < 2:
            continue

        # The next 3 rows must be mostly numeric
        if i + 3 >= len(df_raw):
            continue

        next_rows = df_raw.iloc[i + 1 : i + 4]
        numeric_count = 0
        total_count = 0
        for _, r in next_rows.iterrows():
            for v in r.dropna():
                total_count += 1
                try:
                    float(v)
                    numeric_count += 1
                except (ValueError, TypeError):
                    pass

        if total_count > 0 and numeric_count / total_count >= 0.5:
            return i

    return 0


def _detect_separator(text_sample: str) -> str:
    """Detect CSV/TSV separator from first 2 000 characters."""
    counts = {
        "\t":  text_sample.count("\t"),
        ",":   text_sample.count(","),
        ";":   text_sample.count(";"),
        "|":   text_sample.count("|"),
    }
    best = max(counts, key=counts.get)
    return best if counts[best] > 0 else ","


def _compute_stats(series: pd.Series, name: str) -> ColumnStats:
    """Compute descriptive statistics for a single numeric column."""
    clean = series.dropna()
    n = len(clean)
    if n == 0:
        return ColumnStats(
            name=name, n=0, mean=0, std=0, min=0, max=0, q1=0, q3=0,
            n_missing=len(series)
        )
    q1 = float(np.percentile(clean, 25))
    q3 = float(np.percentile(clean, 75))
    return ColumnStats(
        name=name,
        n=n,
        mean=round(float(clean.mean()), 6),
        std=round(float(clean.std(ddof=1)), 6) if n > 1 else 0.0,
        min=round(float(clean.min()), 6),
        max=round(float(clean.max()), 6),
        q1=round(q1, 6),
        q3=round(q3, 6),
        n_missing=int(series.isna().sum()),
    )


def _clean_df(df: pd.DataFrame) -> pd.DataFrame:
    """Strip whitespace from column names and drop fully-empty columns."""
    df.columns = [str(c).strip() for c in df.columns]
    df = df.dropna(axis=1, how="all")
    return df


def _extract_numeric_columns(
    df: pd.DataFrame,
) -> tuple[pd.DataFrame, List[str]]:
    """
    Convert every column that can be numeric to float64.
    Returns (modified_df, list_of_numeric_col_names).
    """
    numeric_cols: List[str] = []
    for col in df.columns:
        coerced = pd.to_numeric(df[col], errors="coerce")
        valid_count = int(coerced.notna().sum())
        if valid_count >= MIN_NUMERIC_VALUES:
            df[col] = coerced
            numeric_cols.append(col)
    return df, numeric_cols


# ── Public API ────────────────────────────────────────────────────────────────

def parse_any_file(file_bytes: bytes, filename: str = "file") -> ParseResult:
    """
    Parse any supported file format into a ParseResult.

    Supported formats
    -----------------
    - .csv, .tsv, .txt  → delimiter-detected text parse
    - .xlsx, .xls       → smart header-row-detected Excel parse

    Raises ParseError on any unrecoverable failure (never raises raw
    exceptions so FastAPI routes always get a clean message to return
    as JSON).
    """
    if len(file_bytes) > MAX_FILE_BYTES:
        raise ParseError(
            f"File is too large ({len(file_bytes) / 1024 / 1024:.1f} MB). "
            f"Maximum allowed size is {MAX_FILE_BYTES // 1024 // 1024} MB."
        )


    # File type guard — reject executables and script files
    _ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    _BLOCKED = {"exe","sh","bat","ps1","js","php","rb","pl","cmd","jar","dll","html","zip","tar"}
    if _ext in _BLOCKED:
        raise ParseError(
            f"File type '.{_ext}' is not allowed. "
            "Accepted formats: .csv .tsv .txt .xlsx .xls"
        )

    warnings: List[str] = []
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""

    try:
        if ext in ("xlsx", "xls"):
            df = _parse_excel(file_bytes, warnings)
        else:
            df = _parse_text(file_bytes, filename, warnings)
    except ParseError:
        raise
    except Exception as exc:
        raise ParseError(f"Could not read file '{filename}': {exc}") from exc

    df = _clean_df(df)

    if df.empty:
        raise ParseError(
            f"No data found in '{filename}'. "
            "Check that the file contains rows below the header."
        )

    df, numeric_cols = _extract_numeric_columns(df)

    if not numeric_cols:
        raise ParseError(
            f"No numeric columns found in '{filename}'. "
            "StatMind needs at least one column with 10+ numeric values."
        )

    col_stats = [_compute_stats(df[c], c) for c in numeric_cols]

    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else "csv"
    fmt_map = {"xlsx": "Excel", "xls": "Excel (legacy)", "csv": "CSV",
               "tsv": "TSV", "txt": "Text"}
    source_fmt = fmt_map.get(ext, ext.upper())

    return ParseResult(
        df=df,
        numeric_columns=numeric_cols,
        all_columns=list(df.columns),
        column_stats=col_stats,
        filename=filename,
        n_rows=len(df),
        warnings=warnings,
        source_format=source_fmt,
        metadata={},
    )


# ── Format-specific parsers ───────────────────────────────────────────────────

def _parse_excel(file_bytes: bytes, warnings: List[str]) -> pd.DataFrame:
    """Parse Excel with auto header-row detection."""
    header_row = _find_excel_header_row(file_bytes)

    if header_row > 0:
        warnings.append(
            f"Detected data starting at row {header_row + 1} "
            f"(skipped {header_row} metadata row(s))."
        )

    try:
        df = pd.read_excel(
            io.BytesIO(file_bytes),
            header=header_row,
            engine="openpyxl",
        )
    except Exception as exc:
        # Try legacy xlrd engine for .xls
        try:
            df = pd.read_excel(
                io.BytesIO(file_bytes),
                header=header_row,
                engine="xlrd",
            )
        except Exception:
            raise ParseError(f"Cannot read Excel file: {exc}") from exc

    return df


def _parse_text(
    file_bytes: bytes, filename: str, warnings: List[str]
) -> pd.DataFrame:
    """Parse CSV / TSV / TXT with auto-separator detection."""
    try:
        text = file_bytes.decode("utf-8-sig")   # handles BOM
    except UnicodeDecodeError:
        try:
            text = file_bytes.decode("latin-1")
            warnings.append("File decoded as Latin-1 (not UTF-8).")
        except Exception as exc:
            raise ParseError(f"Cannot decode file '{filename}': {exc}") from exc

    sep = _detect_separator(text[:2000])

    try:
        df = pd.read_csv(
            io.StringIO(text),
            sep=sep,
            engine="python",
            on_bad_lines="warn",
        )
    except Exception as exc:
        raise ParseError(f"CSV parse failed for '{filename}': {exc}") from exc

    return df


# ── Convenience: column list endpoint helper ──────────────────────────────────

def columns_response(result: ParseResult) -> dict:
    """
    Convert a ParseResult into the dict the /api/v1/columns endpoint returns.
    Kept here so endpoint logic is thin.
    """
    return {
        "columns": [
            {
                "name": s.name,
                "n":    s.n,
                "mean": round(s.mean, 4),
                "std":  round(s.std, 4),
                "min":  round(s.min, 4),
                "max":  round(s.max, 4),
            }
            for s in result.column_stats
        ],
        "all_columns":     result.all_columns,
        "numeric_columns": result.numeric_columns,
        "n_rows":          result.n_rows,
        "warnings":        result.warnings,
    }
