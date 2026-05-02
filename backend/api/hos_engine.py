"""
FMCSA property-carrying HOS simulation (educational planner).

Rules modeled:
- Max 11 hours driving after ≥10 consecutive hours off duty
- May not drive after 14 hours on duty (driving + on-duty not driving) without 10h off
- 30-minute off-duty break after 8 hours cumulative driving before more driving
- 70 hours on-duty (driving + ON duty N/D) in any rolling 8-day window
- 34 consecutive hours off duty resets the 70-hour clock (simplified)
- Fuel stop every 1000 miles (~30 min on-duty not driving)
- Pre-trip / post-trip inspections (30 min ON each), pickup / dropoff (1 h ON each)

Driving totals are taken from simulated segments; a fallback sums planned drive tasks
if segment aggregation is ever inconsistent.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal

Status = Literal["driving", "on_duty_not_driving", "off_duty", "sleeper_berth"]

MAX_DRIVING_HOURS = 11.0
MAX_DUTY_WINDOW_HOURS = 14.0
DRIVING_BEFORE_BREAK = 8.0
BREAK_MIN_HOURS = 0.5
OFF_DUTY_RESET_HOURS = 10.0
WEEKLY_RESTART_HOURS = 34.0
WEEKLY_ON_DUTY_MAX = 70.0
WEEKLY_LOOKBACK_DAYS = 8
FUEL_INTERVAL_MI = 1000.0
FUEL_STOP_HOURS = 0.5
PICKUP_DROPOFF_HOURS = 1.0
PRE_POST_INSPECTION_HOURS = 0.5
# Split long planned drives into tasks so timelines show multiple segments (~3.5 h each)
PLANNED_DRIVE_CHUNK_HOURS = 3.5
METERS_PER_MILE = 1609.344
# FMCSA-style planning speed (matches common truck speed limit assumptions)
DEFAULT_TRUCK_MPH = 55.0


@dataclass
class HOSSegment:
    start: datetime
    end: datetime
    status: Status
    label: str = ""


@dataclass
class HOSTask:
    kind: Literal["drive", "on_duty"]
    hours: float
    label: str = ""


@dataclass
class HOSSimulationResult:
    segments: list[HOSSegment]
    trip_start: datetime
    trip_end: datetime
    total_drive_hours: float
    total_on_duty_nd_hours: float
    total_miles: float
    cycle_hours_end: float
    planned_drive_hours: float
    planned_on_duty_nd_hours: float
    # From route (for display / reconciliation); set in views after run()
    route_drive_hours_osrm: float = 0.0
    route_drive_hours_55mph: float = 0.0


def _hours(n: float) -> timedelta:
    return timedelta(seconds=n * 3600.0)


def _split_drive_hours(total_h: float, label_prefix: str) -> list[HOSTask]:
    """Split a long drive into ~3.5 h tasks for clearer labels / timeline."""
    out: list[HOSTask] = []
    rem = max(float(total_h), 0.0)
    n = 0
    while rem > 1e-9:
        chunk = min(PLANNED_DRIVE_CHUNK_HOURS, rem)
        n += 1
        out.append(
            HOSTask(
                "drive",
                chunk,
                f"{label_prefix} (part {n})" if rem > PLANNED_DRIVE_CHUNK_HOURS + 1e-6 else label_prefix,
            )
        )
        rem -= chunk
    return out


def build_tasks_from_legs(
    legs: list[Any],
    meters_to_next_fuel: float = 0.0,
    mph: float = DEFAULT_TRUCK_MPH,
) -> list[HOSTask]:
    """
    Build ordered work tasks: pre-trip → drive to pickup → pickup → main haul
    (with fuel) → post-trip → dropoff.

    Driving durations use leg distance ÷ mph (default 55), not OSRM durations,
    so planned driving hours align with total_distance_miles / 55.

    legs[0]: current → pickup. legs[1]: pickup → dropoff.
    """
    if len(legs) < 2:
        raise ValueError("Expected at least two route legs.")

    tasks: list[HOSTask] = []

    tasks.append(
        HOSTask("on_duty", PRE_POST_INSPECTION_HOURS, "Pre-trip inspection"),
    )

    leg0 = legs[0]
    leg0_mi = float(leg0.distance_m) / METERS_PER_MILE
    h0 = max(leg0_mi / mph, 1e-6)
    tasks.extend(_split_drive_hours(h0, "Drive to pickup"))

    tasks.append(HOSTask("on_duty", PICKUP_DROPOFF_HOURS, "Pickup / loading"))

    main_mi = float(legs[1].distance_m) / METERS_PER_MILE
    if main_mi <= 0:
        tasks.append(
            HOSTask("on_duty", PRE_POST_INSPECTION_HOURS, "Post-trip inspection"),
        )
        tasks.append(HOSTask("on_duty", PICKUP_DROPOFF_HOURS, "Dropoff / unloading"))
        return tasks

    miles_done = 0.0
    fuel_carry = max(meters_to_next_fuel / METERS_PER_MILE, 0.0)

    while miles_done < main_mi - 1e-6:
        room = FUEL_INTERVAL_MI - fuel_carry
        chunk_mi = min(room, main_mi - miles_done)
        chunk_h = max(chunk_mi / mph, 1e-6)
        tasks.extend(
            _split_drive_hours(
                chunk_h,
                f"En route ({chunk_mi:.0f} mi)",
            )
        )
        miles_done += chunk_mi
        fuel_carry += chunk_mi

        if miles_done < main_mi - 1e-6 and fuel_carry >= FUEL_INTERVAL_MI - 1e-6:
            tasks.append(HOSTask("on_duty", FUEL_STOP_HOURS, "Fuel stop"))
            fuel_carry = 0.0

    tasks.append(
        HOSTask("on_duty", PRE_POST_INSPECTION_HOURS, "Post-trip inspection"),
    )
    tasks.append(HOSTask("on_duty", PICKUP_DROPOFF_HOURS, "Dropoff / unloading"))
    return tasks


def _sum_planned_hours(tasks: list[HOSTask]) -> tuple[float, float]:
    d = sum(t.hours for t in tasks if t.kind == "drive")
    o = sum(t.hours for t in tasks if t.kind == "on_duty")
    return d, o


class HOSEngine:
    def __init__(
        self,
        trip_start: datetime,
        cycle_used_hours: float,
    ):
        self.trip_start = trip_start.astimezone(timezone.utc)
        self.now = self.trip_start
        self.segments: list[HOSSegment] = []

        self.driving_since_reset = 0.0
        self.duty_elapsed = 0.0
        self.driving_since_break = 0.0
        self.consecutive_off = 0.0

        cu = max(0.0, min(float(cycle_used_hours), WEEKLY_ON_DUTY_MAX))
        self.daily_on_duty: dict[date, float] = defaultdict(float)
        d0 = self.trip_start.date()
        for i in range(7):
            self.daily_on_duty[d0 - timedelta(days=7 - i)] = cu / 7.0

    def _weekly_total(self) -> float:
        d = self.now.date()
        return sum(
            self.daily_on_duty.get(d - timedelta(days=i), 0.0)
            for i in range(WEEKLY_LOOKBACK_DAYS)
        )

    def _add_daily(self, hours: float) -> None:
        d = self.now.date()
        self.daily_on_duty[d] += hours

    def _prune_old_days(self) -> None:
        d = self.now.date()
        cutoff = d - timedelta(days=WEEKLY_LOOKBACK_DAYS + 2)
        for k in list(self.daily_on_duty.keys()):
            if k < cutoff:
                del self.daily_on_duty[k]

    def _apply_off_segment(self, hours: float, status: Status, label: str) -> None:
        if hours <= 0:
            return
        start = self.now
        self.now = start + _hours(hours)
        self.segments.append(HOSSegment(start, self.now, status, label))
        self.consecutive_off += hours
        self._prune_old_days()

        if self.consecutive_off + 1e-9 >= WEEKLY_RESTART_HOURS:
            self.daily_on_duty.clear()
            self.driving_since_reset = 0.0
            self.duty_elapsed = 0.0
            self.driving_since_break = 0.0
            self.consecutive_off = 0.0
        elif self.consecutive_off + 1e-9 >= OFF_DUTY_RESET_HOURS:
            self.driving_since_reset = 0.0
            self.duty_elapsed = 0.0
            self.driving_since_break = 0.0
            self.consecutive_off = 0.0

    def _ensure_weekly_room(self, need: float) -> None:
        while self._weekly_total() + need > WEEKLY_ON_DUTY_MAX - 1e-6:
            self._apply_off_segment(
                WEEKLY_RESTART_HOURS,
                "off_duty",
                "34-hour restart (70-hour rule)",
            )

    def _ensure_break(self) -> None:
        if self.driving_since_break + 1e-9 < DRIVING_BEFORE_BREAK:
            return
        self._apply_off_segment(BREAK_MIN_HOURS, "off_duty", "30-minute rest break")
        self.driving_since_break = 0.0
        self.consecutive_off = 0.0

    def _ensure_daily_reset(self) -> None:
        if (
            self.driving_since_reset + 1e-9 < MAX_DRIVING_HOURS
            and self.duty_elapsed + 1e-9 < MAX_DUTY_WINDOW_HOURS
        ):
            return
        self._apply_off_segment(
            OFF_DUTY_RESET_HOURS,
            "off_duty",
            "10-hour off-duty reset",
        )

    def _drive_chunk(self, hours: float, label: str) -> None:
        remaining = float(hours)
        guard = 0
        while remaining > 1e-6:
            guard += 1
            if guard > 50000:
                raise RuntimeError("HOS drive simulation exceeded iteration guard")

            self._ensure_weekly_room(min(remaining, MAX_DRIVING_HOURS))
            self.consecutive_off = 0.0

            self._ensure_daily_reset()
            self._ensure_break()

            room_drive = max(0.0, MAX_DRIVING_HOURS - self.driving_since_reset)
            room_duty = max(0.0, MAX_DUTY_WINDOW_HOURS - self.duty_elapsed)
            room_break = max(0.0, DRIVING_BEFORE_BREAK - self.driving_since_break)
            step = min(remaining, room_drive, room_duty, room_break)

            if step < 1e-6:
                self._ensure_daily_reset()
                self._ensure_break()
                continue

            start = self.now
            self.now = start + _hours(step)
            self.segments.append(HOSSegment(start, self.now, "driving", label))
            self.driving_since_reset += step
            self.duty_elapsed += step
            self.driving_since_break += step
            self._add_daily(step)
            remaining -= step
            self._prune_old_days()

    def _on_duty_chunk(self, hours: float, label: str) -> None:
        remaining = float(hours)
        guard = 0
        while remaining > 1e-6:
            guard += 1
            if guard > 50000:
                raise RuntimeError("HOS on-duty simulation exceeded iteration guard")

            self._ensure_weekly_room(min(remaining, MAX_DUTY_WINDOW_HOURS))
            self.consecutive_off = 0.0
            self._ensure_daily_reset()

            room_duty = max(0.0, MAX_DUTY_WINDOW_HOURS - self.duty_elapsed)
            step = min(remaining, room_duty)
            if step < 1e-6:
                self._ensure_daily_reset()
                continue

            start = self.now
            self.now = start + _hours(step)
            self.segments.append(
                HOSSegment(start, self.now, "on_duty_not_driving", label)
            )
            self.duty_elapsed += step
            self._add_daily(step)
            remaining -= step
            self._prune_old_days()

    def run(self, tasks: list[HOSTask]) -> HOSSimulationResult:
        planned_drive, planned_on = _sum_planned_hours(tasks)

        for task in tasks:
            if task.kind == "drive":
                self._drive_chunk(task.hours, task.label or "Driving")
            else:
                self._on_duty_chunk(task.hours, task.label or "On duty")

        drive_h = 0.0
        ond_h = 0.0
        for s in self.segments:
            dur = (s.end - s.start).total_seconds() / 3600.0
            if s.status == "driving":
                drive_h += dur
            elif s.status == "on_duty_not_driving":
                ond_h += dur

        # Planned drive must match simulated unless numerical edge case
        if drive_h < 1e-3 and planned_drive > 1e-3:
            drive_h = planned_drive

        return HOSSimulationResult(
            segments=self.segments,
            trip_start=self.trip_start,
            trip_end=self.now,
            total_drive_hours=round(drive_h, 4),
            total_on_duty_nd_hours=round(ond_h, 4),
            total_miles=0.0,
            cycle_hours_end=round(self._weekly_total(), 2),
            planned_drive_hours=round(planned_drive, 4),
            planned_on_duty_nd_hours=round(planned_on, 4),
            route_drive_hours_osrm=0.0,
            route_drive_hours_55mph=0.0,
        )


def calculate_schedule(
    trip_start: datetime,
    cycle_used_hours: float,
    tasks: list[HOSTask],
    total_distance_miles: float | None = None,
    mph: float = DEFAULT_TRUCK_MPH,
) -> HOSSimulationResult:
    """
    Run the full HOS simulation. If ``total_distance_miles`` is given, the result’s
    ``route_drive_hours_55mph`` is set to total_distance_miles / mph (reference).
    """
    eng = HOSEngine(trip_start, cycle_used_hours)
    out = eng.run(tasks)
    if total_distance_miles is not None and total_distance_miles > 0:
        out.route_drive_hours_55mph = round(float(total_distance_miles) / mph, 4)
    return out


def simulate_hos(
    trip_start: datetime,
    cycle_used_hours: float,
    tasks: list[HOSTask],
) -> HOSSimulationResult:
    return calculate_schedule(trip_start, cycle_used_hours, tasks)
