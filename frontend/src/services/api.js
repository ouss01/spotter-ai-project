const base = (import.meta.env.VITE_API_URL || "").replace(/\/$/, "");

function url(path) {
  if (base) return `${base}${path}`;
  return path;
}

export async function planTrip(body) {
  const res = await fetch(url("/api/plan-trip/"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const msg =
      typeof data.detail === "string"
        ? data.detail
        : Array.isArray(data.detail)
          ? data.detail.map((e) => e.msg || e).join("; ")
          : JSON.stringify(data);
    throw new Error(msg || res.statusText);
  }
  return data;
}
