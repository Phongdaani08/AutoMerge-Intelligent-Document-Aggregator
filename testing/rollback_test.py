import os
import sys
import psutil
import asyncio
import time
import hashlib

# Fix path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from storage.database import SessionLocal, engine
from storage.models import RawFile, RawData
from ingestion.file_parser import parse_file_in_chunks
import json

def get_memory_mb():
    process = psutil.Process(os.getpid())
    return process.memory_info().rss / (1024 * 1024)

def test_rollback(file_path: str, filename: str):
    db = SessionLocal()
    initial_count = db.query(RawData).count()
    print(f"[ROLLBACK TEST] Initial RawData count: {initial_count}")
    
    # Create fake RawFile
    db_file = RawFile(file_name="fake_rollback_test.csv", file_hash="fake_hash_123", source="test")
    db.add(db_file)
    db.commit()
    db.refresh(db_file)
    file_id = db_file.id
    
    seen_hashes = set()
    inserted_rows = 0
    chunks_processed = 0
    
    try:
        for records_chunk in parse_file_in_chunks(file_path, filename):
            valid_objects = []
            for record in records_chunk:
                row_hash = hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest()
                if row_hash in seen_hashes:
                    continue
                seen_hashes.add(row_hash)
                valid_objects.append(RawData(file_id=file_id, row_hash=row_hash, json_data=record))
                
            if valid_objects:
                db.bulk_save_objects(valid_objects)
                inserted_rows += len(valid_objects)
                valid_objects.clear()
                
            chunks_processed += 1
            print(f"[ROLLBACK TEST] Processed chunk {chunks_processed}. Inserted in session: {inserted_rows}. Simulating crash now...")
            if chunks_processed == 2:
                raise RuntimeError("INTENTIONAL CRASH FOR ROLLBACK TEST")
                
        db.commit()
    except Exception as e:
        print(f"[ROLLBACK TEST] Caught exception: {e}")
        db.rollback()
        print("[ROLLBACK TEST] db.rollback() executed.")
    finally:
        db.close()
        
    db = SessionLocal()
    final_count = db.query(RawData).count()
    fake_file_data_count = db.query(RawData).filter(RawData.file_id == file_id).count()
    print(f"[ROLLBACK TEST] Final RawData count: {final_count} (Delta: {final_count - initial_count})")
    print(f"[ROLLBACK TEST] Rows in DB for this file: {fake_file_data_count}")
    db.close()

if __name__ == "__main__":
    print(f"Base RAM: {get_memory_mb():.2f} MB")
    # use one of the 50k row files
    target_file = "testing/generated/test_data_1778468329_001.csv"
    if os.path.exists(target_file):
        test_rollback(target_file, "test_data_1778468329_001.csv")
    else:
        print(f"File not found: {target_file}")
