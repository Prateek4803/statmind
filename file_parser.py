"""
StatMind R1 — Universal File Parser
Handles: CSV (any delimiter), Excel, TSV, space-delimited,
CMM exports (Zeiss CALYPSO, Hexagon PC-DMIS, Renishaw),
Q-DAS, Minitab, JMP, any measurement system output
"""

import io
import re
import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Optional


@dataclass
class ParseResult:
    df: object               # pandas DataFrame (numeric columns only)
    all_columns: list        # all column names found
    numeric_columns: list    # only numeric columns
    metadata: dict           # extracted header metadata (part, operator, machine, date etc)
    source_format: str       # detected format name
    n_rows: int
    n_cols: int
    warnings: list           # any parse warnings


# ── Format detectors ──────────────────────────────────────────────────────────

def detect_format(raw: bytes, filename: str) -> str:
    """Detect the source format from file content and name."""
    fname = filename.lower()
    ext = fname.rsplit('.', 1)[-1] if '.' in fname else ''

    if ext in ('xlsx', 'xls', 'xlsm'):
        return 'excel'
    if ext == 'tsv':
        return 'tsv'

    # Try to decode for text-based detection
    try:
        sample = raw[:4096].decode('utf-8', errors='replace')
    except Exception:
        return 'excel'  # fallback

    sample_lower = sample.lower()

    # PC-DMIS (Hexagon) — starts with measurement plan header
    if any(x in sample_lower for x in ['pc-dmis', 'pcdmis', 'hexagon', 'dmis']):
        return 'pcdmis'

    # CALYPSO (Zeiss) — characteristic blocks
    if any(x in sample_lower for x in ['calypso', 'zeiss', 'characteristic', 'nominal', 'actual', 'deviation']):
        return 'calypso'

    # Renishaw MODUS / CMM
    if any(x in sample_lower for x in ['renishaw', 'modus', 'revo']):
        return 'renishaw'

    # Q-DAS format (K-fields)
    if re.search(r'K\d{4}/', sample):
        return 'qdas'

    # Minitab worksheet
    if 'minitab' in sample_lower or fname.endswith('.mtw') or fname.endswith('.mpj'):
        return 'minitab'

    # JMP
    if 'jmp' in sample_lower or fname.endswith('.jmp'):
        return 'jmp'

    # Generic CSV detection
    lines = [l for l in sample.split('\n') if l.strip()]
    if not lines:
        return 'csv'

    # Count delimiters in data lines
    tab_count   = sum(l.count('\t') for l in lines[:10])
    comma_count = sum(l.count(',')  for l in lines[:10])
    semi_count  = sum(l.count(';')  for l in lines[:10])
    pipe_count  = sum(l.count('|')  for l in lines[:10])
    space_count = sum(len(re.findall(r'\s{2,}', l)) for l in lines[:10])

    counts = {'tsv': tab_count, 'csv': comma_count,
              'ssv': semi_count, 'psv': pipe_count, 'wsv': space_count}
    best = max(counts, key=counts.get)
    return best if counts[best] > 0 else 'csv'


def extract_metadata(lines: list) -> dict:
    """
    Extract metadata from header lines common in CMM/metrology exports.
    Looks for: Part, Operator, Machine, Date, Serial, Program, Revision etc.
    """
    meta = {}
    meta_patterns = [
        (r'part[\s#:_]*[\s:]*([^\n,;]+)',     'part'),
        (r'operator[\s:]*([^\n,;]+)',          'operator'),
        (r'machine[\s:]*([^\n,;]+)',           'machine'),
        (r'serial[\s#:_]*[\s:]*([^\n,;]+)',    'serial'),
        (r'date[\s:]*([^\n,;]+)',              'date'),
        (r'time[\s:]*([^\n,;]+)',              'time'),
        (r'program[\s:]*([^\n,;]+)',           'program'),
        (r'revision[\s:_]*[\s:]*([^\n,;]+)',   'revision'),
        (r'fixture[\s:]*([^\n,;]+)',           'fixture'),
        (r'temperature[\s:]*([^\n,;]+)',       'temperature'),
        (r'drawing[\s#:_]*[\s:]*([^\n,;]+)',   'drawing'),
        (r'customer[\s:]*([^\n,;]+)',          'customer'),
        (r'job[\s#:_]*[\s:]*([^\n,;]+)',       'job'),
        (r'nominal[\s:]*([^\n,;]+)',           'nominal_ref'),
        (r'tolerance[\s:]*([^\n,;]+)',         'tolerance_ref'),
    ]
    header_text = '\n'.join(lines[:30]).lower()
    for pattern, key in meta_patterns:
        m = re.search(pattern, header_text, re.IGNORECASE)
        if m:
            val = m.group(1).strip().strip('"\'').strip()
            if val and len(val) < 80:
                meta[key] = val
    return meta


# ── CMM-specific parsers ──────────────────────────────────────────────────────

def parse_pcdmis(raw: bytes) -> tuple:
    """
    Parse Hexagon PC-DMIS output.
    Typical format: tab-delimited with feature name, nominal, actual, deviation, tol+, tol-
    Header lines start with non-numeric characters.
    """
    text = raw.decode('utf-8', errors='replace')
    lines = text.split('\n')
    meta = extract_metadata(lines)

    # Find data section — look for lines with consistent numeric content
    data_lines = []
    header_line = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        parts = re.split(r'[\t,;|]+', stripped)
        numeric_parts = sum(1 for p in parts if _is_numeric(p.strip()))
        if numeric_parts >= 3:
            if header_line is None:
                # Check if previous line is a header
                for j in range(max(0, i-3), i):
                    prev = lines[j].strip()
                    if prev and not _is_numeric(prev.split()[0] if prev.split() else ''):
                        header_line = prev
                        break
            data_lines.append(stripped)

    if not data_lines:
        return None, meta

    # Parse into dataframe
    sep = _detect_sep('\n'.join(data_lines[:5]))
    buf = io.StringIO('\n'.join(data_lines))
    try:
        df = pd.read_csv(buf, sep=sep, header=None, engine='python', on_bad_lines='skip')
        # Keep only numeric columns
        df = df.apply(pd.to_numeric, errors='coerce')
        df = df.dropna(axis=1, how='all')
        # Name columns based on PC-DMIS convention
        col_names = ['Nominal', 'Actual', 'Deviation', 'Tol_Plus', 'Tol_Minus',
                     'Out_Of_Tol', 'Feature_X', 'Feature_Y', 'Feature_Z']
        df.columns = col_names[:len(df.columns)]
        return df, meta
    except Exception:
        return None, meta


def parse_calypso(raw: bytes) -> tuple:
    """
    Parse Zeiss CALYPSO output (CSV/text export).
    Typical: characteristic name, nominal, actual, deviation, lower tol, upper tol, result
    """
    text = raw.decode('utf-8', errors='replace')
    lines = text.split('\n')
    meta = extract_metadata(lines)

    # CALYPSO exports often have characteristic name in first column
    # Find lines where columns 2+ are numeric
    data_rows = []
    col_names_row = None

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        sep = _detect_sep(stripped)
        parts = [p.strip().strip('"') for p in re.split(sep, stripped)]
        numeric_count = sum(1 for p in parts[1:] if _is_numeric(p))

        if numeric_count >= 3:
            data_rows.append(parts)
        elif i < 20 and any(kw in stripped.lower() for kw in
                            ['nominal', 'actual', 'deviation', 'tolerance', 'result']):
            col_names_row = parts

    if not data_rows:
        return None, meta

    # Build DataFrame
    max_cols = max(len(r) for r in data_rows)
    padded = [r + [''] * (max_cols - len(r)) for r in data_rows]
    df = pd.DataFrame(padded)

    # First column is often feature name — keep as index label
    if not _is_numeric(str(df.iloc[0, 0])):
        feature_names = df.iloc[:, 0].tolist()
        meta['feature_names'] = feature_names
        df = df.iloc[:, 1:]

    df = df.apply(pd.to_numeric, errors='coerce')
    df = df.dropna(axis=1, how='all').dropna(how='all')

    # Standard CALYPSO column order
    calypso_cols = ['Nominal', 'Actual', 'Deviation', 'Tol_Lower', 'Tol_Upper']
    if col_names_row:
        clean = [c.lower().strip() for c in col_names_row[1:]]
        rename_map = {}
        for j, c in enumerate(clean[:len(df.columns)]):
            if 'nominal' in c: rename_map[j] = 'Nominal'
            elif 'actual' in c or 'measured' in c: rename_map[j] = 'Actual'
            elif 'dev' in c: rename_map[j] = 'Deviation'
            elif 'lower' in c or 'minus' in c or '-tol' in c: rename_map[j] = 'Tol_Lower'
            elif 'upper' in c or 'plus' in c or '+tol' in c: rename_map[j] = 'Tol_Upper'
        df.rename(columns={df.columns[k]: v for k, v in rename_map.items()}, inplace=True)
    else:
        df.columns = calypso_cols[:len(df.columns)]

    return df, meta


def parse_qdas(raw: bytes) -> tuple:
    """
    Parse Q-DAS ASCII format (K-fields).
    K0001 = part name, K0004 = characteristic name, K0006 = nominal,
    K0007 = lower tol, K0008 = upper tol, K0001x = measured value
    """
    text = raw.decode('utf-8', errors='replace')
    meta = {}
    characteristics = {}
    values = []
    current_char = None

    for line in text.split('\n'):
        line = line.strip()
        if not line:
            continue
        m = re.match(r'K(\d{4})/(.*)', line)
        if not m:
            continue
        kfield, value = m.group(1), m.group(2).strip()

        if kfield == '0001':
            meta['part'] = value
        elif kfield == '0002':
            meta['order'] = value
        elif kfield == '0003':
            meta['quantity'] = value
        elif kfield == '0004':
            current_char = value
            if current_char not in characteristics:
                characteristics[current_char] = {'nominal': None, 'ltol': None, 'utol': None, 'values': []}
        elif kfield == '0006' and current_char:
            try: characteristics[current_char]['nominal'] = float(value)
            except: pass
        elif kfield == '0007' and current_char:
            try: characteristics[current_char]['ltol'] = float(value)
            except: pass
        elif kfield == '0008' and current_char:
            try: characteristics[current_char]['utol'] = float(value)
            except: pass
        elif kfield.startswith('0001') and len(kfield) > 4 and current_char:
            try: characteristics[current_char]['values'].append(float(value))
            except: pass

    if not characteristics:
        return None, meta

    # Build DataFrame — one column per characteristic
    max_len = max(len(c['values']) for c in characteristics.values()) if characteristics else 0
    data = {}
    for char_name, char_data in characteristics.items():
        vals = char_data['values']
        if vals:
            padded = vals + [np.nan] * (max_len - len(vals))
            data[char_name[:30]] = padded  # truncate long names

    if not data:
        return None, meta

    df = pd.DataFrame(data)
    return df, meta


# ── Generic smart parser ──────────────────────────────────────────────────────

def smart_skip_header(lines: list) -> tuple:
    """
    Find where the actual data starts by scanning for the first line
    where most parts are numeric. Returns (skiprows, header_row, metadata).
    """
    meta = extract_metadata(lines)

    # Look for a header row followed by numeric data
    for i in range(min(30, len(lines))):
        line = lines[i].strip()
        if not line:
            continue
        sep = _detect_sep(line)
        parts = [p.strip().strip('"') for p in re.split(sep, line)]

        # Check if NEXT few lines are numeric
        next_numeric = 0
        for j in range(i+1, min(i+5, len(lines))):
            nxt = lines[j].strip()
            if not nxt:
                continue
            nxt_parts = [p.strip().strip('"') for p in re.split(sep, nxt)]
            if sum(1 for p in nxt_parts if _is_numeric(p)) >= max(2, len(nxt_parts)*0.5):
                next_numeric += 1

        if next_numeric >= 2:
            # This line might be the header
            has_text = any(not _is_numeric(p) for p in parts if p)
            if has_text:
                return i, i, meta  # skip i rows, header at row i
            else:
                return i, None, meta  # data starts here, no header

    return 0, 0, meta


def _detect_sep(sample: str) -> str:
    """Detect separator from a sample string."""
    counts = {
        '\t': sample.count('\t'),
        ',': sample.count(','),
        ';': sample.count(';'),
        '|': sample.count('|'),
    }
    best = max(counts, key=counts.get)
    if counts[best] > 0:
        return best
    # Try multiple spaces
    if re.search(r'\s{2,}', sample):
        return r'\s{2,}'
    return ','


def _is_numeric(s: str) -> bool:
    """Check if string is a number."""
    if not s or s in ('-', '+', '.', 'nan', 'inf', 'N/A', 'NA', '#N/A', ''):
        return False
    s = s.replace(',', '.')  # European decimal
    try:
        float(s)
        return True
    except ValueError:
        return False


def _clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Clean up a parsed dataframe — fix types, drop empties, clean names."""
    # Convert European decimals (1.234,56 → 1234.56)
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].astype(str).str.strip().str.replace(',', '.', regex=False)

    # Coerce to numeric
    df = df.apply(pd.to_numeric, errors='coerce')

    # Drop columns that are >80% NaN
    df = df.dropna(axis=1, thresh=max(1, int(len(df) * 0.2)))
    df = df.dropna(how='all')

    # Clean column names
    df.columns = [str(c).strip().replace(' ', '_').replace('/', '_').replace('\\', '_')
                  .replace('(', '').replace(')', '').replace('[', '').replace(']', '')
                  .strip('_')[:40] for c in df.columns]

    # Deduplicate column names
    seen = {}
    new_cols = []
    for c in df.columns:
        if c in seen:
            seen[c] += 1
            new_cols.append(f"{c}_{seen[c]}")
        else:
            seen[c] = 0
            new_cols.append(c)
    df.columns = new_cols

    return df


# ── Main entry point ──────────────────────────────────────────────────────────

def parse_any_file(file_bytes: bytes, filename: str) -> ParseResult:
    """
    Universal parser. Accepts any measurement/data file.
    Returns ParseResult with DataFrame of numeric columns.
    """
    warnings = []
    fmt = detect_format(file_bytes, filename)
    meta = {}
    df = None

    # ── Excel ──
    if fmt == 'excel':
        try:
            buf = io.BytesIO(file_bytes)
            # Try all sheets, pick the one with most numeric data
            xl = pd.ExcelFile(buf)
            best_df = None
            best_score = 0
            for sheet in xl.sheet_names[:5]:  # max 5 sheets
                try:
                    raw_df = pd.read_excel(buf, sheet_name=sheet, header=None)
                    # Find best header row
                    lines = [str(row.tolist()) for _, row in raw_df.iterrows()]
                    skip, hdr, sheet_meta = smart_skip_header(lines)
                    meta.update(sheet_meta)
                    test_df = pd.read_excel(buf, sheet_name=sheet,
                                            header=hdr, skiprows=skip if hdr == skip else 0)
                    test_df = _clean_dataframe(test_df)
                    numeric_cols = test_df.select_dtypes(include=[np.number]).columns
                    score = len(numeric_cols) * len(test_df)
                    if score > best_score:
                        best_score = score
                        best_df = test_df[numeric_cols] if len(numeric_cols) > 0 else test_df
                except Exception:
                    continue
            df = best_df
        except Exception as e:
            warnings.append(f"Excel parse warning: {e}")

    # ── PC-DMIS ──
    elif fmt == 'pcdmis':
        df, meta = parse_pcdmis(file_bytes)
        if df is None:
            fmt = 'csv'  # fallback

    # ── CALYPSO ──
    elif fmt == 'calypso':
        df, meta = parse_calypso(file_bytes)
        if df is None:
            fmt = 'csv'

    # ── Q-DAS ──
    elif fmt == 'qdas':
        df, meta = parse_qdas(file_bytes)
        if df is None:
            fmt = 'csv'

    # ── Generic text-based ──
    if df is None:
        sep_map = {'csv': ',', 'tsv': '\t', 'ssv': ';', 'psv': '|', 'wsv': r'\s+'}
        sep = sep_map.get(fmt, ',')

        try:
            text = file_bytes.decode('utf-8', errors='replace')
            lines = text.split('\n')
            meta = extract_metadata(lines)
            skip, hdr, _ = smart_skip_header(lines)

            buf = io.StringIO(text)
            kwargs = dict(sep=sep, engine='python', on_bad_lines='skip',
                          encoding_errors='replace')
            if hdr is not None:
                kwargs['header'] = hdr
                kwargs['skiprows'] = list(range(skip)) if skip > 0 and hdr != skip else None
            else:
                kwargs['header'] = None
                if skip > 0:
                    kwargs['skiprows'] = skip

            # Clean up None skiprows
            if kwargs.get('skiprows') is None:
                kwargs.pop('skiprows', None)

            df = pd.read_csv(buf, **kwargs)
            df = _clean_dataframe(df)
        except Exception as e:
            warnings.append(f"Parse error: {e}")
            # Last resort — try every common separator
            for fallback_sep in [',', '\t', ';', '|', ' ']:
                try:
                    buf = io.StringIO(file_bytes.decode('utf-8', errors='replace'))
                    df = pd.read_csv(buf, sep=fallback_sep, engine='python',
                                     on_bad_lines='skip')
                    df = _clean_dataframe(df)
                    if len(df.columns) > 1:
                        break
                except Exception:
                    continue

    if df is None or df.empty:
        raise ValueError(
            f"Could not parse file '{filename}'. "
            "Please ensure it contains numeric measurement data in CSV, Excel, or tab-delimited format."
        )

    # Final cleanup — keep only numeric columns
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    all_cols = df.columns.tolist()

    if not numeric_cols:
        raise ValueError(
            f"No numeric columns found in '{filename}'. "
            "StatMind needs numeric measurement data. "
            "Check that your file has measurement values (not just text labels)."
        )

    numeric_df = df[numeric_cols].copy()

    # Drop columns with fewer than 3 valid values
    valid_cols = [c for c in numeric_cols if numeric_df[c].dropna().count() >= 3]
    if not valid_cols:
        raise ValueError("All columns have fewer than 3 valid measurements.")

    numeric_df = numeric_df[valid_cols]

    return ParseResult(
        df=numeric_df,
        all_columns=all_cols,
        numeric_columns=valid_cols,
        metadata=meta,
        source_format=fmt,
        n_rows=len(numeric_df),
        n_cols=len(valid_cols),
        warnings=warnings,
    )
