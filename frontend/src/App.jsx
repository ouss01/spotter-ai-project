import { useState } from "react";
import TripForm from "./components/TripForm.jsx";
import RouteMap from "./components/RouteMap.jsx";
import ELDLogs from "./components/ELDLogs.jsx";
import { planTrip } from "./services/api.js";
import "./App.css";

export default function App() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  async function handlePlan(form) {
    setLoading(true);
    setError(null);
    try {
      const res = await planTrip({
        current_location: form.current_location,
        pickup: form.pickup,
        dropoff: form.dropoff,
        cycle_used_hours: Number(form.cycle_used_hours),
        trip_start_iso: form.trip_start_iso || undefined,
      });
      setData(res);
    } catch (e) {
      setError(e.message || "Request failed");
      setData(null);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="app">
      <header className="app-header">
        <div className="brand">
          <span className="brand-mark" aria-hidden />
          <div>
            <h1>Spotter Trip Planner</h1>
            <p className="tagline">
              FMCSA property-carrying HOS · 70 hr / 8 day · ELD-style logs
            </p>
          </div>
        </div>
      </header>

      <main className="layout">
        <section className="panel form-panel">
          <TripForm onSubmit={handlePlan} loading={loading} />
          {error && (
            <div className="alert alert-error" role="alert">
              {error}
            </div>
          )}
        </section>

        <section className="panel map-panel">
          <h2 className="panel-title">Route</h2>
          <RouteMap data={data} />
        </section>

        <section className="panel eld-panel">
          <h2 className="panel-title">ELD logs</h2>
          <ELDLogs data={data} />
        </section>
      </main>

      <footer className="app-footer">
        <span>
          Educational demo — verify compliance with current FMCSA / carrier
          policies.
        </span>
      </footer>
    </div>
  );
}
