#!/usr/bin/env python3
"""Simple GPU memory monitor to run alongside paper processor"""

import time
import torch
import psutil

def get_memory_info():
    """Get current memory usage information"""
    if not torch.cuda.is_available():
        return None
    
    gpu_mem = torch.cuda.memory_allocated() / 1024**3
    gpu_reserved = torch.cuda.memory_reserved() / 1024**3
    gpu_total = torch.cuda.get_device_properties(0).total_memory / 1024**3
    
    cpu_mem = psutil.virtual_memory()
    
    return {
        'gpu_allocated': gpu_mem,
        'gpu_reserved': gpu_reserved,
        'gpu_total': gpu_total,
        'gpu_allocated_percent': (gpu_mem / gpu_total) * 100,
        'gpu_reserved_percent': (gpu_reserved / gpu_total) * 100,
        'cpu_percent': cpu_mem.percent,
    }

def monitor_memory(interval=5):
    """Monitor memory usage every interval seconds"""
    print("GPU Memory Monitor - Press Ctrl+C to stop")
    print("=" * 80)
    print(f"{'Time':<8} {'GPU Alloc':<10} {'GPU Res':<10} {'GPU Alloc%':<12} {'GPU Res%':<12} {'CPU%':<8}")
    print("=" * 80)
    
    try:
        while True:
            mem_info = get_memory_info()
            if mem_info:
                current_time = time.strftime("%H:%M:%S")
                print(f"{current_time:<8} "
                      f"{mem_info['gpu_allocated']:<10.2f} "
                      f"{mem_info['gpu_reserved']:<10.2f} "
                      f"{mem_info['gpu_allocated_percent']:<12.1f} "
                      f"{mem_info['gpu_reserved_percent']:<12.1f} "
                      f"{mem_info['cpu_percent']:<8.1f}")
            else:
                print("CUDA not available")
            
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nMonitoring stopped.")

if __name__ == "__main__":
    monitor_memory()
