"""
tests/test_statistical_engines.py
===================================
Unit tests for StatMind's statistical engines.
Run with:  python -m pytest tests/ -v

These tests exist to catch:
- Statistical regressions when scipy/numpy versions change
- Silent formula bugs after refactors
- Edge cases that break production analyses
"""

import math
import sys
import io
import openpyxl

import numpy as np
import pytest

sys.path.insert(0, ".")

# ── outliers ─────────────────────────────────────────────────────────────────

from outliers import detect_outliers, OutlierResult


class TestGrubbs:
    def test_detects_clear_outlier(self):
        rng  = np.random.default_rng(42)
        data = rng.normal(100.0, 5.0, 50)
        data[10] = 140.0  # 8-sigma outlier
        r = detect_outliers(data, "col", method="grubbs", alpha=0.05)
        assert r.n_outliers >= 1
        indices = [o.index for o in r.outliers]
        assert 10 in indices, f"Index 10 not flagged; got {indices}"

    def test_no_false_positive_clean_data(self):
        rng  = np.random.default_rng(0)
        data = rng.normal(100.0, 5.0, 100)
        r = detect_outliers(data, "col", method="grubbs", alpha=0.05)
        # Allow at most 1 false positive in perfectly normal data
        assert r.n_outliers <= 1

    def test_minimum_n_guard(self):
        # n < 7 should return no outliers (Grubbs requires n >= 7)
        r = detect_outliers(np.array([1.0, 2.0, 100.0]), "col", method="grubbs")
        assert r.n_outliers == 0

    def test_z_scores_sorted_descending(self):
        rng  = np.random.default_rng(1)
        data = rng.normal(0, 1, 50)
        data[5] = 8.0
        data[20] = 7.0
        r = detect_outliers(data, "col", method="grubbs")
        if len(r.outliers) >= 2:
            assert r.outliers[0].z_score >= r.outliers[1].z_score


class TestDixonQ:
    def test_detects_outlier_small_sample(self):
        # n=10, clear max outlier
        data = np.array([1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 9.9])
        r = detect_outliers(data, "col", method="dixon", alpha=0.05)
        assert r.n_outliers >= 1
        vals = [o.value for o in r.outliers]
        assert 9.9 in vals

    def test_not_applied_for_large_n(self):
        rng  = np.random.default_rng(42)
        data = rng.normal(0, 1, 50)
        data[0] = 100.0
        r = detect_outliers(data, "col", method="dixon")
        # Dixon Q should not run for n > 30 (only Grubbs/ESD)
        assert all(o.method != "Dixon Q" for o in r.outliers)


class TestRosnerESD:
    def test_detects_multiple_outliers(self):
        rng  = np.random.default_rng(7)
        data = rng.normal(50.0, 3.0, 60)
        data[5]  = 80.0
        data[10] = 75.0
        r = detect_outliers(data, "col", method="esd", alpha=0.05)
        indices = [o.index for o in r.outliers]
        assert 5  in indices, "Index 5 (80.0) not flagged"
        assert 10 in indices, "Index 10 (75.0) not flagged"

    def test_not_applied_for_small_n(self):
        data = np.arange(20, dtype=float)
        r = detect_outliers(data, "col", method="esd")
        assert all(o.method != "Rosner ESD" for o in r.outliers)


class TestOutliersEdgeCases:
    def test_constant_array(self):
        data = np.ones(50)
        r = detect_outliers(data, "col")
        assert r.n_outliers == 0

    def test_nan_values_stripped(self):
        # [1, 2, NaN, 3, 4] × 20 = 100 total; 20 NaN stripped → n=80
        data = np.array([1.0, 2.0, np.nan, 3.0, 4.0] * 20)
        r = detect_outliers(data, "col")
        assert r.n == 80   # 4 valid per chunk × 20 chunks
        assert r.n_outliers >= 0

    def test_mq_dataset1_known_outliers(self):
        """
        MQE Dataset 1 (Nominal=1.5, n=100) has two known Grubbs outliers:
        - Run #16 (index 15), value ≈ 1.525, z ≈ 4.62
        - Run #74 (index 73), value ≈ 1.515, z ≈ 3.81
        This test uses synthetic data matching those statistics.
        """
        rng  = np.random.default_rng(99)
        data = rng.normal(1.489, 0.0078, 100)
        data[15] = 1.525
        data[73] = 1.515

        r = detect_outliers(data, "Dataset 1", method="grubbs", alpha=0.05)
        indices = [o.index for o in r.outliers]
        assert 15 in indices, f"Run 16 not flagged; outliers at {indices}"
        assert 73 in indices, f"Run 74 not flagged; outliers at {indices}"


# ── equivalence_test ──────────────────────────────────────────────────────────

from equivalence_test import tost_equivalence, EquivalenceResult


class TestTOST:
    def test_equivalent_datasets(self):
        """Two groups from same distribution should be equivalent at 5% margin."""
        rng = np.random.default_rng(42)
        a   = rng.normal(1.499, 0.008, 100)
        b   = rng.normal(1.501, 0.015, 100)
        r   = tost_equivalence(a, b, delta=0.074, alpha=0.05)
        assert r.equivalent, f"Expected EQUIVALENT; CI=[{r.confidence_interval['lower']:.4f},{r.confidence_interval['upper']:.4f}]"

    def test_non_equivalent_large_shift(self):
        rng = np.random.default_rng(0)
        a   = rng.normal(1.50, 0.01, 100)
        b   = rng.normal(1.55, 0.01, 100)   # 0.05 shift >> delta=0.005
        r   = tost_equivalence(a, b, delta=0.005, alpha=0.05)
        assert not r.equivalent

    def test_welch_df_not_overflowed(self):
        """
        Core regression test: the previous bug caused df≈0.07 for
        small-variance matched data (std≈0.008 and 0.015, n=100 each).
        After the fix, df should be ≈150.
        """
        rng = np.random.default_rng(0)
        a   = rng.normal(1.499, 0.008, 100)
        b   = rng.normal(1.501, 0.015, 100)
        r   = tost_equivalence(a, b, delta=0.074, alpha=0.05)
        assert r.welch_df > 50.0, f"df overflow not fixed: df={r.welch_df:.2f}"
        assert r.welch_df < 300.0, f"df unreasonably large: df={r.welch_df:.2f}"

    def test_ci_is_sane(self):
        """CI should never be ±billions."""
        rng = np.random.default_rng(3)
        a   = rng.normal(1.499, 0.008, 100)
        b   = rng.normal(1.501, 0.015, 100)
        r   = tost_equivalence(a, b, delta=0.074, alpha=0.05)
        lo  = r.confidence_interval["lower"]
        hi  = r.confidence_interval["upper"]
        assert abs(lo) < 10.0, f"CI lower is unreasonable: {lo}"
        assert abs(hi) < 10.0, f"CI upper is unreasonable: {hi}"

    def test_default_delta_five_percent(self):
        rng = np.random.default_rng(5)
        a   = rng.normal(2.0, 0.1, 50)
        r   = tost_equivalence(a, a + rng.normal(0, 0.001, 50), delta=None)
        # delta defaults to |mean_a| * 0.05
        assert abs(r.delta - 2.0 * 0.05) < 0.02

    def test_raises_on_too_few_values(self):
        with pytest.raises(ValueError, match="need ≥ 3"):
            tost_equivalence(np.array([1.0, 2.0]), np.array([1.0, 2.0] * 20))


# ── file_parser ───────────────────────────────────────────────────────────────

from file_parser import parse_any_file, _find_excel_header_row, ParseError


class TestFileParser:
    def _make_excel_with_metadata(self, n_meta_rows: int = 9) -> bytes:
        """Build a synthetic Excel file with metadata rows before data."""
        wb = openpyxl.Workbook()
        ws = wb.active
        for _ in range(n_meta_rows - 1):
            ws.append(["meta info", None])
        ws.append(["Run Order", "Value A", "Value B"])
        rng = np.random.default_rng(7)
        for i in range(1, 51):
            ws.append([i,
                       round(float(rng.normal(100, 5)), 3),
                       round(float(rng.normal(200, 8)), 3)])
        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()

    def test_detects_header_row(self):
        excel_bytes = self._make_excel_with_metadata(9)
        row = _find_excel_header_row(excel_bytes)
        assert row == 9 - 1, f"Expected header at row 8, got {row}"

    def test_parses_data_correctly(self):
        excel_bytes = self._make_excel_with_metadata(9)
        result = parse_any_file(excel_bytes, "test.xlsx")
        assert "Value A" in result.numeric_columns
        assert "Value B" in result.numeric_columns
        assert result.n_rows == 50

    def test_no_metadata_rows_fallback(self):
        excel_bytes = self._make_excel_with_metadata(0)
        result = parse_any_file(excel_bytes, "test.xlsx")
        assert result.n_rows > 0

    def test_csv_comma_separated(self):
        # Build CSV with known row count — no trailing blank lines
        rows = "\n".join(["A,B,C"] + ["1.0,2.0,3.0", "4.0,5.0,6.0", "7.0,8.0,9.0"] * 5)
        result = parse_any_file(rows.encode(), "test.csv")
        assert set(result.numeric_columns) == {"A", "B", "C"}
        assert result.n_rows == 15

    def test_csv_tab_separated(self):
        tsv = "X\tY\n1.0\t2.0\n3.0\t4.0\n" * 10
        result = parse_any_file(tsv.encode(), "test.tsv")
        assert "X" in result.numeric_columns

    def test_raises_on_oversized_file(self):
        # 51MB of zeros — exceeds the 50MB limit
        big = b"A\n" + b"1\n" * (51 * 1024 * 1024 // 2)
        with pytest.raises(ParseError, match="too large"):
            parse_any_file(big, "big.csv")

    def test_raises_on_no_numeric_columns(self):
        csv = "Name,City\nAlice,NYC\nBob,LA\n"
        with pytest.raises(ParseError, match="No numeric columns"):
            parse_any_file(csv.encode(), "text.csv")

    def test_raises_on_empty_file(self):
        with pytest.raises(ParseError):
            parse_any_file(b"", "empty.csv")

    def test_column_stats_correct(self):
        data = np.linspace(1.0, 100.0, 100)
        csv  = "val\n" + "\n".join(str(v) for v in data) + "\n"
        result = parse_any_file(csv.encode(), "test.csv")
        s = result.column_stats[0]
        assert abs(s.mean - 50.5) < 0.1
        assert s.n == 100


# ── integration: pipeline ─────────────────────────────────────────────────────

class TestPipeline:
    """End-to-end: parse → outlier detect → equivalence test."""

    def test_full_mq_pipeline(self):
        """
        Simulate the MQE analysis pipeline:
        parse Excel → outlier detection → TOST equivalence.
        """
        # Build synthetic MQE-like Excel
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["Prototype 1 Build"])
        ws.append(["- Same Dimension"])
        ws.append([None])
        ws.append(["Nominal:", 1.5])
        ws.append(["USL:", 1.53])
        ws.append(["LSL:", 1.47])
        ws.append([None])
        ws.append([None])
        ws.append([None])
        ws.append(["Run Order", "Dataset 1", "Dataset 2"])
        rng = np.random.default_rng(42)
        d1_vals, d2_vals = [], []
        for i in range(1, 101):
            v1 = round(float(rng.normal(1.489, 0.0078)), 6)
            v2 = round(float(rng.normal(1.499, 0.0145)), 6)
            d1_vals.append(v1); d2_vals.append(v2)
            ws.append([i, v1, v2])
        buf = io.BytesIO(); wb.save(buf)

        # 1. Parse
        result = parse_any_file(buf.getvalue(), "mq_test.xlsx")
        assert "Dataset 1" in result.numeric_columns
        assert "Dataset 2" in result.numeric_columns
        assert result.n_rows == 100

        # 2. Outlier detection on Dataset 1
        d1 = result.df["Dataset 1"].dropna().values.astype(float)
        out_r = detect_outliers(d1, "Dataset 1", method="all", alpha=0.05)
        assert isinstance(out_r.n_outliers, int)
        assert isinstance(out_r.summary, str)

        # 3. TOST equivalence
        d2 = result.df["Dataset 2"].dropna().values.astype(float)
        eq_r = tost_equivalence(d1, d2, delta=None, alpha=0.05)
        assert isinstance(eq_r.equivalent, bool)
        # Welch df must be sane
        assert 50 < eq_r.welch_df < 300
        # CI must be sane
        assert abs(eq_r.confidence_interval["lower"]) < 1.0
        assert abs(eq_r.confidence_interval["upper"]) < 1.0

        print(f"\nPipeline result: "
              f"Outliers={out_r.n_outliers}, "
              f"Equivalent={eq_r.equivalent}, "
              f"Welch_df={eq_r.welch_df:.1f}")
