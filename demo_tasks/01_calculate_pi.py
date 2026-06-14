"""
GridMind demo: estimate Pi by Monte Carlo — real, honest computation.

Throws millions of random darts into the unit square and counts how many land
inside the quarter circle. The ratio (inside / total) approaches pi/4, so
4 * inside / total -> pi. No time.sleep() padding: the runtime you see is real
CPU work, which is exactly what GridMind is meant to offload to an idle node.
"""
import os
import random
import time

TOTAL_POINTS = 5_000_000


def main():
    chunk = os.environ.get("GRIDMIND_CHUNK_INDEX")
    if chunk is not None:
        print(f"(running as parallel chunk {int(chunk) + 1})", flush=True)

    print(f"Estimating Pi via Monte Carlo with {TOTAL_POINTS:,} random points...", flush=True)
    t0 = time.time()
    inside = 0
    step = TOTAL_POINTS // 10

    for i in range(1, TOTAL_POINTS + 1):
        x = random.random()
        y = random.random()
        if x * x + y * y <= 1.0:
            inside += 1
        if i % step == 0:
            print(
                f"[{i * 100 // TOTAL_POINTS:3d}%] running estimate: {4.0 * inside / i:.6f}",
                flush=True,
            )

    pi = 4.0 * inside / TOTAL_POINTS
    err = abs(pi - 3.141592653589793)
    print(f"\nFinished in {time.time() - t0:.1f}s.", flush=True)
    print(f"Final Pi estimate: {pi:.6f}  (error vs math.pi: {err:.6f})", flush=True)


if __name__ == "__main__":
    main()
