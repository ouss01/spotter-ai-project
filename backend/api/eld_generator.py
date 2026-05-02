"""
Build per-day ELD data: 96-slot resolution, 4×24 duty-status grid, and totals.

The 4×24 grid has one row per duty type (off, sleeper, driving, on-duty N/D).
For each clock hour 0–23, the cell in the row matching the **dominant** status
during that hour is marked active (others empty). This matches paper log “graph” style.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from .hos_engine import HOSSimulationResult

SLOTS_PER_DAY = 96
SLOT_MINUTES = 15

# Display order (rows top → bottom) must match frontend
STATUS_ROWS = (
    "off_duty",
    "sleeper_berth",
    "driving",
    "on_duty_not_driving",
)

STATUS_CODE = {
    "off_duty": "OFF",
    "sleeper_berth": "SB",
    "driving": "D",
    "on_duty_not_driving": "ON",
}

HOUR_LABELS = (
    "12a",
    "1a",
    "2a",
    "3a",
    "4a",
    "5a",
    "6a",
    "7a",
    "8a",
    "9a",
    "10a",
    "11a",
    "12p",
    "1p",
    "2p",
    "3p",
    "4p",
    "5p",
    "6p",
    "7p",
    "8p",
    "9p",
    "10p",
    "11p",
)


def _segment_to_grid_code(status: str) -> str:
    return STATUS_CODE.get(status, "OFF")


def _overlap_minutes(
    a0: datetime, a1: datetime, b0: datetime, b1: datetime
) -> float:
    s = max(a0, b0)
    e = min(a1, b1)
    return max(0.0, (e - s).total_seconds() / 60.0)


def _dominant_status_for_hour(
    segments: list,
    day_start: datetime,
    hour_index: int,
) -> str:
    """Return status with the most overlap in [hour_index, hour_index+1) local to day_start."""
    t0 = day_start + timedelta(hours=hour_index)
    t1 = t0 + timedelta(hours=1)
    best_st = "off_duty"
    best_m = -1.0
    for seg in segments:
        om = _overlap_minutes(seg.start, seg.end, t0, t1)
        if om > best_m:
            best_m = om
            best_st = seg.status
    if best_m <= 1e-9:
        return "off_duty"
    return best_st


def _build_grid_4x24(
    day_segments: list,
    day_start: datetime,
) -> dict[str, Any]:
    """
    For each hour, mark exactly one row as active (true) matching dominant status.
    Returns matrix[row_status][hour] booleans and parallel hour_labels.
    """
    grid: dict[str, list[bool]] = {st: [False] * 24 for st in STATUS_ROWS}
    dominant: list[str] = []
    for h in range(24):
        dom = _dominant_status_for_hour(day_segments, day_start, h)
        dominant.append(dom)
        if dom in grid:
            grid[dom][h] = True
    return {
        "rows": list(STATUS_ROWS),
        "cells": [[grid[st][h] for h in range(24)] for st in STATUS_ROWS],
        "dominant_per_hour": dominant,
        "hour_labels": list(HOUR_LABELS),
    }


def build_daily_logs(result: HOSSimulationResult) -> list[dict[str, Any]]:
    if not result.segments:
        return []

    start_d = result.trip_start.astimezone(timezone.utc).date()
    end_d = result.trip_end.astimezone(timezone.utc).date()
    days: list[date] = []
    d = start_d
    while d <= end_d:
        days.append(d)
        d += timedelta(days=1)

    out: list[dict[str, Any]] = []

    for day_idx, day in enumerate(days):
        day_start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
        day_end = day_start + timedelta(days=1)

        slots = ["OFF"] * SLOTS_PER_DAY
        totals = {
            "driving": 0.0,
            "on_duty_nd": 0.0,
            "off_duty": 0.0,
            "sleeper": 0.0,
        }

        day_segments = [
            s for s in result.segments if s.end > day_start and s.start < day_end
        ]

        for seg in result.segments:
            if seg.end <= day_start or seg.start >= day_end:
                continue
            dur_h = _overlap_minutes(seg.start, seg.end, day_start, day_end) / 60.0
            st = seg.status
            if st == "driving":
                totals["driving"] += dur_h
            elif st == "on_duty_not_driving":
                totals["on_duty_nd"] += dur_h
            elif st == "sleeper_berth":
                totals["sleeper"] += dur_h
            else:
                totals["off_duty"] += dur_h

        for i in range(SLOTS_PER_DAY):
            slot_start = day_start + timedelta(minutes=i * SLOT_MINUTES)
            slot_end = slot_start + timedelta(minutes=SLOT_MINUTES)
            best_code = "OFF"
            best_om = 0.0
            for seg in day_segments:
                om = _overlap_minutes(seg.start, seg.end, slot_start, slot_end)
                if om > best_om:
                    best_om = om
                    best_code = _segment_to_grid_code(seg.status)
            slots[i] = best_code

        grid_4x24 = _build_grid_4x24(day_segments, day_start)

        seg_rows = []
        for seg in result.segments:
            if seg.end <= day_start or seg.start >= day_end:
                continue
            st = seg.status
            seg_rows.append(
                {
                    "start": max(seg.start, day_start).isoformat(),
                    "end": min(seg.end, day_end).isoformat(),
                    "status": st,
                    "code": _segment_to_grid_code(st),
                    "label": seg.label,
                }
            )

        out.append(
            {
                "day": day.isoformat(),
                "day_index": day_idx + 1,
                "slots": slots,
                "grid_4x24": grid_4x24,
                "segments": seg_rows,
                "totals": {k: round(v, 2) for k, v in totals.items()},
            }
        )

    return out


def eld_payload(result: HOSSimulationResult) -> dict[str, Any]:
    days = build_daily_logs(result)
    drive_h = float(result.total_drive_hours)
    # Mirror views reconciliation so ELD totals never stick at 0 incorrectly
    ref_d = max(
        float(getattr(result, "route_drive_hours_osrm", 0) or 0),
        float(getattr(result, "route_drive_hours_55mph", 0) or 0),
        float(result.planned_drive_hours or 0),
    )
    if drive_h < 0.01 and ref_d > 0.01:
        drive_h = ref_d
    return {
        "days": days,
        "hour_labels": list(HOUR_LABELS),
        "trip_start": result.trip_start.isoformat(),
        "trip_end": result.trip_end.isoformat(),
        "totals": {
            "drive_hours": round(drive_h, 2),
            "on_duty_nd_hours": round(result.total_on_duty_nd_hours, 2),
            "planned_drive_hours": round(result.planned_drive_hours, 2),
            "planned_on_duty_nd_hours": round(result.planned_on_duty_nd_hours, 2),
            "route_drive_hours_osrm": round(
                float(getattr(result, "route_drive_hours_osrm", 0) or 0), 2
            ),
            "route_drive_hours_55mph": round(
                float(getattr(result, "route_drive_hours_55mph", 0) or 0), 2
            ),
            "cycle_hours_end": result.cycle_hours_end,
        },
    }
