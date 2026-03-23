const API_BASE = "http://127.0.0.1:8000";

if (typeof L === "undefined") {
  throw new Error("Leaflet failed to load. Check internet/CDN access.");
}

const map = L.map("map", { zoomControl: true }).setView([12.9716, 77.5946], 11);
const osm = L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  attribution: "&copy; OpenStreetMap",
});
const carto = L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png", {
  maxZoom: 20,
  attribution: "&copy; OpenStreetMap &copy; CARTO",
});
osm.addTo(map);
let tileFallbackUsed = false;
osm.on("tileerror", () => {
  if (!tileFallbackUsed) {
    tileFallbackUsed = true;
    map.removeLayer(osm);
    carto.addTo(map);
    console.warn("OSM tiles failed; switched to CARTO fallback.");
  }
});
setTimeout(() => map.invalidateSize(), 100);

const hub = [12.9716, 77.5946];
let startMarker = L.circleMarker(hub, {
  radius: 7,
  color: "#15803d",
  fillColor: "#22c55e",
  fillOpacity: 1,
}).addTo(map).bindPopup("Start: Bangalore Central");
let destMarker = null;

const routeLines = [];
const vehicleMarker = L.marker(hub, { title: "Vehicle" }).addTo(map);
window.currentRoute = null;

let timer = null;
let animationTimer = null;
let selectedRouteCoordinates = [];
let animationIndex = 0;

const fuelEl = document.getElementById("fuel");
const trafficEl = document.getElementById("traffic");
const qstateEl = document.getElementById("qstate");
const decisionEl = document.getElementById("decision");
const rewardEl = document.getElementById("reward");
const distanceEl = document.getElementById("distance");
const statusEl = document.getElementById("status");
const routesListEl = document.getElementById("routesList");
const directionsListEl = document.getElementById("directionsList");
const qtableListEl = document.getElementById("qtableList");
const startBtn = document.getElementById("startBtn");
const destinationInput = document.getElementById("destination");

function clearAltRoutes() {
  while (routeLines.length) {
    map.removeLayer(routeLines.pop());
  }
}

function renderRouteOptions(routes, selectedRoute) {
  if (window.currentRoute) {
    map.removeLayer(window.currentRoute);
    window.currentRoute = null;
  }
  clearAltRoutes();
  routesListEl.innerHTML = "";
  routes.forEach((route, idx) => {
    const isSelected = idx + 1 === selectedRoute;
    const line = L.polyline(route.coordinates, {
      color: isSelected ? "#2563eb" : "#9aa8c2",
      weight: isSelected ? 6 : 4,
      opacity: isSelected ? 0.9 : 0.75,
      dashArray: isSelected ? null : "8,10",
      smoothFactor: 1,
    }).addTo(map);
    if (isSelected) {
      window.currentRoute = line;
    } else {
      routeLines.push(line);
    }

    const li = document.createElement("li");
    li.textContent = `Route ${idx + 1} (${route.label}) - ${route.distance_km.toFixed(2)} km, ${route.duration_min.toFixed(1)} min`;
    if (isSelected) li.style.fontWeight = "700";
    routesListEl.appendChild(li);
  });
}

function stopAnimation() {
  if (animationTimer) {
    clearTimeout(animationTimer);
    animationTimer = null;
  }
}

function moveCar() {
  if (!selectedRouteCoordinates.length) return;
  if (animationIndex >= selectedRouteCoordinates.length) return;
  vehicleMarker.setLatLng(selectedRouteCoordinates[animationIndex]);
  animationIndex += 1;
  animationTimer = setTimeout(moveCar, 50);
}

function renderDirections(steps) {
  directionsListEl.innerHTML = "";
  if (!steps || !steps.length) {
    const li = document.createElement("li");
    li.textContent = "No route instructions available.";
    directionsListEl.appendChild(li);
    return;
  }
  steps.slice(0, 8).forEach((step) => {
    const li = document.createElement("li");
    const km = (step.distance_m / 1000).toFixed(2);
    li.textContent = `${step.instruction} (${km} km)`;
    directionsListEl.appendChild(li);
  });
}

function renderQTable(rows) {
  qtableListEl.innerHTML = "";
  if (!rows || !rows.length) {
    const li = document.createElement("li");
    li.textContent = "No learned entries yet.";
    qtableListEl.appendChild(li);
    return;
  }
  rows.forEach((row) => {
    const li = document.createElement("li");
    li.textContent = `${row.traffic}/${row.fuel_bucket} -> ${row.action}: ${row.q_value.toFixed(3)}`;
    qtableListEl.appendChild(li);
  });
}

async function refreshQTable() {
  try {
    const res = await fetch(`${API_BASE}/qtable?limit=8`);
    if (!res.ok) return;
    const payload = await res.json();
    renderQTable(payload.top || []);
  } catch (_e) {
    // Keep silent; dashboard should still run without this panel.
  }
}

function updateStats(payload) {
  const state = payload.state;
  fuelEl.textContent = `${state.fuel.toFixed(1)}%`;
  trafficEl.textContent = state.traffic_level;
  qstateEl.textContent = payload.info?.q_state ? `${payload.info.q_state[0]} | ${payload.info.q_state[1]}` : "-";
  decisionEl.textContent = payload.decision || "-";
  const qText = payload.q_update
    ? ` | Q ${payload.q_update.old.toFixed(2)}→${payload.q_update.new.toFixed(2)}`
    : "";
  rewardEl.textContent = `${(payload.reward ?? 0).toFixed(2)}${qText}`;
  distanceEl.textContent = `${state.distance_remaining_km.toFixed(2)} km`;
  statusEl.textContent = state.done ? "Completed" : "Running";

  // Keep marker movement driven by route-geometry animation.
  // Fallback to server position if animation is not active.
  if (!selectedRouteCoordinates.length) {
    const lat = state.current_position.lat;
    const lon = state.current_position.lon;
    vehicleMarker.setLatLng([lat, lon]);
  }
}

async function startDelivery() {
  if (timer) clearInterval(timer);
  stopAnimation();
  selectedRouteCoordinates = [];
  animationIndex = 0;
  vehicleMarker.setLatLng(hub);
  statusEl.textContent = "Fetching real routes...";
  rewardEl.textContent = "-";
  qstateEl.textContent = "-";

  const destination = destinationInput.value.trim() || "Whitefield Bangalore";
  const res = await fetch(`${API_BASE}/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ destination }),
  });

  if (!res.ok) {
    const msg = await res.json();
    statusEl.textContent = msg.detail || "Failed to start";
    return;
  }

  const payload = await res.json();
  renderRouteOptions(payload.routes, payload.selected_route);

  const chosen = payload.routes[payload.selected_route - 1];
  selectedRouteCoordinates = chosen.coordinates;
  console.log("Route points:", selectedRouteCoordinates.length);
  if (selectedRouteCoordinates.length <= 2) {
    console.warn("Route has too few points. Backend may not be returning full geometry.");
  }
  renderDirections(chosen.steps || []);

  const destinationPoint = payload.state.destination;
  if (destMarker) map.removeLayer(destMarker);
  destMarker = L.circleMarker([destinationPoint.lat, destinationPoint.lon], {
    radius: 7,
    color: "#b91c1c",
    fillColor: "#ef4444",
    fillOpacity: 1,
  }).addTo(map).bindPopup("Destination");

  if (window.currentRoute) {
    map.fitBounds(window.currentRoute.getBounds(), { padding: [50, 50] });
  }

  updateStats(payload);
  refreshQTable();
  moveCar();

  timer = setInterval(stepDelivery, 1000);
}

async function stepDelivery() {
  const res = await fetch(`${API_BASE}/step`);
  if (!res.ok) {
    statusEl.textContent = "API error";
    clearInterval(timer);
    return;
  }
  const payload = await res.json();
  updateStats(payload);
  refreshQTable();
  if (payload.done) {
    statusEl.textContent = "Finished";
    clearInterval(timer);
    stopAnimation();
  }
}

startBtn.addEventListener("click", startDelivery);
refreshQTable();
