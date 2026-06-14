"""
GridMind data-parallel demo: count primes in a large range, split across nodes.

GridMind runs this same script on every node, passing each a different slice via
env vars it sets on the process:
    GRIDMIND_CHUNK_INDEX  - this node's chunk (0 .. COUNT-1)
    GRIDMIND_CHUNK_COUNT  - total number of chunks

Each node scans only ITS contiguous block of [2, RANGE_MAX). On N nodes the work
is ~N x faster than the whole range on one machine - the "mini-supercomputer"
payoff. Run standalone (no env) and it just does the whole range as chunk 0/1.
"""
import os
import time

RANGE_MAX = 1_000_000   # total search space, split into contiguous blocks per chunk


def is_prime(n: int) -> bool:
    if n < 2:
        return False
    if n % 2 == 0:
        return n == 2
    i = 3
    while i * i <= n:
        if n % i == 0:
            return False
        i += 2
    return True


def main() -> None:
    index = int(os.environ.get("GRIDMIND_CHUNK_INDEX", "0"))
    count = max(1, int(os.environ.get("GRIDMIND_CHUNK_COUNT", "1")))

    # Contiguous block per chunk: chunk i owns [i*block, (i+1)*block).
    block = RANGE_MAX // count
    lo = index * block
    hi = RANGE_MAX if index == count - 1 else (index + 1) * block
    lo = max(2, lo)

    start = time.time()
    print(f"[chunk {index + 1}/{count}] scanning [{lo}, {hi}) for primes...", flush=True)

    found = sum(1 for n in range(lo, hi) if is_prime(n))

    elapsed = time.time() - start
    print(f"[chunk {index + 1}/{count}] DONE -> {found} primes in [{lo}, {hi}) in {elapsed:.1f}s", flush=True)


if __name__ == "__main__":
    main()
