from __future__ import annotations

from typing import Any, Dict

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .agent import QAgent
from .env import DeliveryRLEnv
from .routing import geocode_destination, get_route_options


class StartRequest(BaseModel):
    destination: str


app = FastAPI(title="Smart AI Delivery Navigation")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

env = DeliveryRLEnv(seed=42)
agent = QAgent(alpha=0.1, gamma=0.9, epsilon=0.0)
agent.load("backend/q_table.pkl")
session_active = False
online_learning = True


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/qtable")
def qtable(limit: int = 10) -> Dict[str, Any]:
    rows = []
    for (state_key, action), value in agent.q_table.items():
        traffic, fuel_bucket = state_key
        rows.append(
            {
                "traffic": traffic,
                "fuel_bucket": fuel_bucket,
                "action": f"SELECT_ROUTE_{action + 1}",
                "q_value": float(value),
            }
        )
    rows.sort(key=lambda r: r["q_value"], reverse=True)
    return {"count": len(rows), "top": rows[: max(1, min(limit, 50))]}


@app.post("/start")
def start_delivery(req: StartRequest) -> Dict[str, Any]:
    global session_active
    try:
        dest = geocode_destination(req.destination)
        routes = get_route_options(
            start=(env.hub["lat"], env.hub["lon"]),
            dest=(dest["lat"], dest["lon"]),
        )
        state = env.reset(
            destination_name=dest["name"],
            destination={"lat": dest["lat"], "lon": dest["lon"]},
            route_options=routes,
        )
        action = agent.choose_action(state, env.actions, explore=False)
        session_active = True
        return {
            "state": state,
            "decision": f"SELECT_ROUTE_{action + 1}",
            "selected_route": action + 1,
            "routes": routes,
        }
    except Exception as e:  # pragma: no cover
        # Return explicit JSON error so frontend does not show opaque CORS-style failure.
        raise HTTPException(status_code=500, detail=f"Start failed: {e}")


@app.get("/step")
def step_delivery() -> Dict[str, Any]:
    if not session_active:
        raise HTTPException(status_code=400, detail="Call POST /start first.")
    if env.done:
        return {"state": env.get_state(), "done": True, "reward": 0.0, "info": {"event": "episode_done"}}

    current_state = env.get_state()
    action = agent.choose_action(current_state, env.actions, explore=False)
    next_state, reward, done, info = env.step(action)
    q_update = None
    if online_learning:
        old_q, new_q = agent.update(current_state, action, reward, next_state, env.actions)
        q_update = {"old": old_q, "new": new_q}
        agent.save("backend/q_table.pkl")
    return {
        "state": next_state,
        "decision": f"SELECT_ROUTE_{action + 1}",
        "selected_route": action + 1,
        "reward": reward,
        "done": done,
        "info": info,
        "q_update": q_update,
    }
