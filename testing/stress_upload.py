import os
import time
import argparse
import requests
import glob
from concurrent.futures import ThreadPoolExecutor, as_completed

UPLOAD_URL = "http://127.0.0.1:8000/api/v1/upload"

def upload_file(file_path: str):
    """
    Safely uploads a single file using streaming (rb) to prevent RAM explosion.
    Returns the tuple (status_code, response_time, error_detail).
    """
    start_time = time.time()
    try:
        # Using context manager to guarantee file handle closure
        with open(file_path, 'rb') as f:
            files = [('files', (os.path.basename(file_path), f, 'text/csv'))]
            response = requests.post(UPLOAD_URL, files=files, timeout=60)
            
        elapsed_time = time.time() - start_time
        
        detail = ""
        if response.status_code != 200:
            try:
                detail = response.json().get('detail', 'Unknown error')
            except:
                detail = response.text
                
        return response.status_code, elapsed_time, detail
        
    except requests.exceptions.RequestException as e:
        elapsed_time = time.time() - start_time
        return 0, elapsed_time, str(e)
    except Exception as e:
        elapsed_time = time.time() - start_time
        return 0, elapsed_time, f"System Error: {str(e)}"

def main():
    parser = argparse.ArgumentParser(description="AutoMerge Safe API Stress Test")
    parser.add_argument("--dir", type=str, default="generated", help="Directory containing test files")
    parser.add_argument("--workers", type=int, default=10, help="Number of concurrent workers (Safe limit: 30)")
    args = parser.parse_args()

    base_dir = os.path.dirname(os.path.abspath(__file__))
    input_dir = os.path.join(base_dir, args.dir)
    
    csv_files = glob.glob(os.path.join(input_dir, "*.csv"))
    
    print("=========================================")
    print(" AUTO MERGE - API STRESS UPLOADER ")
    print("=========================================")
    print(f"Target URL: {UPLOAD_URL}")
    print(f"Input Directory: {input_dir}")
    print(f"Files Found: {len(csv_files)}")
    print(f"Concurrent Workers: {args.workers}")
    print("=========================================")
    
    if not csv_files:
        print("[!] No CSV files found. Run generate_test_files.py first.")
        return
        
    if args.workers > 50:
        print("[WARNING] Worker count exceeds DB Pool safety limit (50).")
        print("This intentionally risks causing QueuePool TimeoutErrors.")
        confirm = input("Proceed? (y/N): ")
        if confirm.lower() != 'y':
            return

    print("\nStarting stress test. Please wait...\n")
    
    results = {
        200: 0,
        409: 0,
        500: 0,
        0: 0, # Timeouts / Network errors
        'other': 0
    }
    
    total_time = 0.0
    start_test_time = time.time()
    
    # Use ThreadPoolExecutor to upload concurrently
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        future_to_file = {executor.submit(upload_file, f): f for f in csv_files}
        
        for future in as_completed(future_to_file):
            file_path = future_to_file[future]
            try:
                status, elapsed, detail = future.result()
                total_time += elapsed
                
                if status in results:
                    results[status] += 1
                else:
                    results['other'] += 1
                
                # Print individual status for monitoring
                if status == 200:
                    print(f"[\u2713] {os.path.basename(file_path)}: 200 OK ({elapsed:.2f}s)")
                elif status == 409:
                    print(f"[-] {os.path.basename(file_path)}: 409 CONFLICT (Duplicate Detected) ({elapsed:.2f}s)")
                else:
                    print(f"[x] {os.path.basename(file_path)}: {status} ERROR - {detail[:50]} ({elapsed:.2f}s)")
                    
            except Exception as exc:
                print(f"[x] {os.path.basename(file_path)} generated an exception: {exc}")

    test_duration = time.time() - start_test_time
    avg_response_time = total_time / len(csv_files) if csv_files else 0
    
    print("\n=========================================")
    print(" STRESS TEST RESULTS ")
    print("=========================================")
    print(f"Total Time Taken:     {test_duration:.2f} seconds")
    print(f"Avg Response Time:    {avg_response_time:.2f} seconds")
    print("-----------------------------------------")
    print(f"Success (200 OK):     {results[200]}")
    print(f"Duplicate (409):      {results[409]}")
    print(f"Server Error (500):   {results[500]}")
    print(f"Timeouts/Fails (0):   {results[0]}")
    print(f"Other Errors:         {results['other']}")
    print("=========================================")

if __name__ == "__main__":
    main()
