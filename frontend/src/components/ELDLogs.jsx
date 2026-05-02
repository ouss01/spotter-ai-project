import { useCallback, useEffect, useMemo, useState } from "react";
import "./ELDLogs.css";

/** Matches backend HOUR_LABELS (12a … 11p). */
const FALLBACK_HOUR_LABELS = [
  "12a", "1a", "2a", "3a", "4a", "5a", "6a", "7a", "8a", "9a", "10a", "11a",
  "12p", "1p", "2p", "3p", "4p", "5p", "6p", "7p", "8p", "9p", "10p", "11p",
];

/** Coerce API strings/numbers so totals never show NaN or stuck at 0 incorrectly. */
function num(v) {
  if (v == null || v === "") return null;
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : null;
}

const GRID_ROWS = [
  { rowClass: "off-duty-row", label: "Off Duty", rowIdx: 0 },
  { rowClass: "sleeper-row", label: "Sleeper Berth", rowIdx: 1 },
  { rowClass: "driving-row", label: "Driving", rowIdx: 2 },
  { rowClass: "onduty-row", label: "On Duty (N/D)", rowIdx: 3 },
];

const statusColor = {
  driving: "var(--eld-driving)",
  on_duty_not_driving: "var(--eld-on-duty)",
  off_duty: "var(--eld-off-duty)",
  sleeper_berth: "var(--eld-sleeper)",
};

function formatRange(isoStart, isoEnd) {
  try {
    const a = new Date(isoStart);
    const b = new Date(isoEnd);
    const opts = { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" };
    return `${a.toLocaleString(undefined, opts)} → ${b.toLocaleString(undefined, opts)}`;
  } catch {
    return `${isoStart} – ${isoEnd}`;
  }
}

function cycleTier(hours) {
  if (hours > 70) return "over";
  if (hours >= 60) return "warn";
  return "ok";
}

export default function ELDLogs({ data }) {
  const [dayIndex, setDayIndex] = useState(0);

  useEffect(() => {
    setDayIndex(0);
  }, [data]);

  const eld = data?.eld;
  const hos = data?.hos;
  const route = data?.route;
  const days = eld?.days || [];
  const hourLabels = eld?.hour_labels || FALLBACK_HOUR_LABELS;

  const safeIndex = Math.min(dayIndex, Math.max(0, days.length - 1));
  const day = days[safeIndex];

  const tripSpan = useMemo(() => {
    if (!hos?.trip_start || !hos?.trip_end) return null;
    return `${new Date(hos.trip_start).toLocaleDateString()} – ${new Date(hos.trip_end).toLocaleDateString()}`;
  }, [hos]);

  const legsDriveHours = useMemo(() => {
    const legs = data?.legs;
    if (!Array.isArray(legs)) return null;
    let s = 0;
    for (const l of legs) {
      const h = num(l?.duration_hours);
      if (h != null) s += h;
    }
    return s > 0 ? s : null;
  }, [data]);

  /** Prefer reconciled HOS/ELD totals, then route calculator fields. */
  const totalDriveDisplay = useMemo(() => {
    const chain = [
      num(hos?.total_drive_hours),
      num(eld?.totals?.drive_hours),
      num(hos?.planned_drive_hours),
      num(route?.total_driving_hours),
      num(route?.duration_hours),
      num(eld?.totals?.route_drive_hours_osrm),
      num(eld?.totals?.route_drive_hours_55mph),
      num(hos?.route_drive_hours_osrm),
      num(hos?.route_drive_hours_55mph),
      legsDriveHours,
    ];
    for (const v of chain) {
      if (v != null && v > 0.001) return v;
    }
    for (const v of chain) {
      if (v != null) return v;
    }
    return 0;
  }, [hos, eld, route, legsDriveHours]);

  const cycleUsed = num(hos?.cycle_hours_end) ?? 0;
  const cyclePct = Math.min(100, (cycleUsed / 70) * 100);
  const remaining = Math.max(0, 70 - cycleUsed);
  const tier = cycleTier(cycleUsed);

  const exportJson = useCallback(() => {
    if (!data) return;
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `eld-trip-${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }, [data]);

  if (!data) {
    return (
      <div className="eld-logs eld-logs--empty">
        <p>ELD grids and timeline appear after a successful plan.</p>
      </div>
    );
  }

  return (
    <div className="eld-logs">
      <div className="eld-toolbar">
        <button type="button" className="eld-export-btn" onClick={exportJson}>
          Export JSON
        </button>
      </div>

      <div className="eld-summary">
        <div className="eld-stat">
          <span className="eld-stat-label">Trip window</span>
          <span className="eld-stat-value">{tripSpan || "—"}</span>
        </div>
        <div className="eld-stat">
          <span className="eld-stat-label">Total drive</span>
          <span className="eld-stat-value">{totalDriveDisplay.toFixed(2)} h</span>
        </div>
        <div className="eld-stat">
          <span className="eld-stat-label">On-duty N/D</span>
          <span className="eld-stat-value">
            {num(hos?.total_on_duty_nd_hours) != null
              ? num(hos?.total_on_duty_nd_hours).toFixed(2)
              : "—"}{" "}
            h
          </span>
        </div>
        {route?.total_driving_hours != null && (
          <div className="eld-stat">
            <span className="eld-stat-label">Route (OSRM) drive</span>
            <span className="eld-stat-value">{num(route.total_driving_hours)?.toFixed(2)} h</span>
          </div>
        )}
      </div>

      <div className="cycle-progress-section">
        <div className="cycle-progress-header">
          <span>70 h / 8-day on-duty cycle</span>
          <span className="cycle-progress-stats">
            <strong>{cycleUsed.toFixed(1)}</strong> / 70 h used ·{" "}
            <strong>{remaining.toFixed(1)}</strong> h remaining ·{" "}
            <strong>{cyclePct.toFixed(0)}%</strong>
          </span>
        </div>
        <div
          className={`cycle-progress-bar cycle-progress-bar--${tier}`}
          role="progressbar"
          aria-valuenow={cycleUsed}
          aria-valuemin={0}
          aria-valuemax={70}
        >
          <div
            className="cycle-progress-bar-fill progress-fill"
            style={{ width: `${Math.min(100, cyclePct)}%` }}
          />
        </div>
      </div>

      {days.length > 0 && (
        <>
          <div className="eld-tabs" role="tablist" aria-label="Log day selector">
            {days.map((d, i) => (
              <button
                key={d.day}
                type="button"
                role="tab"
                aria-selected={i === safeIndex}
                className={`eld-tab ${i === safeIndex ? "is-active" : ""}`}
                onClick={() => setDayIndex(i)}
              >
                Day {d.day_index ?? i + 1}
                <span className="eld-tab-date">{d.day}</span>
              </button>
            ))}
          </div>

          {day && (
            <>
              <div className="eld-legend">
                <span><i className="sw sw-off-duty" /> Off duty</span>
                <span><i className="sw sw-sleeper" /> Sleeper berth</span>
                <span><i className="sw sw-driving" /> Driving</span>
                <span><i className="sw sw-on-duty" /> On duty (N/D)</span>
              </div>

              <div className="eld-graph-scroll">
                <div className="eld-grid" aria-label="ELD four-line duty graph">
                  <div className="eld-grid-header">
                    <div className="grid-corner" aria-hidden />
                    <div className="grid-hours">
                      {hourLabels.map((lbl, i) => (
                        <span key={i}>{lbl}</span>
                      ))}
                    </div>
                  </div>

                  {GRID_ROWS.map(({ rowClass, label, rowIdx }) => {
                    const cells =
                      day.grid_4x24?.cells?.[rowIdx] ||
                      Array.from({ length: 24 }, () => false);
                    return (
                      <div className={`grid-row ${rowClass}`} key={rowClass}>
                        <div className="row-label">{label}</div>
                        <div className="row-cells">
                          {cells.map((active, hi) => (
                            <div
                              key={hi}
                              className={`cell ${active ? "filled" : "empty"}`}
                              title={`${hourLabels[hi]} · ${label}${active ? "" : " (inactive)"}`}
                              role="presentation"
                            />
                          ))}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>

              <div className="day-totals">
                <span>Driving: {day.totals?.driving ?? 0} h</span>
                <span>On-duty N/D: {day.totals?.on_duty_nd ?? 0} h</span>
                <span>Off duty: {day.totals?.off_duty ?? 0} h</span>
                <span>Sleeper: {day.totals?.sleeper ?? 0} h</span>
              </div>

              <h3 className="timeline-title">Duty timeline (complete trip)</h3>
              <div className="timeline" aria-label="HOS segments timeline">
                {(hos?.segments || []).map((s, idx) => {
                  const dur = (new Date(s.end) - new Date(s.start)) / 36e5;
                  const w = Math.max(0.35, dur * 2.5);
                  return (
                    <div
                      key={idx}
                      className="timeline-block"
                      style={{
                        flexGrow: w,
                        background: statusColor[s.status] || "#555",
                      }}
                      title={`${s.label || s.status} · ${dur.toFixed(2)} h`}
                    />
                  );
                })}
              </div>
              <ul className="segment-list">
                {(hos?.segments || []).map((s, idx) => (
                  <li key={idx}>
                    <div className="seg-row-head">
                      <span className="seg-dot" style={{ background: statusColor[s.status] }} />
                      <span className="seg-status">{s.status.replace(/_/g, " ")}</span>
                      {s.label && <span className="seg-label">{s.label}</span>}
                    </div>
                    <div className="seg-time">{formatRange(s.start, s.end)}</div>
                  </li>
                ))}
              </ul>
            </>
          )}
        </>
      )}
    </div>
  );
}
