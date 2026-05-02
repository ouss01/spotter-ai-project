# Spotter — FMCSA HOS trip planner

Full-stack demo: **Django REST** API (geocoding + routing + HOS simulation) and **React (Vite)** UI with **Leaflet** maps and **ELD-style** daily grids.

## Features

- **POST `/api/plan-trip/`** — Nominatim geocoding, OSRM driving route (current → pickup → dropoff), HOS-aware schedule.
- **Property-carrying-style rules (simplified):** 11 h driving, 14 h duty window, 30 min break after 8 h driving, 10 h off-duty reset, **70 h / 8-day** cap with **34 h** off to restart the weekly ledger in this planner, **fuel** every **1000 mi** (~30 min on-duty), **1 h** pickup and **1 h** dropoff on-duty not driving.
- **React UI:** form, route map with waypoints, tabbed ELD day view (96×15 min grid), duty timeline, cycle progress bar.

> This is an **educational planner**, not certified ELD software. Always confirm compliance with FMCSA and your motor carrier.

## Local development

### Backend

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver 0.0.0.0:8000
```

Health check: `GET http://127.0.0.1:8000/api/health/`

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Vite proxies `/api` to `http://127.0.0.1:8000`, so leave `VITE_API_URL` unset for local dev.

### API request body

```json
{
  "current_location": "Chicago, IL",
  "pickup": "Denver, CO",
  "dropoff": "Salt Lake City, UT",
  "cycle_used_hours": 15.5,
  "trip_start_iso": "2026-05-02T14:00:00Z"
}
```

`trip_start_iso` is optional (defaults to now, UTC).

---

## Deploy: Render (backend)

1. Create a **Web Service** on [Render](https://render.com).
2. Connect your repo; set **Root Directory** to `backend`.
3. **Build command:** `pip install -r requirements.txt && python manage.py migrate`
4. **Start command:** `gunicorn backend.wsgi:application --bind 0.0.0.0:$PORT`
5. **Environment variables:**
   - `DJANGO_SECRET_KEY` — long random string
   - `DJANGO_DEBUG` — `false`
   - `ALLOWED_HOSTS` — your service hostname, e.g. `your-api.onrender.com`
   - `CORS_ALLOWED_ORIGINS` — your Vercel frontend URL, e.g. `https://your-app.vercel.app`

After deploy, note the API origin, e.g. `https://your-api.onrender.com`.

---

## Deploy: Vercel (frontend)

1. Import the repo in [Vercel](https://vercel.com).
2. Set **Root Directory** to `frontend`.
3. **Framework preset:** Vite.
4. **Build command:** `npm run build`
5. **Output directory:** `dist`
6. **Environment variable:**
   - `VITE_API_URL` — Render API origin **without** trailing slash, e.g. `https://your-api.onrender.com`

The frontend calls `POST ${VITE_API_URL}/api/plan-trip/`.

7. Redeploy after changing env vars.

---

## Project layout

- `backend/api/route_calculator.py` — Nominatim + OSRM.
- `backend/api/hos_engine.py` — HOS simulation.
- `backend/api/eld_generator.py` — Per-day 24 h grids from segments.
- `backend/api/views.py` — `plan_trip` view.
- `frontend/src/components/*` — `TripForm`, `RouteMap`, `ELDLogs`.
- `frontend/src/services/api.js` — API client.

## External services

- [Nominatim](https://nominatim.org/) — use per their [usage policy](https://operations.osmfoundation.org/policies/nominatim/) (throttling applied in code).
- [OSRM demo server](https://router.project-osrm.org/) — suitable for demos; production apps should host their own routing engine.
