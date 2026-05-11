from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import inspect
from typing import List
import hashlib
import json
import os
import tempfile
import shutil
import asyncio
import pandas as pd

from config.settings import settings
from utils.logger import logger
from storage.database import engine, Base, get_db, SessionLocal
from storage.models import RawFile, RawData
from ingestion.file_parser import parse_file_in_chunks

# Auto-Sync Database Schema (Local Dev / SQLite only)
def init_db():
    inspector = inspect(engine)
    # Check if table exists
    if inspector.has_table("raw_files"):
        columns = [col['name'] for col in inspector.get_columns("raw_files")]
        # Detect if our new 'file_hash' column is missing
        if "file_hash" not in columns:
            logger.warning("Database schema mismatch detected -> recreating DB")
            Base.metadata.drop_all(bind=engine)
            
    # Create tables (will only create if they don't exist)
    Base.metadata.create_all(bind=engine)

init_db()

app = FastAPI(title=settings.PROJECT_NAME, version=settings.VERSION)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "Welcome to AutoMerge API"}

#  รับไฟล์จากผู้ใช้แบบ Multi-File
@app.post("/api/v1/upload")  
async def upload_file(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...), 
    db: Session = Depends(get_db)
):
    logger.info(f"UPLOAD RECEIVED: {len(files)} files")
    
    saved_files = []
    
    try:
        # Process all files
        for file in files:
            # 1. Validate Extension
            _, ext = os.path.splitext(file.filename)
            if ext.lower() not in settings.ALLOWED_EXTENSIONS:
                raise HTTPException(status_code=400, detail=f"Invalid file type: {file.filename}")

            # 2. Stream to Temp File & Calculate Hash Safely
            temp_fd, temp_path = tempfile.mkstemp(suffix=ext, prefix="automerge_")
            
            file_size = 0
            sha256_hash = hashlib.sha256()
            
            try:
                with os.fdopen(temp_fd, 'wb') as f_out:
                    while chunk := await file.read(8192):
                        file_size += len(chunk)
                        if file_size > settings.MAX_UPLOAD_SIZE:
                            # Do NOT delete file here, exit 'with' block cleanly to release OS lock
                            raise HTTPException(status_code=400, detail=f"File too large: {file.filename}")
                        
                        sha256_hash.update(chunk)
                        f_out.write(chunk)
                        
                file_hash = sha256_hash.hexdigest()
                
                # 3. Check for Duplicate File (File-Level Deduplication)
                existing_file = db.query(RawFile).filter(RawFile.file_hash == file_hash).first()
                if existing_file:
                    logger.warning(f"Duplicate file upload attempt rejected: {file.filename} (Hash: {file_hash})")
                    raise HTTPException(status_code=409, detail=f"File already exists with ID: {existing_file.id} (Filename: {file.filename})")

                # 4. Create RawFile record
                db_file = RawFile(file_name=file.filename, file_hash=file_hash, source="manual")
                db.add(db_file)
                db.commit()
                db.refresh(db_file)
                
                # Read first 10 rows for instant preview
                preview_data = []
                try:
                    if file.filename.endswith('.csv'):
                        df_preview = pd.read_csv(temp_path, nrows=10)
                        # Replace NaN with None for JSON serialization
                        df_preview = df_preview.where(pd.notnull(df_preview), None)
                        preview_data = df_preview.to_dict(orient='records')
                    elif file.filename.endswith(('.xls', '.xlsx')):
                        df_preview = pd.read_excel(temp_path, nrows=10)
                        df_preview = df_preview.where(pd.notnull(df_preview), None)
                        preview_data = df_preview.to_dict(orient='records')
                except Exception as e:
                    logger.warning(f"Failed to generate instant preview for {file.filename}: {e}")
                
                saved_files.append({"id": db_file.id, "filename": file.filename, "temp_path": temp_path, "preview": preview_data})
                
                logger.info(f"[UPLOAD] Saved file record ID {db_file.id} for {file.filename}")
                
            except Exception as inner_e:
                # Cleanup the current failed file before raising
                if os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except Exception as clean_err:
                        logger.error(f"Failed to clean temp file {temp_path}: {clean_err}")
                raise inner_e

        # 5. Background Processing (Per File)
        for sf in saved_files:
            background_tasks.add_task(process_uploaded_file, sf["id"], sf["temp_path"], sf["filename"])

        return {
            "message": f"{len(saved_files)} file(s) uploaded successfully", 
            "files": [{"id": sf["id"], "filename": sf["filename"], "preview": sf.get("preview", [])} for sf in saved_files]
        }

    except Exception as outer_e:
        # If the endpoint fails for any reason (e.g. file 3 of 5 fails validation),
        # we must clean up temp files for files 1 and 2, because BackgroundTasks will NEVER run.
        for sf in saved_files:
            if os.path.exists(sf["temp_path"]):
                try:
                    os.remove(sf["temp_path"])
                except Exception as clean_err:
                    logger.error(f"Failed to clean orphaned temp file {sf['temp_path']}: {clean_err}")
        raise outer_e

# Global semaphore for Phase 1 Concurrency Governance
ingestion_semaphore = None

def get_ingestion_semaphore():
    global ingestion_semaphore
    if ingestion_semaphore is None:
        ingestion_semaphore = asyncio.Semaphore(2)
    return ingestion_semaphore

async def process_uploaded_file(file_id: int, file_path: str, filename: str):
    sem = get_ingestion_semaphore()
    logger.info(f"Task for file {file_id} queued. Waiting for semaphore...")
    async with sem:
        logger.info(f"Semaphore acquired for file {file_id}. Starting background thread...")
        await asyncio.to_thread(process_uploaded_file_sync, file_id, file_path, filename)

def process_uploaded_file_sync(file_id: int, file_path: str, filename: str):
    logger.info("START PROCESSING")
    logger.info(f"START PROCESSING FILE {file_id}")
    
    # 1. Background Task Isolation (CRITICAL)
    db = SessionLocal()
    
    try:
        seen_hashes = set()
        inserted_rows = 0
        
        # Parse and Clean in chunks
        for records_chunk in parse_file_in_chunks(file_path, filename):
            valid_objects = []
            
            for record in records_chunk:
                # Deterministic hash for the row dictionary
                row_hash = hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest()
                
                # 2. Row-Level Deduplication (MUST NOT CRASH)
                if row_hash in seen_hashes:
                    continue
                seen_hashes.add(row_hash)
                
                valid_objects.append(RawData(file_id=file_id, row_hash=row_hash, json_data=record))
                
            # 3. Chunk-Safe Insert
            if valid_objects:
                db.bulk_save_objects(valid_objects)
                inserted_rows += len(valid_objects)
                # clear list explicitly for memory safety
                valid_objects.clear()
        
        # Update status
        db_file = db.query(RawFile).filter(RawFile.id == file_id).first()
        if db_file:
            db_file.status = "completed"
            
        db.commit()
        logger.info(f"INSERTED {inserted_rows} ROWS INTO raw_data FOR file_id={file_id} (Bulk Insert)")
        logger.info(f"FINISHED PROCESSING FILE {file_id}")
        logger.info("PREVIEW READY")
        
    except Exception as e:
        db.rollback() # <--- CRITICAL FIX: Ensure clean session on error
        logger.error(f"[ERROR] Failed processing file ID {file_id}: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        
        db_file = db.query(RawFile).filter(RawFile.id == file_id).first()
        if db_file:
            db_file.status = "failed"
            db.commit()
            
        raise HTTPException(
            status_code=500, 
            detail="ไม่สามารถประมวลผลไฟล์ได้ กรุณาตรวจสอบข้อมูล (ERR-5001)"
        )
    finally:
        db.close()
        # 4. Cleanup Temp File
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                logger.info(f"Cleaned up temp file: {file_path}")
            except Exception as e:
                logger.error(f"Failed to clean temp file {file_path}: {str(e)}")
@app.get("/api/v1/preview/{file_id}")
def preview_data(file_id: int, db: Session = Depends(get_db)):
    data = db.query(RawData).filter(RawData.file_id == file_id).order_by(RawData.id.asc()).limit(10).all()
    if not data:
        raise HTTPException(status_code=404, detail="Data not found")
    return {"file_id": file_id, "preview": [d.json_data for d in data]}

@app.get("/api/v1/status/{file_id}")
def get_file_status(file_id: int, db: Session = Depends(get_db)):
    db_file = db.query(RawFile).filter(RawFile.id == file_id).first()
    if not db_file:
        raise HTTPException(status_code=404, detail="File not found")
    return {"file_id": file_id, "status": db_file.status}
