from __future__ import annotations

from .agent import QAgent
from .env import DeliveryRLEnv
from .routing import geocode_destination, get_route_options


def run_training(episodes: int = 300) -> None:
    env = DeliveryRLEnv(seed=42)
    agent = QAgent(alpha=0.1, gamma=0.9, epsilon=0.2)

    destinations = ["Whitefield Bangalore", "Electronic City Bangalore", "Indiranagar Bangalore"]
    cached_scenarios = []
    for d in destinations:
        dest = geocode_destination(d)
        routes = get_route_options((env.hub["lat"], env.hub["lon"]), (dest["lat"], dest["lon"]))
        cached_scenarios.append((dest["name"], {"lat": dest["lat"], "lon": dest["lon"]}, routes))

    for ep in range(1, episodes + 1):
        name, dest, routes = cached_scenarios[(ep - 1) % len(cached_scenarios)]
        env.reset(name, dest, routes)
        done = False
        while not done:
            state = env.get_state()
            action = agent.choose_action(state, env.actions, explore=True)
            next_state, reward, done, _ = env.step(action)
            old_q, new_q = agent.update(state, action, reward, next_state, env.actions)
            s = agent.get_state_key(state)
            print(
                f"Traffic: {s[0].title()} | Fuel: {s[1].title()} | "
                f"Action: Route {action + 1} | Reward: {reward:+.2f} | Q updated: {old_q:.3f} -> {new_q:.3f}"
            )
            print("\nQ-TABLE SNAPSHOT")
            for k, v in list(agent.q_table.items())[:5]:
                print(f"{k} -> {round(v, 2)}")
        if ep % 50 == 0:
            print(f"Completed episode {ep}/{episodes}")

    agent.save("backend/q_table.pkl")
    print("Training complete. Saved Q-table to backend/q_table.pkl")


if __name__ == "__main__":
    run_training(episodes=300)
