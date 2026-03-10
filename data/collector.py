import argparse
import csv
import os
import time
import psutil
from datetime import datetime

parser = argparse.ArgumentParser()
parser.add_argument("--mode", required=True, choices=["idle","soft_busy","hard_busy"])
args = parser.parse_args()

mode = args.mode

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

file_name = f"telemetry_{mode}.csv"
file_path = os.path.join(DATA_DIR, file_name)

header = [
    "timestamp",
    "cpu_usage_pct",
    "ram_usage_pct",
    "process_count",
    "mode"
]

file_exists = os.path.isfile(file_path)

with open(file_path,"a",newline="") as f:
    writer = csv.writer(f)

    if not file_exists:
        writer.writerow(header)

    print(f"Collecting {mode} data... Ctrl+C to stop")

    while True:
        row = [
            datetime.now(),
            psutil.cpu_percent(),
            psutil.virtual_memory().percent,
            len(psutil.pids()),
            mode
        ]

        writer.writerow(row)
        f.flush()
        time.sleep(5)