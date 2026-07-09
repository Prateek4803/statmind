"""Session M1: multistage dataset generator with known causal ground truth.
These tests pin the DESIGNED cascade so the M2 attribution engine has a
trustworthy fixture — 'given a downstream excursion, was it caused by the
recorded upstream stage at the recorded lag?'"""
import numpy as np
import pandas as pd
import pytest

from multistage_data import generate_multistage_dataset, to_wide


def test_shape_and_schema():
    df, gt = generate_multistage_dataset(n_units=200, n_stages=8)
    assert len(df) == 200 * 8
    assert set(df.columns) == {"unit_id", "stage_index", "stage_name", "value", "timestamp"}
    assert df.stage_index.nunique() == 8
    assert df.unit_id.nunique() == 200
    assert gt.n_stages == 8 and gt.n_units == 200


def test_wide_pivot_preserves_stage_order():
    df, gt = generate_multistage_dataset(n_units=100)
    w = to_wide(df)
    assert len(w) == 100
    cols = [c for c in w.columns if c != "unit_id"]
    assert cols == gt.stage_names


def test_ground_truth_records_downstream_arrivals():
    df, gt = generate_multistage_dataset()
    fault = gt.faults[0]
    assert fault["source_stage"] == 1
    arrivals = fault["downstream_arrivals"]
    # The professor's exact example: stage-1 change reaches stages 3 and 7-8.
    for stage in (3, 7, 8):
        assert stage in arrivals
        assert arrivals[stage]["lag"] >= 1
        assert 0 < arrivals[stage]["gain"] <= 1


def test_lag_increases_downstream():
    _, gt = generate_multistage_dataset()
    arr = gt.faults[0]["downstream_arrivals"]
    # arrival lag at stage 8 must exceed lag at stage 3 (further = later)
    assert arr[8]["lag"] > arr[3]["lag"]


def test_injected_fault_produces_measurable_downstream_shift():
    """The causal claim must be empirically real, not just recorded metadata."""
    df, gt = generate_multistage_dataset(n_units=400, seed=11)
    w = to_wide(df)
    cols = [c for c in w.columns if c != "unit_id"]
    split = 150
    pre, post = w[w.unit_id < split], w[w.unit_id >= split]
    # stage 1 (source) shows the largest shift
    shift_s1 = post[cols[0]].mean() - pre[cols[0]].mean()
    assert shift_s1 > 2.0
    # stages 3 and 7 show a real (smaller) downstream shift
    for k in (3, 7):
        shift = post[cols[k - 1]].mean() - pre[cols[k - 1]].mean()
        assert shift > 0.5, f"stage {k} shift {shift} too small — cascade broken"


def test_lagged_correlation_recovers_causal_link():
    """At the recorded lag, stage-1 must correlate with the downstream stage
    more than a neighbouring wrong lag would — this is what M2 will exploit."""
    df, gt = generate_multistage_dataset(n_units=400, seed=3)
    w = to_wide(df)
    cols = [c for c in w.columns if c != "unit_id"]
    s1 = w[cols[0]].values
    lag3 = gt.faults[0]["downstream_arrivals"][3]["lag"]
    s3 = w[cols[2]].values
    r_at_lag = np.corrcoef(s1[:-lag3], s3[lag3:])[0, 1]
    assert r_at_lag > 0.3, "stage1→stage3 correlation at recorded lag too weak"


def test_custom_fault_at_midline_stage():
    df, gt = generate_multistage_dataset(
        n_units=300,
        faults=[{"source_stage": 3, "unit_start": 100, "unit_end": 300,
                 "magnitude": 4.0, "kind": "step"}])
    fault = gt.faults[0]
    assert fault["source_stage"] == 3
    # a stage-3 fault must NOT propagate upstream to stages 1-2
    assert 1 not in fault["downstream_arrivals"]
    assert 2 not in fault["downstream_arrivals"]
    # but must reach 7-8 via the 3->7 skip link
    assert 7 in fault["downstream_arrivals"]


def test_drift_fault_kind():
    df, gt = generate_multistage_dataset(
        faults=[{"source_stage": 1, "unit_start": 100, "unit_end": 300,
                 "magnitude": 5.0, "kind": "drift"}])
    assert gt.faults[0]["kind"] == "drift"


def test_reproducible_with_seed():
    d1, _ = generate_multistage_dataset(seed=42)
    d2, _ = generate_multistage_dataset(seed=42)
    pd.testing.assert_frame_equal(d1, d2)
