from __future__ import annotations

import random
import pickle
from pathlib import Path
from typing import Dict, List, Tuple, Any


StateKey = Tuple[str, str]  # (traffic, fuel_bucket)


class QAgent:
    def __init__(self, alpha: float = 0.1, gamma: float = 0.9, epsilon: float = 0.2) -> None:
        self.q_table: Dict[Tuple[StateKey, int], float] = {}
        self.alpha = alpha
        self.gamma = gamma
        self.epsilon = epsilon

    def get_state_key(self, state: Dict[str, Any] | StateKey) -> StateKey:
        if isinstance(state, tuple):
            traffic, fuel_bucket = state
            return traffic, fuel_bucket
        traffic = state.get("traffic") or state.get("traffic_level", "medium")
        fuel = float(state.get("fuel", 100.0))
        if fuel < 20:
            fuel_bucket = "low"
        elif fuel < 55:
            fuel_bucket = "medium"
        else:
            fuel_bucket = "high"
        return traffic, fuel_bucket

    def choose_action(self, state: Dict[str, Any] | StateKey, actions: List[int], explore: bool = True) -> int:
        key = self.get_state_key(state)
        if explore and random.random() < self.epsilon:
            return random.choice(actions)
        return max(actions, key=lambda a: self.q_table.get((key, a), 0.0))

    def update(
        self,
        state: Dict[str, Any] | StateKey,
        action: int,
        reward: float,
        next_state: Dict[str, Any] | StateKey,
        actions: List[int],
    ) -> Tuple[float, float]:
        key = self.get_state_key(state)
        next_key = self.get_state_key(next_state)
        old_q = self.q_table.get((key, action), 0.0)
        max_next = max([self.q_table.get((next_key, a), 0.0) for a in actions], default=0.0)
        new_q = old_q + self.alpha * (reward + self.gamma * max_next - old_q)
        self.q_table[(key, action)] = new_q
        return old_q, new_q

    def save(self, path: str = "backend/q_table.pkl") -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("wb") as f:
            pickle.dump(self.q_table, f)

    def load(self, path: str = "backend/q_table.pkl") -> bool:
        p = Path(path)
        if not p.exists():
            return False
        with p.open("rb") as f:
            self.q_table = pickle.load(f)
        return True


class QLearningAgent(QAgent):
    """Backward-compatible alias."""
