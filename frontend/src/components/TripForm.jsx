import { useState } from "react";
import "./TripForm.css";

const initial = {
  current_location: "Chicago, IL",
  pickup: "Indianapolis, IN",
  dropoff: "Columbus, OH",
  cycle_used_hours: 12,
  trip_start_iso: "",
};

export default function TripForm({ onSubmit, loading }) {
  const [form, setForm] = useState(initial);

  function update(e) {
    const { name, value } = e.target;
    setForm((f) => ({ ...f, [name]: value }));
  }

  function handleSubmit(e) {
    e.preventDefault();
    onSubmit(form);
  }

  return (
    <form className="trip-form" onSubmit={handleSubmit}>
      <h2 className="trip-form-title">Trip inputs</h2>
      <p className="trip-form-hint">
        Addresses are geocoded with Nominatim. Routing uses OSRM (demo).
      </p>

      <label className="field">
        <span>Current location</span>
        <input
          name="current_location"
          value={form.current_location}
          onChange={update}
          required
          autoComplete="off"
          placeholder="City, state or address"
        />
      </label>

      <label className="field">
        <span>Pickup</span>
        <input
          name="pickup"
          value={form.pickup}
          onChange={update}
          required
          placeholder="Pickup location"
        />
      </label>

      <label className="field">
        <span>Dropoff</span>
        <input
          name="dropoff"
          value={form.dropoff}
          onChange={update}
          required
          placeholder="Final dropoff"
        />
      </label>

      <label className="field">
        <span>Cycle used (0–70 hrs)</span>
        <input
          name="cycle_used_hours"
          type="number"
          min={0}
          max={70}
          step={0.5}
          value={form.cycle_used_hours}
          onChange={update}
          required
        />
      </label>

      <label className="field">
        <span>Trip start (optional, ISO UTC)</span>
        <input
          name="trip_start_iso"
          value={form.trip_start_iso}
          onChange={update}
          placeholder="2026-05-02T14:00:00Z"
          className="mono-input"
        />
      </label>

      <button type="submit" className="submit-btn" disabled={loading}>
        {loading ? "Planning…" : "Plan trip & HOS"}
      </button>
    </form>
  );
}
