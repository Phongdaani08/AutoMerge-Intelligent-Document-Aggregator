import asyncio
import httpx
import time
import os

async def upload_file(client, file_path):
    start = time.time()
    try:
        with open(file_path, 'rb') as f:
            # Re-read file content into memory for httpx to prevent file descriptor limits or async IO blocking
            # but for 100k rows (10MB), it's fine.
            content = f.read()
            
        files = {'files': (os.path.basename(file_path), content, 'text/csv')}
        resp = await client.post('http://localhost:8000/api/v1/upload', files=files, timeout=300.0)
        status = resp.status_code
    except Exception as e:
        status = str(e)
    end = time.time()
    return end - start, status

async def stress_test(workers, file_path):
    size_mb = os.path.getsize(file_path) / (1024 * 1024)
    print(f"\n--- Stress Test: {workers} workers | File: {os.path.basename(file_path)} ({size_mb:.2f} MB) ---")
    
    start_time = time.time()
    
    async with httpx.AsyncClient(limits=httpx.Limits(max_connections=100, max_keepalive_connections=20)) as client:
        tasks = [upload_file(client, file_path) for _ in range(workers)]
        results = await asyncio.gather(*tasks)
        
    end_time = time.time()
    
    times = [r[0] for r in results if isinstance(r[1], int) and r[1] == 200]
    errors = [r[1] for r in results if not (isinstance(r[1], int) and r[1] == 200)]
    
    avg_time = sum(times) / len(times) if times else 0
    total_time = end_time - start_time
    
    print(f"Total Time: {total_time:.2f}s")
    print(f"Avg Response Time (per upload): {avg_time:.2f}s")
    print(f"Success: {len(times)}, Errors: {len(errors)}")
    if errors:
        print(f"Sample error: {errors[0]}")

async def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(base_dir, "benchmark_data")
    
    f10k = os.path.join(data_dir, "10k", os.listdir(os.path.join(data_dir, "10k"))[0])
    f50k = os.path.join(data_dir, "50k", os.listdir(os.path.join(data_dir, "50k"))[0])
    f100k = os.path.join(data_dir, "100k", os.listdir(os.path.join(data_dir, "100k"))[0])
    
    files = [f10k, f50k, f100k]
    workers_list = [1, 5, 20, 50]
    
    for f in files:
        for w in workers_list:
            await stress_test(w, f)
            await asyncio.sleep(2) # Give server a breather

if __name__ == "__main__":
    asyncio.run(main())
