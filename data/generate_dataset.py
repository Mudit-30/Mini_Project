import csv
import os
import time
import psutil
import random
from pynput import keyboard, mouse

# activity counters
kb_count = 0
mouse_count = 0

# previous network snapshot
prev_net = psutil.net_io_counters()

# -------------------------
# Keyboard / Mouse Listeners
# -------------------------

def on_key_press(key):
    global kb_count
    kb_count += 1


def on_mouse_move(x, y):
    global mouse_count
    mouse_count += 1


def on_mouse_click(x, y, button, pressed):
    global mouse_count
    if pressed:
        mouse_count += 1


keyboard.Listener(on_press=on_key_press, daemon=True).start()
mouse.Listener(on_move=on_mouse_move, on_click=on_mouse_click, daemon=True).start()

# -------------------------
# CSV Setup
# -------------------------

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

file_path = os.path.join(DATA_DIR, "telemetry_dataset.csv")

header = [
    "cpu_usage_pct",
    "ram_usage_pct",
    "kb_events",
    "mouse_events",
    "net_bytes_interval",
    "process_count",
    "carbon_intensity_gco2",
    "label"
]

file_exists = os.path.isfile(file_path)

with open(file_path, "a", newline="") as f:

    writer = csv.writer(f)

    if not file_exists:
        writer.writerow(header)

    print("Telemetry collector running... Press CTRL+C to stop")

    while True:

        # CPU (1-second averaged measurement)
        cpu = psutil.cpu_percent(interval=1)

        # RAM
        ram = psutil.virtual_memory().percent

        # process count
        process_count = len(psutil.pids())

        # network delta
        net = psutil.net_io_counters()
        net_bytes = (net.bytes_sent + net.bytes_recv) - (
            prev_net.bytes_sent + prev_net.bytes_recv
        )

        prev_net = net

        # fake carbon value (until WattTime integration)
        carbon = random.uniform(180, 320)

        # -------------------------
        # Activity classification
        # -------------------------

        # HEAVY COMPUTATION
        if cpu > 60:
            label = 2

        # USER ACTIVITY
        elif kb_count > 3 or mouse_count > 10:
            label = 1

        # BACKGROUND NETWORK ACTIVITY
        elif net_bytes > 20000:
            label = 1

        # IDLE
        else:
            label = 0

        row = [
            cpu,
            ram,
            kb_count,
            mouse_count,
            net_bytes,
            process_count,
            round(carbon, 2),
            label
        ]

        writer.writerow(row)
        f.flush()

        # reset counters for next interval
        kb_count = 0
        mouse_count = 0

        # sampling window
        time.sleep(5)