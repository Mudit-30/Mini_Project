"""
GridMind demo / proof script: shows WHICH laptop actually ran the task.

Submit this from the dashboard with priority = Urgent. The output prints the
hostname of the node that executed it -> undeniable proof the task ran on another
laptop (not the master). Use it as your pre-demo check: if the hostname is a
teammate's laptop, remote execution works. If it's the master's hostname (or the
task fails), that laptop's firewall is blocking port 50052.

It also works as a parallel-job chunk (prints its chunk index when split).
"""
import os
import socket
import time

idx = os.environ.get("GRIDMIND_CHUNK_INDEX")
cnt = os.environ.get("GRIDMIND_CHUNK_COUNT")

print(f"THIS TASK RAN ON: {socket.gethostname()}", flush=True)
if idx is not None and cnt and int(cnt) > 1:
    print(f"   (parallel chunk {int(idx) + 1}/{cnt})", flush=True)

print("Working...", flush=True)
time.sleep(2)
print("Done. If this hostname is a teammate's laptop, remote execution works.", flush=True)
