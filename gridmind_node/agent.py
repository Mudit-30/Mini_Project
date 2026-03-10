import psutil
import time
from pynput import keyboard, mouse

kb_count = 0
mouse_count = 0


def on_key_press(key):
    global kb_count
    kb_count += 1


def on_mouse_move(x, y):
    global mouse_count
    mouse_count += 1


class TelemetryCollector:
    def __init__(self):

        # initialize cpu measurement
        psutil.cpu_percent(interval=None)

        # start keyboard listener
        self.keyboard_listener = keyboard.Listener(on_press=on_key_press)
        self.keyboard_listener.start()

        # start mouse listener
        self.mouse_listener = mouse.Listener(on_move=on_mouse_move)
        self.mouse_listener.start()

    def collect(self):

        global kb_count, mouse_count

        cpu_usage_pct = psutil.cpu_percent(interval=None)
        ram_usage_pct = psutil.virtual_memory().percent

        net = psutil.net_io_counters()
        net_io_bytes = net.bytes_sent + net.bytes_recv

        process_count = len(psutil.pids())

        data = {
            "cpu_usage_pct": cpu_usage_pct,
            "ram_usage_pct": ram_usage_pct,
            "kb_events_per_min": kb_count,
            "mouse_events_per_min": mouse_count,
            "net_io_bytes": net_io_bytes,
            "process_count": process_count
        }

        # reset counters
        kb_count = 0
        mouse_count = 0

        return data


if __name__ == "__main__":

    collector = TelemetryCollector()

    while True:
        data = collector.collect()
        print("Collected telemetry:", data)
        time.sleep(5)