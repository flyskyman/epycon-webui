#!/usr/bin/env python
"""
Performance regression detection for EPYCON.
Benchmarks key operations and compares against baseline.
"""

import sys
import os
import json
import time
import tempfile
import psutil
from pathlib import Path

# Ensure UTF-8 output on all platforms
if sys.stdout.encoding != 'utf-8':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# Add epycon module to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / 'epycon'))
sys.path.insert(0, str(project_root))

import numpy as np
from iou.planters import HDFPlanter, CSVPlanter
from core.helpers import deep_override, difftimestamp

# Benchmark storage
BENCHMARK_FILE = Path(__file__).parent / 'benchmarks.json'
REGRESSION_THRESHOLD = 0.15  # 15% regression threshold

class PerformanceBenchmark:
    """Performance benchmarking and regression detection"""
    
    def __init__(self):
        self.results = {}
        self.baseline = self._load_baseline()
    
    def _load_baseline(self):
        """Load baseline benchmarks if they exist"""
        if BENCHMARK_FILE.exists():
            try:
                with open(BENCHMARK_FILE, 'r') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Warning: Could not load baseline: {e}")
        return {}
    
    def save_baseline(self):
        """Save current results as new baseline"""
        with open(BENCHMARK_FILE, 'w') as f:
            json.dump(self.results, f, indent=2)
        print(f"✅ Baseline saved to {BENCHMARK_FILE}")
    
    def measure(self, name, func, iterations=1):
        """Measure function execution time"""
        times = []
        for _ in range(iterations):
            start = time.perf_counter()
            func()
            elapsed = time.perf_counter() - start
            times.append(elapsed)
        
        avg_time = np.mean(times)
        std_time = np.std(times)
        
        # Measure Memory & CPU (single pass estimation)
        process = psutil.Process(os.getpid())
        mem_before = process.memory_info().rss / 1024 / 1024
        process.cpu_percent(interval=None)
        
        # Run once more for resource measurement
        func()
        
        mem_after = process.memory_info().rss / 1024 / 1024
        cpu_usage = process.cpu_percent(interval=None)
        mem_diff = max(0, mem_after - mem_before)

        self.results[name] = {
            'avg': avg_time,
            'std': std_time,
            'min': min(times),
            'max': max(times),
            'iterations': iterations,
            'avg_mem_mb': mem_diff,
            'avg_cpu_percent': cpu_usage
        }
        
        return avg_time, std_time
    
    def check_regression(self, name, current_time):
        """Check if current performance is regressed"""
        if name not in self.baseline:
            return None, "No baseline"
        
        baseline_time = self.baseline[name]['avg']
        regression = (current_time - baseline_time) / baseline_time
        
        if regression > REGRESSION_THRESHOLD:
            return True, f"Regression: {regression*100:.1f}% slower"
        elif regression > 0.05:
            return False, f"Slight slower: {regression*100:.1f}%"
        else:
            return False, f"OK: {regression*100:.1f}%"
    
    def report(self):
        """Generate performance report"""
        print("\n" + "="*70)
        print("PERFORMANCE BENCHMARK REPORT")
        print("="*70)
        
        for name, result in sorted(self.results.items()):
            avg = result['avg']
            std = result['std']
            mem = result.get('avg_mem_mb', 0)
            cpu = result.get('avg_cpu_percent', 0)
            
            is_regressed, msg = self.check_regression(name, avg)
            
            status = "🔴" if is_regressed else "🟢"
            
            print(f"\n{status} {name}")
            print(f"   Average: {avg*1000:.2f}ms (±{std*1000:.2f}ms)")
            print(f"   Mem: {mem:.2f} MB | CPU: {cpu:.1f}%")
            print(f"   Status: {msg}")
            
            if name in self.baseline:
                baseline = self.baseline[name]['avg']
                print(f"   Baseline: {baseline*1000:.2f}ms")


# ==================== Benchmark Functions ====================

def benchmark_hdf5_write():
    """Benchmark HDF5 write performance"""
    data = np.random.randn(100000, 2)
    counter = {'i': 0}
    
    def write_op():
        counter['i'] += 1
        h5_path = os.path.join(tempfile.gettempdir(), f'benchmark_{counter["i"]}.h5')
        try:
            with HDFPlanter(
                h5_path,
                column_names=['Ch1', 'Ch2'],
                sampling_freq=500
            ) as planter:
                planter.write(data)
        finally:
            if os.path.exists(h5_path):
                os.remove(h5_path)
    
    return write_op


def benchmark_csv_write():
    """Benchmark CSV write performance"""
    data = np.random.randn(10000, 5)
    counter = {'i': 0}
    
    def write_op():
        counter['i'] += 1
        csv_path = os.path.join(tempfile.gettempdir(), f'benchmark_{counter["i"]}.csv')
        try:
            with CSVPlanter(csv_path) as planter:
                planter.write(data)
        finally:
            if os.path.exists(csv_path):
                os.remove(csv_path)
    
    return write_op


def benchmark_config_override():
    """Benchmark config override performance"""
    cfg = {
        'app': {'settings': {'logging': {'level': 'INFO'}}},
        'data': {'processing': {'channels': 8, 'sampling_freq': 500}}
    }
    
    def override_op():
        test_cfg = cfg.copy()
        deep_override(test_cfg, ['app', 'settings', 'logging', 'level'], 'DEBUG')
        deep_override(test_cfg, ['data', 'processing', 'sampling_freq'], 1000)
    
    return override_op


def benchmark_timestamp_diff():
    """Benchmark timestamp difference calculation"""
    timestamps = [1704038400, 1704042000, 1704045600, 1704049200]
    
    def ts_op():
        for i in range(len(timestamps)-1):
            difftimestamp([timestamps[i], timestamps[i+1]])
    
    return ts_op


def benchmark_array_operations():
    """Benchmark numpy array operations"""
    data = np.random.randn(1000000, 4)
    
    def array_op():
        mean = np.mean(data, axis=0)
        std = np.std(data, axis=0)
        normalized = (data - mean) / std
        return normalized
    
    return array_op


# ==================== Main ====================

def main():
    """Run all performance benchmarks"""
    
    print("="*70)
    print("EPYCON PERFORMANCE BENCHMARK SUITE")
    print("="*70)
    
    benchmark = PerformanceBenchmark()
    
    # Define benchmarks
    benchmarks = [
        ('HDF5 Write (100K samples)', benchmark_hdf5_write(), 3),
        ('CSV Write (10K samples)', benchmark_csv_write(), 3),
        ('Config Override (4 levels)', benchmark_config_override(), 10),
        ('Timestamp Diff (4 ops)', benchmark_timestamp_diff(), 100),
        ('Array Operations (1M elements)', benchmark_array_operations(), 3),
    ]
    
    # Run benchmarks
    print("\n🏃 Running benchmarks...\n")
    regressions = 0
    
    for name, func, iterations in benchmarks:
        print(f"⏱️  {name}...", end=' ', flush=True)
        try:
            avg, std = benchmark.measure(name, func, iterations)
            is_regressed, msg = benchmark.check_regression(name, avg)
            
            if is_regressed:
                print(f"⚠️  {msg}")
                regressions += 1
            else:
                print(f"✅ {avg*1000:.2f}ms")
        except Exception as e:
            print(f"❌ Error: {e}")
    
    # Generate report
    benchmark.report()
    
    # Check for update flag
    if "--update" in sys.argv:
        print("\nUsing current results as new baseline...")
        benchmark.save_baseline()
    
    # Summary
    print("\n" + "="*70)
    if regressions > 0 and "--update" not in sys.argv:
        print(f"⚠️  REGRESSION DETECTED: {regressions} benchmark(s) regressed")
        print(f"   Threshold: {REGRESSION_THRESHOLD*100:.0f}%")
        print("   Consider investigating performance issues")
    elif "--update" in sys.argv:
        print("✅ Baseline updated. Future runs will compare against these results.")
    else:
        print("✅ NO REGRESSIONS DETECTED")
    
    print("="*70)
    
    # Save baseline if not exists
    if not Path(BENCHMARK_FILE).exists():
        print("\n💾 No baseline found. Saving current results as baseline...")
        benchmark.save_baseline()
        
    return 0


if __name__ == '__main__':
    exit_code = main()
    sys.exit(exit_code)
