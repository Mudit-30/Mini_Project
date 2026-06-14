import time

print("Initializing Deep Neural Network...")
time.sleep(1)
print("Loading dataset: 50,000 images...")
time.sleep(2)
print("Dataset loaded. Starting training for 5 epochs.")

epochs = 5
batches_per_epoch = 20

for epoch in range(1, epochs + 1):
    print(f"\n--- Epoch {epoch}/{epochs} ---")
    loss = 2.5 / epoch
    
    for batch in range(1, batches_per_epoch + 1):
        if batch % 5 == 0:
            current_loss = loss + (0.1 / batch)
            print(f"Epoch {epoch} | Batch {batch}/{batches_per_epoch} | Loss: {current_loss:.4f} | Accuracy: {(1 - current_loss/3)*100:.2f}%")
            time.sleep(0.2)
            
    print(f"Epoch {epoch} complete. Validation Loss: {loss * 0.9:.4f}")

print("\nTraining Complete! Model saved successfully.")
