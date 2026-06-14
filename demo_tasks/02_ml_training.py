"""
GridMind demo: a REAL neural network, trained from scratch.

No fake numbers, no time.sleep() — this builds a 1-hidden-layer neural net in
pure Python (stdlib only, so it runs on any node without numpy/sklearn) and
trains it with genuine forward-propagation, binary cross-entropy loss, and
back-propagation / gradient descent. The loss really falls and the accuracy
really climbs because the network is actually learning.

Task: classify whether a 2-D point lies inside a circle. This is NOT linearly
separable, so a plain linear model can't solve it — the hidden layer is what
lets the net learn the curved decision boundary. That's the point: it's doing
real work, not printing a scripted curve.
"""
import math
import os
import random
import time

random.seed(42)  # reproducible so the demo looks the same every run

# ── Hyper-parameters ──────────────────────────────────────────────────────────
N_TRAIN = 1200
N_TEST = 400
HIDDEN = 12            # hidden-layer width
EPOCHS = 500
LR = 3.0              # learning rate
RADIUS2 = 0.5          # decision boundary: inside circle of radius sqrt(0.5)


def make_dataset(n):
    """Random points in [-1, 1]^2; label 1 if inside the circle, else 0."""
    xs, ys = [], []
    for _ in range(n):
        x1 = random.uniform(-1, 1)
        x2 = random.uniform(-1, 1)
        label = 1.0 if (x1 * x1 + x2 * x2) < RADIUS2 else 0.0
        xs.append((x1, x2))
        ys.append(label)
    return xs, ys


def sigmoid(z):
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    e = math.exp(z)
    return e / (1.0 + e)


def main():
    chunk = os.environ.get("GRIDMIND_CHUNK_INDEX")
    if chunk is not None:
        print(f"(running as parallel chunk {int(chunk) + 1})", flush=True)

    print("Generating dataset (real points, real labels)...", flush=True)
    Xtr, Ytr = make_dataset(N_TRAIN)
    Xte, Yte = make_dataset(N_TEST)
    print(f"  {N_TRAIN} training / {N_TEST} test samples · 2 features · 2 classes", flush=True)
    print(f"Network: 2 inputs -> {HIDDEN} hidden (tanh) -> 1 output (sigmoid)", flush=True)
    print(f"Training for {EPOCHS} epochs with full-batch gradient descent (lr={LR})\n", flush=True)

    # ── Initialise weights (small random) ───────────────────────────────────────
    W1 = [[random.uniform(-0.5, 0.5) for _ in range(2)] for _ in range(HIDDEN)]
    b1 = [0.0] * HIDDEN
    W2 = [random.uniform(-0.5, 0.5) for _ in range(HIDDEN)]
    b2 = 0.0

    t0 = time.time()
    for epoch in range(1, EPOCHS + 1):
        # accumulate gradients over the whole batch
        gW1 = [[0.0, 0.0] for _ in range(HIDDEN)]
        gb1 = [0.0] * HIDDEN
        gW2 = [0.0] * HIDDEN
        gb2 = 0.0
        total_loss = 0.0

        for (x1, x2), y in zip(Xtr, Ytr):
            # forward
            a1 = [0.0] * HIDDEN
            for h in range(HIDDEN):
                z = W1[h][0] * x1 + W1[h][1] * x2 + b1[h]
                a1[h] = math.tanh(z)
            z2 = b2 + sum(W2[h] * a1[h] for h in range(HIDDEN))
            yhat = sigmoid(z2)

            # binary cross-entropy loss (clamped for numerical safety)
            p = min(max(yhat, 1e-9), 1 - 1e-9)
            total_loss += -(y * math.log(p) + (1 - y) * math.log(1 - p))

            # backward
            dz2 = yhat - y                       # dL/dz2
            gb2 += dz2
            for h in range(HIDDEN):
                gW2[h] += dz2 * a1[h]
                da1 = dz2 * W2[h]
                dz1 = da1 * (1.0 - a1[h] * a1[h])  # tanh'(z) = 1 - tanh^2
                gW1[h][0] += dz1 * x1
                gW1[h][1] += dz1 * x2
                gb1[h] += dz1

        # gradient-descent update (mean gradient)
        inv = 1.0 / N_TRAIN
        for h in range(HIDDEN):
            W1[h][0] -= LR * gW1[h][0] * inv
            W1[h][1] -= LR * gW1[h][1] * inv
            b1[h] -= LR * gb1[h] * inv
            W2[h] -= LR * gW2[h] * inv
        b2 -= LR * gb2 * inv

        if epoch % 50 == 0 or epoch == 1:
            # real training accuracy this epoch
            correct = 0
            for (x1, x2), y in zip(Xtr, Ytr):
                a1 = [math.tanh(W1[h][0] * x1 + W1[h][1] * x2 + b1[h]) for h in range(HIDDEN)]
                yhat = sigmoid(b2 + sum(W2[h] * a1[h] for h in range(HIDDEN)))
                if (yhat >= 0.5) == (y >= 0.5):
                    correct += 1
            print(
                f"Epoch {epoch:3d}/{EPOCHS} | loss {total_loss * inv:.4f} | "
                f"train acc {100.0 * correct / N_TRAIN:5.2f}%",
                flush=True,
            )

    # ── Evaluate on held-out test set ───────────────────────────────────────────
    correct = 0
    for (x1, x2), y in zip(Xte, Yte):
        a1 = [math.tanh(W1[h][0] * x1 + W1[h][1] * x2 + b1[h]) for h in range(HIDDEN)]
        yhat = sigmoid(b2 + sum(W2[h] * a1[h] for h in range(HIDDEN)))
        if (yhat >= 0.5) == (y >= 0.5):
            correct += 1
    test_acc = 100.0 * correct / N_TEST

    print(f"\nTraining complete in {time.time() - t0:.1f}s.", flush=True)
    print(f"Held-out test accuracy: {test_acc:.2f}%  ({correct}/{N_TEST} correct)", flush=True)
    print("The net learned the circular decision boundary from scratch — real gradient descent.", flush=True)


if __name__ == "__main__":
    main()
