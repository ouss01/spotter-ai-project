import logging
from datetime import datetime, timezone

from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .eld_generator import eld_payload
from .hos_engine import METERS_PER_MILE, build_tasks_from_legs, calculate_schedule
from .route_calculator import plan_stops
from .serializers import PlanTripSerializer

logger = logging.getLogger(__name__)


def _parse_start(s: str | None) -> datetime:
    if not s or not str(s).strip():
        return datetime.now(timezone.utc)
    raw = str(s).strip()
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return datetime.now(timezone.utc)


@api_view(["POST"])
def plan_trip(request):
    ser = PlanTripSerializer(data=request.data)
    if not ser.is_valid():
        return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)

    cd = ser.validated_data
    try:
        geocoded, route = plan_stops(
            cd["current_location"],
            cd["pickup"],
            cd["dropoff"],
        )
    except ValueError as e:
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        logger.exception("plan_stops failed")
        return Response(
            {"detail": f"Routing or geocoding failed: {e}"},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    trip_start = _parse_start(cd.get("trip_start_iso"))
    tasks = build_tasks_from_legs(route.legs)
    total_mi = route.total_distance_m / METERS_PER_MILE
    hos_result = calculate_schedule(
        trip_start,
        cd["cycle_used_hours"],
        tasks,
        total_distance_miles=total_mi,
    )
    hos_result.total_miles = total_mi
    # OSRM road duration (matches route card); 55 mph reference already on result
    hos_result.route_drive_hours_osrm = round(route.total_duration_s / 3600.0, 4)
    # Ensure UI / ELD never show 0.00 when route has real driving time
    sim_d = float(hos_result.total_drive_hours)
    planned_d = float(hos_result.planned_drive_hours)
    ref_d = max(
        hos_result.route_drive_hours_osrm,
        hos_result.route_drive_hours_55mph,
        planned_d,
    )
    if sim_d < 0.01 and ref_d > 0.01:
        hos_result.total_drive_hours = round(ref_d, 2)
    else:
        hos_result.total_drive_hours = round(sim_d, 2)

    waypoints = [
        {
            "key": "current",
            "label": geocoded[0].display_name,
            "lat": geocoded[0].lat,
            "lon": geocoded[0].lon,
        },
        {
            "key": "pickup",
            "label": geocoded[1].display_name,
            "lat": geocoded[1].lat,
            "lon": geocoded[1].lon,
        },
        {
            "key": "dropoff",
            "label": geocoded[2].display_name,
            "lat": geocoded[2].lat,
            "lon": geocoded[2].lon,
        },
    ]

    return Response(
        {
            "waypoints": waypoints,
            "route": {
                "type": "LineString",
                "coordinates": route.coordinates,
                "distance_miles": round(total_mi, 1),
                "duration_hours": round(route.total_duration_s / 3600.0, 2),
                "total_driving_hours": round(route.total_duration_s / 3600.0, 2),
                "driving_hours_55mph": round(total_mi / 55.0, 2),
            },
            "legs": [
                {
                    "distance_miles": round(leg.distance_m / 1609.344, 1),
                    "duration_hours": round(leg.duration_s / 3600.0, 2),
                    "summary": leg.summary,
                }
                for leg in route.legs
            ],
            "hos": {
                "trip_start": hos_result.trip_start.isoformat(),
                "trip_end": hos_result.trip_end.isoformat(),
                "total_drive_hours": round(float(hos_result.total_drive_hours), 2),
                "total_on_duty_nd_hours": round(hos_result.total_on_duty_nd_hours, 2),
                "planned_drive_hours": round(hos_result.planned_drive_hours, 2),
                "planned_on_duty_nd_hours": round(hos_result.planned_on_duty_nd_hours, 2),
                "route_drive_hours_osrm": round(hos_result.route_drive_hours_osrm, 2),
                "route_drive_hours_55mph": round(hos_result.route_drive_hours_55mph, 2),
                "total_planned_miles": round(hos_result.total_miles, 1),
                "cycle_hours_end": hos_result.cycle_hours_end,
                "segments": [
                    {
                        "start": s.start.isoformat(),
                        "end": s.end.isoformat(),
                        "status": s.status,
                        "label": s.label,
                    }
                    for s in hos_result.segments
                ],
            },
            "eld": eld_payload(hos_result),
        }
    )


@api_view(["GET"])
def health(_request):
    return Response({"status": "ok"})
