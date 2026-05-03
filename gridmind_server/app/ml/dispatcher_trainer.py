import os
import random
from collections import deque
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim

try:
    from gridmind_server.app.ml.dispatcher_env import GridMindEnv
except ModuleNotFoundError:
    from dispatcher_env import GridMindEnv

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

class DQNAgent:
    def __init__(self, state_dim, action_dim):
        self.state_dim = state_dim
        self.action_dim = action_dim
        
        # Hyperparameters
        self.gamma = 0.99
        self.epsilon = 1.0
        self.epsilon_min = 0.05
        self.epsilon_decay = 0.995
        self.batch_size = 64
        self.lr = 0.001
        
        self.memory = deque(maxlen=10000)
        self.model = DQN(state_dim, action_dim)
        self.optimizer = optim.Adam(self.model.parameters(), lr=self.lr)
        self.criterion = nn.MSELoss()
        
    def act(self, state):
        if np.random.rand() <= self.epsilon:
            return random.randrange(self.action_dim)
        state_tensor = torch.FloatTensor(state).unsqueeze(0)
        with torch.no_grad():
            q_values = self.model(state_tensor)
        return torch.argmax(q_values).item()
        
    def remember(self, state, action, reward, next_state, done):
        self.memory.append((state, action, reward, next_state, done))
        
    def replay(self):
        if len(self.memory) < self.batch_size:
            return
            
        minibatch = random.sample(self.memory, self.batch_size)
        states = torch.FloatTensor(np.vstack([m[0] for m in minibatch]))
        actions = torch.LongTensor([m[1] for m in minibatch])
        rewards = torch.FloatTensor([m[2] for m in minibatch])
        next_states = torch.FloatTensor(np.vstack([m[3] for m in minibatch]))
        dones = torch.FloatTensor([m[4] for m in minibatch])
        
        # Current Q
        curr_Q = self.model(states).gather(1, actions.unsqueeze(1)).squeeze(1)
        
        # Target Q
        with torch.no_grad():
            max_next_Q = self.model(next_states).max(1)[0]
            target_Q = rewards + (1 - dones) * self.gamma * max_next_Q
            
        loss = self.criterion(curr_Q, target_Q)
        
        self.optimizer.zero_grad()
        loss.backward()
        self.optimizer.step()
        
        if self.epsilon > self.epsilon_min:
            self.epsilon *= self.epsilon_decay

def train_and_export(carbon_csv_path):
    env = GridMindEnv(carbon_csv_path)
    state_dim = env.state_space_n
    action_dim = env.action_space_n
    
    agent = DQNAgent(state_dim, action_dim)
    episodes = 500
    
    print("Starting DQN Training...")
    
    for e in range(episodes):
        state = env.reset()
        total_reward = 0
        done = False
        
        while not done:
            action = agent.act(state)
            next_state, reward, done = env.step(action)
            agent.remember(state, action, reward, next_state, done)
            state = next_state
            total_reward += reward
            agent.replay()
            
        if e % 50 == 0:
            print(f"Episode {e}/{episodes} - Total Reward: {total_reward:.2f} - Epsilon: {agent.epsilon:.2f}")
    
    print("Training Complete!")
    export_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "models", "dispatcher_dqn.onnx"))
    os.makedirs(os.path.dirname(export_path), exist_ok=True)
    
    # Save model weights as a native PyTorch .pt file.
    # torch.onnx.export is unstable in torch 2.x on this system.
    # torch.save + torch.load is fully stable and sub-1ms on CPU for this tiny network.
    pt_path = export_path.replace(".onnx", ".pt")
    agent.model.eval()
    torch.save(agent.model.state_dict(), pt_path)
    print("Model weights saved to:", pt_path)
    # Also save the full model architecture for easy loading
    torch.save(agent.model, pt_path.replace(".pt", "_full.pt"))
    print("Full model saved to:", pt_path.replace(".pt", "_full.pt"))

if __name__ == "__main__":
    import sys
    # Expect csv path passed as arg, or default
    csv_path = "watttime_carbon_data_CAISO_NORTH.csv"
    if len(sys.argv) > 1:
        csv_path = sys.argv[1]
    
    train_and_export(csv_path)
