# gpu_heavy_training.py

import torch
import torch.nn as nn
import torch.optim as optim
from torch.cuda.amp import autocast, GradScaler
import time

# Check GPU
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

if device.type == "cpu":
    print("❌ CUDA GPU not found")
    exit()

print(f"🔥 Using GPU: {torch.cuda.get_device_name(0)}")

# Huge model for GPU stress
class HeavyNet(nn.Module):
    def __init__(self):
        super().__init__()

        self.net = nn.Sequential(
            nn.Linear(8192, 16384),
            nn.ReLU(),

            nn.Linear(16384, 16384),
            nn.ReLU(),

            nn.Linear(16384, 8192),
            nn.ReLU(),

            nn.Linear(8192, 4096),
            nn.ReLU(),

            nn.Linear(4096, 1000)
        )

    def forward(self, x):
        return self.net(x)


model = HeavyNet().to(device)

optimizer = optim.AdamW(model.parameters(), lr=0.0005)
criterion = nn.CrossEntropyLoss()

# Mixed precision for max GPU throughput
scaler = GradScaler()

# Massive synthetic batch
batch_size = 8192
input_dim = 8192
num_classes = 1000

print("🚀 Creating synthetic data...")

X = torch.randn(batch_size, input_dim, device=device)
y = torch.randint(0, num_classes, (batch_size,), device=device)

print("🔥 Starting GPU intensive training...")
start = time.time()

epochs = 1000

for epoch in range(epochs):

    optimizer.zero_grad()

    with autocast():
        outputs = model(X)
        loss = criterion(outputs, y)

    scaler.scale(loss).backward()
    scaler.step(optimizer)
    scaler.update()

    if epoch % 10 == 0:
        allocated = torch.cuda.memory_allocated() / 1024**3
        reserved = torch.cuda.memory_reserved() / 1024**3

        print(
            f"Epoch {epoch} | "
            f"Loss: {loss.item():.4f} | "
            f"VRAM Used: {allocated:.2f} GB | "
            f"Reserved: {reserved:.2f} GB"
        )

end = time.time()

print(f"\n✅ Finished in {end-start:.2f} sec")