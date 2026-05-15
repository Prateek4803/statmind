"""
StatMind E11 — Live Data Stream Engine
In-memory ring buffer for real-time measurements.
Accepts POST of individual measurements or batches.
Re-runs SPC on rolling window, alerts on violations.
"""

import numpy as np
from datetime import datetime
from collections import deque
from dataclasses import dataclass, field
from typing import Optional
import threading

# Thread-safe in-memory store: stream_id → StreamBuffer
_streams: dict = {}
_lock = threading.Lock()

WINDOW_SIZE = 200       # keep last N measurements in memory
ALERT_WINDOW = 25       # run SPC on last N points


@dataclass
class StreamPoint:
    index: int
    value: float
    timestamp: str
    alarm: bool
    alarm_rule: str


@dataclass
class StreamStatus:
    stream_id: str
    parameter: str
    n_total: int
    n_window: int
    mean: float
    std: float
    ucl: float
    cl: float
    lcl: float
    last_value: float
    last_alarm: bool
    last_alarm_rule: str
    total_alarms_window: int
    in_control: bool
    usl: Optional[float]
    lsl: Optional[float]
    cpk: Optional[float]
    trend_direction: str        # "up", "down", "stable"
    recent_points: list         # last 50 StreamPoints for chart
    alert_message: str


class StreamBuffer:
    def __init__(self, stream_id: str, parameter: str,
                 usl: float = None, lsl: float = None):
        self.stream_id  = stream_id
        self.parameter  = parameter
        self.usl        = usl
        self.lsl        = lsl
        self.points: deque = deque(maxlen=WINDOW_SIZE)
        self.total_count = 0
        self.created_at  = datetime.now().isoformat()

    def add(self, value: float, timestamp: str = None) -> StreamPoint:
        self.total_count += 1
        ts = timestamp or datetime.now().isoformat()
        # Quick alarm check against rolling mean±3σ
        alarm, rule = self._check_alarm(value)
        pt = StreamPoint(
            index=self.total_count, value=round(float(value), 6),
            timestamp=ts, alarm=alarm, alarm_rule=rule
        )
        self.points.append(pt)
        return pt

    def add_batch(self, values: list, timestamps: list = None) -> list:
        return [self.add(v, timestamps[i] if timestamps and i < len(timestamps) else None)
                for i, v in enumerate(values)]

    def _check_alarm(self, value: float) -> tuple:
        """WE1 alarm: beyond 3σ from rolling mean."""
        arr = np.array([p.value for p in self.points])
        if len(arr) < 8:
            return False, ""
        mean = float(np.mean(arr))
        std  = float(np.std(arr, ddof=1))
        if std == 0:
            return False, ""
        ucl = mean + 3 * std
        lcl = mean - 3 * std
        if value > ucl:
            return True, "WE1-High"
        if value < lcl:
            return True, "WE1-Low"

        # WE4: 8 consecutive on same side
        recent = list(self.points)[-7:] + [StreamPoint(0, value, "", False, "")]
        side = [p.value > mean for p in recent]
        if all(side) or not any(side):
            return True, "WE4"

        return False, ""

    def get_status(self) -> StreamStatus:
        arr = np.array([p.value for p in self.points])
        n   = len(arr)

        if n == 0:
            return StreamStatus(
                stream_id=self.stream_id, parameter=self.parameter,
                n_total=self.total_count, n_window=0,
                mean=0, std=0, ucl=0, cl=0, lcl=0,
                last_value=0, last_alarm=False, last_alarm_rule="",
                total_alarms_window=0, in_control=True,
                usl=self.usl, lsl=self.lsl, cpk=None,
                trend_direction="stable",
                recent_points=[], alert_message="No data yet.",
            )

        mean = float(np.mean(arr))
        std  = float(np.std(arr, ddof=1)) if n > 1 else 0.0
        ucl  = mean + 3 * std
        lcl  = mean - 3 * std

        # Cpk
        cpk = None
        if self.usl and self.lsl and std > 0:
            cpk = round(float(min((self.usl - mean)/(3*std), (mean - self.lsl)/(3*std))), 4)

        # Trend: compare last 5 vs previous 5
        trend = "stable"
        if n >= 10:
            m_recent = float(np.mean(arr[-5:]))
            m_prev   = float(np.mean(arr[-10:-5]))
            delta    = m_recent - m_prev
            if abs(delta) > std * 0.3:
                trend = "up" if delta > 0 else "down"

        alarms = [p for p in self.points if p.alarm]
        last_pt = list(self.points)[-1] if self.points else None
        recent_pts = [
            {"index": p.index, "value": p.value, "timestamp": p.timestamp,
             "alarm": p.alarm, "alarm_rule": p.alarm_rule}
            for p in list(self.points)[-50:]
        ]

        alert_msg = ""
        if alarms and list(self.points)[-1].alarm:
            alert_msg = f"⚠ ALARM: {list(self.points)[-1].alarm_rule} at point {list(self.points)[-1].index} (value={list(self.points)[-1].value:.4f})"

        return StreamStatus(
            stream_id=self.stream_id, parameter=self.parameter,
            n_total=self.total_count, n_window=n,
            mean=round(mean, 5), std=round(std, 5),
            ucl=round(ucl, 5), cl=round(mean, 5), lcl=round(lcl, 5),
            last_value=round(float(last_pt.value), 5) if last_pt else 0,
            last_alarm=last_pt.alarm if last_pt else False,
            last_alarm_rule=last_pt.alarm_rule if last_pt else "",
            total_alarms_window=len(alarms),
            in_control=len(alarms) == 0,
            usl=self.usl, lsl=self.lsl, cpk=cpk,
            trend_direction=trend,
            recent_points=recent_pts,
            alert_message=alert_msg,
        )


# ── Public API ────────────────────────────────────────────────────────────────

def create_stream(stream_id: str, parameter: str,
                  usl: float = None, lsl: float = None) -> StreamStatus:
    with _lock:
        _streams[stream_id] = StreamBuffer(stream_id, parameter, usl, lsl)
    return _streams[stream_id].get_status()


def add_measurement(stream_id: str, value: float,
                    timestamp: str = None) -> StreamStatus:
    with _lock:
        if stream_id not in _streams:
            raise KeyError(f"Stream '{stream_id}' not found. Create it first.")
        _streams[stream_id].add(value, timestamp)
    return _streams[stream_id].get_status()


def add_batch(stream_id: str, values: list,
              timestamps: list = None) -> StreamStatus:
    with _lock:
        if stream_id not in _streams:
            raise KeyError(f"Stream '{stream_id}' not found.")
        _streams[stream_id].add_batch(values, timestamps)
    return _streams[stream_id].get_status()


def get_stream_status(stream_id: str) -> StreamStatus:
    with _lock:
        if stream_id not in _streams:
            raise KeyError(f"Stream '{stream_id}' not found.")
    return _streams[stream_id].get_status()


def list_streams() -> list:
    with _lock:
        return [s.get_status() for s in _streams.values()]


def delete_stream(stream_id: str) -> bool:
    with _lock:
        if stream_id in _streams:
            del _streams[stream_id]
            return True
    return False
