import numpy as np
import pandas as pd
from typing import Tuple, List

class GridMindEnv:
    """
    Custom Gym-like environment for the GridMind Dispatcher.
    
    State: [Queue_Size, Carbon_Intensity_Normalized, Node_1_State, Node_2_State, Node_3_State]
        - Queue_Size: 0 to MAX_QUEUE (int)
        - Carbon_Intensity: 0.0 to 1.0 (float)
        - Node State: 0 (idle), 1 (active_user), 2 (busy_hardware)
        
    Actions:
        0: Defer (Do nothing)
        1: Dispatch to Node 1
        2: Dispatch to Node 2
        3: Dispatch to Node 3
    """
    
    def __init__(self, carbon_csv_path: str, max_queue: int = 5):
        self.max_queue = max_queue
        self.num_nodes = 3
        self.action_space_n = 1 + self.num_nodes # Defer + Dispatch to each node
        self.state_space_n = 2 + self.num_nodes  # queue, carbon, [nodes...]
        
        # Load carbon data
        self._load_carbon_data(carbon_csv_path)
        
        self.current_step = 0
        self.queue_size = 0
        self.node_states = [0, 0, 0]
        
    def _load_carbon_data(self, csv_path: str):
        try:
            df = pd.read_csv(csv_path)
            # Normalize to 0-1
            min_c = df['value'].min()
            max_c = df['value'].max()
            self.carbon_series = ((df['value'] - min_c) / (max_c - min_c)).values
        except Exception as e:
            print(f"Warning: Could not load {csv_path}. Using synthetic sine wave.")
            x = np.linspace(0, 100 * np.pi, 10000)
            self.carbon_series = (np.sin(x) + 1) / 2.0
            
    def _randomize_nodes(self):
        """Randomly change node states to simulate real world."""
        # 60% idle, 25% active, 15% busy
        self.node_states = np.random.choice([0, 1, 2], p=[0.60, 0.25, 0.15], size=self.num_nodes).tolist()
        
    def get_state(self) -> np.ndarray:
        carbon = self.carbon_series[self.current_step % len(self.carbon_series)]
        state = [self.queue_size, carbon] + self.node_states
        return np.array(state, dtype=np.float32)
        
    def reset(self) -> np.ndarray:
        self.current_step = 0
        self.queue_size = np.random.randint(0, self.max_queue + 1)
        self._randomize_nodes()
        return self.get_state()
        
    def step(self, action: int) -> Tuple[np.ndarray, float, bool]:
        carbon = self.carbon_series[self.current_step % len(self.carbon_series)]
        reward = 0.0
        done = False
        
        # 1. Process action
        if action == 0:
            # Defer
            if self.queue_size > 0:
                if carbon > 0.6:
                    reward += 2.0 # Good choice to defer when grid is dirty
                else:
                    reward -= 1.0 # Bad choice to defer if grid is clean and we have tasks
            else:
                reward += 0.5 # Sensible to do nothing if empty queue
        else:
            # Attempt Dispatch
            target_idx = action - 1
            if self.queue_size == 0:
                reward -= 5.0 # Penalty for dispatching when no tasks exist
            else:
                target_state = self.node_states[target_idx]
                if target_state == 0:
                    # Successful dispatch to idle node
                    reward += 10.0
                    reward += (1.0 - carbon) * 5.0 # Bonus for green energy
                    self.queue_size -= 1
                else:
                    # Disastrous penalty for interrupting active/busy node
                    reward -= 50.0 
                    
        # 2. Advance world
        self.current_step += 1
        self._randomize_nodes()
        
        # 3. Randomly add new tasks
        if np.random.random() < 0.2 and self.queue_size < self.max_queue:
            self.queue_size += 1
            
        # Queue penalty
        if self.queue_size == self.max_queue:
            reward -= 2.0
            
        # Arbitrary done flag every day of 5-min intervals (288 steps)
        if self.current_step >= 288:
            done = True
            
        next_state = self.get_state()
        return next_state, reward, done
