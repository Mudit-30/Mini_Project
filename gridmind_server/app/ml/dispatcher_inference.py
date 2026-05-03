import os
import logging
import torch
import torch.nn as nn
import numpy as np

logger = logging.getLogger("gridmind.dispatcher_inference")

# Must match the architecture in dispatcher_trainer.py exactly
class DQN(nn.Module):
    def __init__(self, state_dim, action_dim):
        super(DQN, self).__init__()
        self.fc1 = nn.Linear(state_dim, 64)
        self.relu1 = nn.ReLU()
        self.fc2 = nn.Linear(64, 32)
        self.relu2 = nn.ReLU()
        self.fc3 = nn.Linear(32, action_dim)

    def forward(self, x):
        x = self.relu1(self.fc1(x))
        x = self.relu2(self.fc2(x))
        return self.fc3(x)


class DispatcherInference:
    """
    Sub-10ms PyTorch inference wrapper for the Dispatcher AI.

    Loads the trained DQN from a .pt file (native PyTorch format, which is
    fully stable on torch 2.x unlike the ONNX exporter).
    """
    # Fixed dimensions that must match the training environment
    STATE_DIM = 5   # [queue_size, carbon_intensity, node0, node1, node2]
    ACTION_DIM = 4  # [defer, dispatch_node0, dispatch_node1, dispatch_node2]

    def __init__(self, model_path: str = None):
        if model_path is None:
            # We ONLY use the state_dict (.pt) because _full.pt suffers from __main__ unpickling issues
            base = os.path.abspath(
                os.path.join(os.path.dirname(__file__), "..", "..", "..", "models", "dispatcher_dqn")
            )
            weights_path = base + ".pt"

            if os.path.exists(weights_path):
                model_path = weights_path
            else:
                raise FileNotFoundError(
                    f"No trained Dispatcher model found at {weights_path}. "
                    "Run dispatcher_trainer.py first."
                )

        self.model = DQN(self.STATE_DIM, self.ACTION_DIM)
        self.model.load_state_dict(torch.load(model_path, map_location="cpu", weights_only=True))
        self.model.eval()
        logger.info(f"Loaded Dispatcher DQN state_dict from {model_path}")

    def predict_action(self, state: list) -> int:
        """
        Takes raw state list: [QueueSize, CarbonIntensity, Node0State, Node1State, Node2State]
        Returns the chosen action integer: (0=Defer, 1=Node0, 2=Node1, 3=Node2)
        """
        state_tensor = torch.FloatTensor(state).unsqueeze(0)
        with torch.no_grad():
            q_values = self.model(state_tensor)
        return int(torch.argmax(q_values).item())


if __name__ == "__main__":
    import time

    try:
        dispatcher = DispatcherInference()

        # Test: Queue=3, Carbon=0.8 (dirty), Nodes=[1(Active), 0(Idle), 0(Idle)]
        # Expected: AI should defer (carbon dirty) or dispatch to node 2 or 3
        dummy_state = [3, 0.8, 1, 0, 0]

        # Warmup
        _ = dispatcher.predict_action(dummy_state)

        # Timing test
        start = time.perf_counter()
        action = dispatcher.predict_action(dummy_state)
        elapsed_ms = (time.perf_counter() - start) * 1000

        action_names = ["DEFER", "DISPATCH Node 1", "DISPATCH Node 2", "DISPATCH Node 3"]
        print(f"Test state: {dummy_state}")
        print(f"Predicted action: {action} ({action_names[action]})")
        print(f"Inference latency: {elapsed_ms:.3f} ms")
        assert elapsed_ms < 10.0, f"Too slow: {elapsed_ms:.2f}ms"
        print("Inference wrapper validated successfully! (sub-10ms)")

    except FileNotFoundError as e:
        print(e)
