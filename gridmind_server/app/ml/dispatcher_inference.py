import os
import logging
import numpy as np

logger = logging.getLogger("gridmind.dispatcher_inference")

class DispatcherInference:
    """
    Sub-10ms PyTorch inference wrapper for the Dispatcher AI with dynamic fallback.
    """
    STATE_DIM = 10
    ACTION_DIM = 2  # [defer, dispatch]

    def __init__(self, model_path: str = None):
        self._use_heuristic = False
        if os.environ.get("GRIDMIND_LOAD_ML") == "1":
            try:
                import torch
                import torch.nn as nn
                self._torch = torch
                self._nn = nn
                
                # Define DuelingDQN dynamically within the successful import context
                class DuelingDQN(nn.Module):
                    def __init__(self, state_dim, action_dim):
                        super(DuelingDQN, self).__init__()
                        self.fc1 = nn.Linear(state_dim, 64)
                        self.relu1 = nn.ReLU()
                        self.fc2 = nn.Linear(64, 64)
                        self.relu2 = nn.ReLU()
                        self.value_stream = nn.Linear(64, 1)
                        self.advantage_stream = nn.Linear(64, action_dim)

                    def forward(self, x):
                        x = self.relu1(self.fc1(x))
                        x = self.relu2(self.fc2(x))
                        value = self.value_stream(x)
                        advantage = self.advantage_stream(x)
                        return value + (advantage - advantage.mean(dim=1, keepdim=True))

                if model_path is None:
                    base = os.path.abspath(
                        os.path.join(os.path.dirname(__file__), "..", "..", "..", "models", "dispatcher_dqn")
                    )
                    weights_path = base + ".pt"
                    if os.path.exists(weights_path):
                        model_path = weights_path
                    else:
                        raise FileNotFoundError(f"Weights not found: {weights_path}")

                self.model = DuelingDQN(self.STATE_DIM, self.ACTION_DIM)
                self.model.load_state_dict(torch.load(model_path, map_location="cpu", weights_only=True))
                self.model.eval()
                logger.info(f"Loaded Dispatcher DQN state_dict from {model_path}")
            except Exception as exc:
                logger.warning(f"PyTorch/model loading failed; falling back to heuristic: {exc}")
                self._use_heuristic = True
        else:
            logger.info("GRIDMIND_LOAD_ML not set to 1; using high-fidelity heuristic fallback for dispatcher.")
            self._use_heuristic = True

    def predict_action(self, state: list) -> tuple[int, list[float]]:
        if self._use_heuristic:
            # High-fidelity rule-based heuristic dispatching
            # state vector: [q_norm, carbon, idle_ratio, active_ratio, busy_ratio, avg_cpu, avg_ram, urgent_ratio, deferrable_ratio, best_effort_ratio]
            if len(state) >= 10:
                q_norm, carbon, idle_ratio, active_ratio, busy_ratio, avg_cpu, avg_ram, u_ratio, d_ratio, best_effort_ratio = state
                if idle_ratio > 0.0:
                    if u_ratio > 0.0: # Always dispatch urgent immediately
                        return 1, [0.0, 1.0]
                    if carbon < 0.65: # Dispatch if grid carbon is clean
                        return 1, [0.0, 1.0]
            return 0, [1.0, 0.0]
            
        state_tensor = self._torch.FloatTensor(state).unsqueeze(0)
        with self._torch.no_grad():
            q_values = self.model(state_tensor)
        return int(self._torch.argmax(q_values).item()), q_values.squeeze(0).tolist()


def evaluate_decision_matrix(engine: "DispatcherInference", n: int = 400, seed: int = 42) -> dict:
    """
    Build an honest defer/dispatch "confusion" (decision-agreement) matrix for the
    Dispatcher policy.

    The Dispatcher is reinforcement learning, so there is no labelled ground truth.
    Instead we evaluate against the 1-step REWARD-OPTIMAL action under the exact
    environment the DQN was trained on (see dispatcher_env.GridMindEnv.step):

      - Dispatch pays +10..+15 only when a task is queued AND an idle node exists;
        with no idle node it pays -50, and with no task it pays -5.
      - Defer pays at most +2.
    => The reward-optimal action is DISPATCH iff (queue>0 AND an idle node exists),
       otherwise DEFER. (Carbon only changes the dispatch bonus, never which action
       is optimal, so it doesn't flip the oracle.)

    We sample states from the environment's own distribution (seeded → deterministic)
    and compare the policy's argmax action to that oracle.

    Returns rows = oracle (actual-optimal), cols = predicted (policy), labels
    ["defer", "dispatch"].
    """
    rng = np.random.default_rng(seed)
    num_nodes, max_queue = 5, 20
    # matrix[oracle][predicted]
    matrix = [[0, 0], [0, 0]]

    for _ in range(n):
        queue = int(rng.integers(0, max_queue + 1))
        urgent = int(rng.integers(0, queue + 1))
        deferrable = int(rng.integers(0, queue - urgent + 1))
        best = queue - urgent - deferrable
        nodes = rng.choice([0, 1, 2], p=[0.60, 0.25, 0.15], size=num_nodes)
        carbon = float(rng.random())

        q_norm = min(1.0, queue / max_queue)
        idle = float(np.sum(nodes == 0) / num_nodes)
        active = float(np.sum(nodes == 1) / num_nodes)
        busy = float(np.sum(nodes == 2) / num_nodes)
        avg_cpu = 0.2 * idle + 0.5 * active + 0.9 * busy
        tot = max(1, urgent + deferrable + best)
        state = [q_norm, carbon, idle, active, busy, avg_cpu, 0.4,
                 urgent / tot, deferrable / tot, best / tot]

        predicted = engine.predict_action(state)[0]
        oracle = 1 if (q_norm > 0 and idle > 0) else 0
        matrix[oracle][predicted] += 1

    correct = matrix[0][0] + matrix[1][1]
    return {
        "model_name": "dispatcher_dqn",
        "model_type": "Dueling Double DQN (reinforcement learning)",
        "evaluation": (
            "No labelled ground truth (RL). Compared against the 1-step reward-optimal "
            "action under the training environment, over seeded held-out states."
        ),
        "using_model": not engine._use_heuristic,
        "labels": ["defer", "dispatch"],
        "matrix": matrix,                       # rows = optimal, cols = policy
        "samples": n,
        "agreement": round(correct / n, 4) if n else 0.0,
        "state_dim": DispatcherInference.STATE_DIM,
        "action_dim": DispatcherInference.ACTION_DIM,
    }
