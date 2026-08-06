import time
import json
import psutil
import os
from pathlib import Path

class BenchmarkLogger:
    def __init__(self, name):
        self.name = name
        self.start_time = 0
        self.process = psutil.Process(os.getpid())
        
    def start(self):
        self.start_time = time.time()
        
    def stop_and_save(self, input_file, output_file, log_path="benchmark_report.json"):
        duration = time.time() - self.start_time
        mem_usage = self.process.memory_info().rss / (1024 * 1024) # Во MB
        cpu_usage = self.process.cpu_percent(interval=0.1)
        
        in_size = os.path.getsize(input_file) / (1024 * 1024) if os.path.exists(input_file) else 0
        out_size = os.path.getsize(output_file) / (1024 * 1024) if os.path.exists(output_file) else 0
        
        report = {
            "benchmark_name": self.name,
            "execution_time_seconds": round(duration, 3),
            "ram_usage_mb": round(mem_usage, 2),
            "cpu_usage_percent": cpu_usage,
            "input_size_mb": round(in_size, 2),
            "output_size_mb": round(out_size, 2),
            "compression_ratio": round(in_size / out_size, 2) if out_size > 0 else 0
        }
        
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=4)
        return report