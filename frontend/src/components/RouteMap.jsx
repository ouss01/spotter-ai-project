import { useEffect, useMemo } from "react";
import {
  MapContainer,
  Marker,
  Polyline,
  Popup,
  TileLayer,
  useMap,
} from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import "./RouteMap.css";

import icon from "leaflet/dist/images/marker-icon.png";
import iconRetina from "leaflet/dist/images/marker-icon-2x.png";
import iconShadow from "leaflet/dist/images/marker-shadow.png";

const DefaultIcon = L.icon({
  iconUrl: icon,
  iconRetinaUrl: iconRetina,
  shadowUrl: iconShadow,
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
  shadowSize: [41, 41],
});
L.Marker.prototype.options.icon = DefaultIcon;

function FitRoute({ positions }) {
  const map = useMap();
  useEffect(() => {
    if (!positions?.length) return;
    const b = L.latLngBounds(positions);
    map.fitBounds(b, { padding: [28, 28], maxZoom: 8 });
  }, [map, positions]);
  return null;
}

const waypointColors = {
  current: "#3d8bfd",
  pickup: "#fbbf24",
  dropoff: "#34d399",
};

export default function RouteMap({ data }) {
  const positions = useMemo(() => {
    if (!data?.route?.coordinates?.length) return [];
    return data.route.coordinates.map(([lon, lat]) => [lat, lon]);
  }, [data]);

  const center = positions[0] || [39.8, -98.5];
  const summary = data?.route;
  const waypoints = data?.waypoints || [];

  if (!data) {
    return (
      <div className="route-map route-map--empty">
        <p>Submit the form to load the route and waypoints.</p>
      </div>
    );
  }

  return (
    <div className="route-map">
      <div className="route-meta">
        {summary && (
          <>
            <span>
              <strong>{summary.distance_miles}</strong> mi
            </span>
            <span>
              Road time ~<strong>{summary.duration_hours}</strong> h (pre-HOS)
            </span>
          </>
        )}
      </div>
      <MapContainer
        center={center}
        zoom={6}
        className="route-map-inner"
        scrollWheelZoom
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        {positions.length > 1 && (
          <Polyline
            positions={positions}
            pathOptions={{ color: "#3d8bfd", weight: 5, opacity: 0.85 }}
          />
        )}
        <FitRoute positions={positions} />
        {waypoints.map((wp) => (
          <Marker key={wp.key} position={[wp.lat, wp.lon]}>
            <Popup>
              <strong style={{ color: waypointColors[wp.key] || "#fff" }}>
                {wp.key}
              </strong>
              <br />
              {wp.label}
            </Popup>
          </Marker>
        ))}
      </MapContainer>
    </div>
  );
}
