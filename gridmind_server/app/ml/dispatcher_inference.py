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
