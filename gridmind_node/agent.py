import psutil
import time

class TelemetryCollector:
    def __init__(self):
        # We store initial state to calculate deltas
        psutil.cpu_percent(interval=None)
        
    def collect(self):
        # Gather basic telemetry data
        cpu_usage_pct = psutil.cpu_percent(interval=None)
        ram = psutil.virtual_memory()
        ram_usage_pct = ram.percent
        
        # Simplified for now: just returning CPU and RAM
        return {
            "cpu_usage_pct": cpu_usage_pct,
            "ram_usage_pct": ram_usage_pct,
            "kb_events_per_min": 0,
            "mouse_events_per_min": 0,
            "net_io_bytes": 0,
            "process_count": len(psutil.pids())
        }

if __name__ == "__main__":
    collector = TelemetryCollector()
    while True:
        data = collector.collect()
        print(f"Collected telemetry: {data}")
        time.sleep(5)
