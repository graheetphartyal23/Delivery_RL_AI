from __future__ import annotations

import random
from typing import Any, Dict, List, Tuple


SELECT_ROUTE_1 = 0
SELECT_ROUTE_2 = 1
SELECT_ROUTE_3 = 2


class DeliveryRLEnv:
    """Environment consuming real route options from routing APIs."""

    def __init__(self, seed: int = 42) -> None:
        self.rng = random.Random(seed)
        self.actions = [SELECT_ROUTE_1, SELECT_ROUTE_2, SELECT_ROUTE_3]
        self.hub = {"name": "Bangalore Central", "lat": 12.9716, "lon": 77.5946}
        self.done = True

    def reset(self, destination_name: str, destination: Dict[str, float], route_options: List[Dict[str, Any]]) -> Dict[str, Any]:
        if len(route_options) < 3:
            raise ValueError("Need at least 3 route options.")
        self.destination_name = destination_name
        self.destination = destination
        self.route_options = route_options[:3]
        self.current_route_idx = 0
        self.selected_action: int | None = None
        self.step_count = 0
        self.fuel = 100.0
        self.total_reward = 0.0
        self.done = False
        self.traffic_level = self._sample_traffic()
        self.route_progress = [0, 0, 0]
        self.current_position = {"lat": self.hub["lat"], "lon": self.hub["lon"]}
        return self.get_state()

    def step(self, action: int) -> Tuple[Dict[str, Any], float, bool, Dict[str, Any]]:
        if self.done:
            return self.get_state(), 0.0, True, {"event": "episode_done"}
        if action not in self.actions:
            raise ValueError(f"Invalid action: {action}")

        # Lock decision after first step to mimic route commitment.
        if self.selected_action is None:
            self.selected_action = action
        action = self.selected_action
        self.current_route_idx = action
        route = self.route_options[action]
        coords = route["coordinates"]

        self.step_count += 1
        self.traffic_level = self._sample_traffic(dynamic=True)
        traffic_mult = {"low": 0.95, "medium": 1.10, "high": 1.30}[self.traffic_level]
        event_penalty = 0.0
        event = "none"
        if self.rng.random() < 0.16:
            event = self.rng.choice(["delay", "shortcut", "congestion"])
            event_penalty = {"delay": 1.2, "shortcut": -0.8, "congestion": 1.8}[event]

        hop = 1 if self.traffic_level == "high" else 2
        self.route_progress[action] = min(len(coords) - 1, self.route_progress[action] + hop)
        lat, lon = coords[self.route_progress[action]]
        self.current_position = {"lat": lat, "lon": lon}

        base_fuel = route["distance_km"] / max(1.0, len(coords))
        fuel_used = max(0.4, base_fuel * 0.9 * traffic_mult + max(0.0, event_penalty * 0.1))
        self.fuel = max(0.0, self.fuel - fuel_used)

        reward = 0.0
        reward += 8.0 if hop > 1 else 3.0
        reward -= fuel_used * 0.7
        reward -= event_penalty
        if self.traffic_level == "high" and action == SELECT_ROUTE_1:
            reward -= 3.0
        if self._optimal_action() == action:
            reward += 5.0

        finished = self.route_progress[action] >= len(coords) - 1
        if finished:
            reward += 100.0
            self.done = True
        elif self.fuel <= 0:
            reward -= 100.0
            self.done = True
        elif self.step_count >= 120:
            reward -= 20.0
            self.done = True

        self.total_reward += reward
        info = {
            "event": event,
            "traffic": self.traffic_level,
            "selected_route": action + 1,
            "q_state": self.discrete_state(),
        }
        return self.get_state(), round(reward, 3), self.done, info

    def get_state(self) -> Dict[str, Any]:
        return {
            "current_position": dict(self.current_position),
            "destination": dict(self.destination),
            "route_options": [
                {
                    "id": idx + 1,
                    "label": r["label"],
                    "distance_km": round(r["distance_km"], 2),
                    "duration_min": round(r["duration_min"], 1),
                }
                for idx, r in enumerate(self.route_options)
            ],
            "traffic_level": self.traffic_level,
            "fuel": round(self.fuel, 2),
            "distance_remaining_km": self._remaining_distance_km(),
            "selected_route": None if self.selected_action is None else self.selected_action + 1,
            "step_count": self.step_count,
            "total_reward": round(self.total_reward, 3),
            "done": self.done,
            "available_actions": list(self.actions),
        }

    def discrete_state(self) -> Tuple[str, str]:
        if self.fuel < 20:
            fuel_state = "low"
        elif self.fuel < 55:
            fuel_state = "medium"
        else:
            fuel_state = "high"
        return self.traffic_level, fuel_state

    def _remaining_distance_km(self) -> float:
        route = self.route_options[self.current_route_idx]
        coords = route["coordinates"]
        idx = self.route_progress[self.current_route_idx]
        ratio = 1.0 - (idx / max(1, len(coords) - 1))
        return round(route["distance_km"] * ratio, 3)

    def _sample_traffic(self, dynamic: bool = False) -> str:
        name = self.destination_name.lower()
        if "whitefield" in name:
            probs = [0.15, 0.35, 0.50]
        elif "electronic" in name:
            probs = [0.20, 0.55, 0.25]
        elif "indiranagar" in name:
            probs = [0.25, 0.45, 0.30] if dynamic else [0.30, 0.45, 0.25]
        else:
            probs = [0.30, 0.50, 0.20]
        return self.rng.choices(["low", "medium", "high"], weights=probs, k=1)[0]

    def _optimal_action(self) -> int:
        # Heuristic ground truth for shaping while learning.
        ranked = sorted(
            enumerate(self.route_options),
            key=lambda x: (x[1]["duration_min"], x[1]["distance_km"]),
        )
        if self.traffic_level == "high":
            return sorted(enumerate(self.route_options), key=lambda x: x[1]["distance_km"])[0][0]
        if self.fuel < 20:
            return sorted(enumerate(self.route_options), key=lambda x: x[1]["distance_km"] / max(1.0, x[1]["duration_min"]))[0][0]
        return ranked[0][0]
