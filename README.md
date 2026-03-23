# Smart AI Delivery: Real-Road Q-Learning Navigator

This project upgrades the delivery RL demo into a real-world inspired navigation system:

- Real destination geocoding
- Real road routes (OpenRouteService)
- Q-learning agent for route selection

## Architecture

```text
backend/
  env.py        # RL environment with route options, fuel, traffic
  routing.py    # geocoding + real road routing API calls
  agent.py      # Q-learning agent + Q-table persistence
  train.py      # train Q-table with live Q-update logs
  app.py        # FastAPI endpoints /start and /step
frontend/
  index.html
  script.js
  style.css
```

## Routing and Geocoding

The backend uses:

- Geocoding: `https://api.openrouteservice.org/geocode/search`
- Routing: `https://api.openrouteservice.org/v2/directions/driving-car/geojson`

It fetches three real-road options:

1. Fastest
2. Shortest
3. Balanced (`recommended`)

The frontend draws those exact polylines from API response geometry (no fake paths).

## Q-Learning

State is discretized into:

- traffic: `low | medium | high`
- fuel: `low | medium | high`

Actions:

- `SELECT_ROUTE_1`
- `SELECT_ROUTE_2`
- `SELECT_ROUTE_3`

Update rule:

`Q(s,a) = Q(s,a) + alpha * (reward + gamma * max_a' Q(s',a') - Q(s,a))`

Parameters:

- `alpha = 0.1`
- `gamma = 0.9`
- `epsilon = 0.2` (during training)

## Setup

1. Install dependencies:

```bash
pip install fastapi uvicorn requests
```

2. Set your OpenRouteService key:

```bash
# PowerShell
$env:ORS_API_KEY="your_openrouteservice_api_key"
```

## Train Agent

Run training (prints Q updates for each step):

```bash
python -m backend.train
```

This saves learned values to:

- `backend/q_table.pkl`

Example log:

```text
Traffic: High | Fuel: Low | Action: Route 2 | Reward: +8.00 | Q updated: 2.300 -> 3.100
```

## Run Backend

```bash
python -m uvicorn backend.app:app --reload --port 8000
```

Endpoints:

- `POST /start` with `{"destination":"Whitefield Bangalore"}`
- `GET /step`

## Run Frontend

```bash
python -m http.server 5500 -d frontend
```

Open:

- [http://127.0.0.1:5500](http://127.0.0.1:5500)

## Demo Flow

1. Enter destination text
2. Click **Start Delivery**
3. Backend geocodes destination and fetches real road alternatives
4. Q-agent picks best route from learned Q-table
5. Map animates car along selected route coordinates
6. Live panel shows traffic, fuel, reward, Q-state, and decision

## Error Handling

- Missing ORS key: backend returns clear error for `/start`
- Invalid destination: geocoding error returned to UI
- Routing API failure: HTTP error details surfaced via API response
