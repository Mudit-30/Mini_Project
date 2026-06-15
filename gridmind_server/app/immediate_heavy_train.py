# immediate_heavy_train.py

import time
import numpy as np
from sklearn.datasets import make_classification
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score

print("Generating heavy dataset...")

# Create large synthetic dataset
X, y = make_classification(
    n_samples=300000,
    n_features=100,
    n_informative=80,
    n_classes=5,
    random_state=42
)

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42
)

print("Starting heavy training...")

start = time.time()

# Heavy CPU training
model = RandomForestClassifier(
    n_estimators=500,
    max_depth=30,
    n_jobs=-1,  # use all CPU cores
    random_state=42
)

model.fit(X_train, y_train)

end = time.time()

preds = model.predict(X_test)
acc = accuracy_score(y_test, preds)

print(f"Training completed!")
print(f"Accuracy: {acc:.4f}")
print(f"Time taken: {end - start:.2f} sec")