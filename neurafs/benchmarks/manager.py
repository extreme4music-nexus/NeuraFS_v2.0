"""NeuraFS Benchmark Suite Execution Manager."""

import os
from neurafs.utils.logger import BenchmarkLogger
from neurafs.benchmarks.benchmark_encode import run_encode_benchmark
from neurafs.benchmarks.benchmark_decode import run_decode_benchmark


class BenchmarkManager:
    """Manages execution and reporting of NeuraFS benchmarks."""

    @staticmethod
    def run(benchmark_type: str = "decode", log_file: str = "benchmark_report.json") -> None:
        """Runs specified benchmark suite ('encode', 'decode', or 'full')."""
        print(f"\n--- Starting NeuraFS {benchmark_type.capitalize()} Benchmark Suite ---")
        logger = BenchmarkLogger(f"{benchmark_type}_benchmark")
        logger.start()

        try:
            if benchmark_type in ("encode", "full"):
                print("[Benchmark] Executing Neural Encoding Benchmark...")
                run_encode_benchmark()
                print("✅ Encoding benchmark complete.")

            if benchmark_type in ("decode", "full"):
                print("[Benchmark] Executing Neural Resynthesis/Decoding Benchmark...")
                run_decode_benchmark()
                print("✅ Decoding benchmark complete.")

            report = logger.stop_and_save("input_sample.wav", "output_sample.hcs", log_path=log_file)
            print("\n📊 --- Benchmark Summary ---")
            print(f" • Execution Time : {report['execution_time_seconds']} s")
            print(f" • Peak RAM Usage : {report['ram_usage_mb']} MB")
            print(f" • CPU Utilization: {report['cpu_usage_percent']}%")
            print(f" • Report saved to: {log_file}\n")

        except Exception as err:
            print(f"\n❌ [Benchmark Error]: {err}")