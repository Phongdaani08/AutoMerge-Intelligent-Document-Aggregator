import time
import os
import tracemalloc
import sys
import asyncio
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ingestion.file_parser import parse_file_in_chunks

def profile_pandas_chunking(file_path):
    print(f"\n--- Profiling Pandas Chunking: {os.path.basename(file_path)} ---")
    tracemalloc.start()
    start_time = time.time()
    
    chunks_processed = 0
    total_records = 0
    peak_mem_mb = 0
    
    for records in parse_file_in_chunks(file_path, file_path, chunk_size=5000):
        chunks_processed += 1
        total_records += len(records)
        current, peak = tracemalloc.get_traced_memory()
        peak_mb = peak / 10**6
        if peak_mb > peak_mem_mb:
            peak_mem_mb = peak_mb
            
    end_time = time.time()
    tracemalloc.stop()
    
    print(f"Time: {end_time - start_time:.4f}s")
    print(f"Records: {total_records}")
    print(f"Chunks: {chunks_processed}")
    print(f"Peak Memory: {peak_mem_mb:.2f} MB")

async def profile_semaphore(workers=50):
    print(f"\n--- Profiling Semaphore Governance (Workers: {workers}) ---")
    sem = asyncio.Semaphore(2)
    active_workers = 0
    max_active_workers = 0
    
    async def worker(worker_id):
        nonlocal active_workers, max_active_workers
        async with sem:
            active_workers += 1
            if active_workers > max_active_workers:
                max_active_workers = active_workers
            await asyncio.sleep(0.01) # Simulate DB Work
            active_workers -= 1
            
    start = time.time()
    tasks = [worker(i) for i in range(workers)]
    await asyncio.gather(*tasks)
    end = time.time()
    
    print(f"Max Concurrent Workers: {max_active_workers} (Expected: 2)")
    print(f"Total processing time: {end - start:.4f}s")

if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(base_dir, "benchmark_data")
    
    for size in ["10k", "50k", "100k"]:
        f_dir = os.path.join(data_dir, size)
        files = os.listdir(f_dir)
        if files:
            profile_pandas_chunking(os.path.join(f_dir, files[0]))
            
    asyncio.run(profile_semaphore(50))
