import time
import random

def estimate_pi(num_points):
    inside_circle = 0
    total_points = num_points
    
    print(f"Starting Pi estimation using Monte Carlo method with {total_points} points.")
    
    for i in range(1, total_points + 1):
        x = random.uniform(-1, 1)
        y = random.uniform(-1, 1)
        
        if x**2 + y**2 <= 1:
            inside_circle += 1
            
        if i % (total_points // 10) == 0:
            current_pi = 4 * inside_circle / i
            progress = (i / total_points) * 100
            print(f"[Progress: {progress:3.0f}%] Current Pi Estimate: {current_pi:.6f}")
            time.sleep(0.5) # Simulate heavy computation
            
    final_pi = 4 * inside_circle / total_points
    print(f"Finished! Final Pi Estimate: {final_pi:.6f}")

if __name__ == "__main__":
    estimate_pi(10000000)
