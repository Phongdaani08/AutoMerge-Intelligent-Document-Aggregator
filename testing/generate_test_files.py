import csv
import random
import os
import argparse
import uuid
import datetime

def generate_csv(file_path: str, rows: int, is_duplicate_of: str = None):
    """
    Generate a safe CSV file for load testing.
    If is_duplicate_of is provided, it copies that file exactly.
    """
    if is_duplicate_of and os.path.exists(is_duplicate_of):
        import shutil
        shutil.copy2(is_duplicate_of, file_path)
        print(f"[-] Created DUPLICATE file: {file_path}")
        return

    # To avoid memory issues, we stream writes row by row
    with open(file_path, mode='w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        # Header
        writer.writerow(["customer_id", "invoice_no", "email", "amount", "timestamp", "country", "status"])
        
        for _ in range(rows):
            writer.writerow([
                f"CUST_{random.randint(1000, 99999)}",
                f"INV_{uuid.uuid4().hex[:8].upper()}",
                f"user_{random.randint(1, 10000)}@example.com",
                round(random.uniform(10.0, 5000.0), 2),
                (datetime.datetime.now() - datetime.timedelta(days=random.randint(0, 365))).isoformat(),
                random.choice(["TH", "SG", "US", "JP", "UK"]),
                random.choice(["PAID", "PENDING", "FAILED"])
            ])
    print(f"[+] Generated file: {file_path} ({rows} rows)")

def main():
    parser = argparse.ArgumentParser(description="AutoMerge Safe Test Data Generator")
    parser.add_argument("--files", type=int, default=5, help="Number of files to generate")
    parser.add_argument("--rows", type=int, default=1000, help="Rows per file")
    parser.add_argument("--duplicate", action="store_true", help="Generate identical files to test 409 Conflict")
    parser.add_argument("--dir", type=str, default="generated", help="Output directory inside testing folder")
    
    args = parser.parse_args()

    # Ensure output directory exists securely
    base_dir = os.path.dirname(os.path.abspath(__file__))
    output_dir = os.path.join(base_dir, args.dir)
    os.makedirs(output_dir, exist_ok=True)
    
    # Clear old files so tests don't mix up
    import glob
    old_files = glob.glob(os.path.join(output_dir, "*.csv"))
    for f in old_files:
        try:
            os.remove(f)
        except:
            pass
    
    print("=========================================")
    print(" AUTO MERGE - TEST DATA GENERATOR ")
    print("=========================================")
    print(f"Target Directory: {output_dir}")
    print(f"Files to generate: {args.files}")
    print(f"Rows per file: {args.rows}")
    print(f"Duplicate Mode: {args.duplicate}")
    print(f"Old files cleared: {len(old_files)}")
    print("=========================================")

    # Disk usage warning check
    estimated_size_mb = (args.files * args.rows * 100) / (1024 * 1024)
    if estimated_size_mb > 500:
        print(f"[WARNING] Estimated disk usage is {estimated_size_mb:.2f} MB.")
        confirm = input("Are you sure you want to proceed? (y/N): ")
        if confirm.lower() != 'y':
            print("Aborted.")
            return

    import time
    timestamp_prefix = int(time.time())
    
    first_file_path = None
    for i in range(1, args.files + 1):
        filename = f"test_data_{timestamp_prefix}_{i:03d}.csv"
        file_path = os.path.join(output_dir, filename)
        
        if args.duplicate and i > 1:
            generate_csv(file_path, args.rows, is_duplicate_of=first_file_path)
        else:
            generate_csv(file_path, args.rows)
            if i == 1:
                first_file_path = file_path

    print("\nGeneration completed safely.")

if __name__ == "__main__":
    main()
