from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import inspect
from typing import List
import hashlib
import json

from config.settings import settings
from utils.logger import logger
from storage.database import engine, Base, get_db, SessionLocal
from storage.models import RawFile, RawData
from ingestion.file_parser import parse_file_to_json

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

#  รับไฟล์จากผู้ใช้
@app.post("/api/v1/upload")  
async def upload_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...), 
    db: Session = Depends(get_db)
):
    logger.info("UPLOAD RECEIVED")
    # 1. Validate Extension
    import os
    _, ext = os.path.splitext(file.filename)
    if ext.lower() not in settings.ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Invalid file type")

    # 2. Read File
    content = await file.read()
    if len(content) > settings.MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=400, detail="File too large")

    # 3. Check for Duplicate File (File-Level Deduplication)
    file_hash = hashlib.sha256(content).hexdigest()
    existing_file = db.query(RawFile).filter(RawFile.file_hash == file_hash).first()
    if existing_file:
        logger.warning(f"Duplicate file upload attempt rejected: {file.filename} (Hash: {file_hash})")
        raise HTTPException(status_code=409, detail=f"File already exists with ID: {existing_file.id}")

    # 4. Create RawFile record
    db_file = RawFile(file_name=file.filename, file_hash=file_hash, source="manual")
    db.add(db_file)
    db.commit()
    db.refresh(db_file)
    
    logger.info("FILE SAVED")
    logger.info(f"[UPLOAD] Saved file record ID {db_file.id} for {file.filename}")

    # 4. Background Processing
    background_tasks.add_task(process_uploaded_file, db_file.id, content, file.filename)

    return {"message": "File uploaded successfully", "file_id": db_file.id}

def process_uploaded_file(file_id: int, content: bytes, filename: str):
    logger.info("START PROCESSING")
    logger.info(f"START PROCESSING FILE {file_id}")
    
    # 1. Background Task Isolation (CRITICAL)
    db = SessionLocal()
    
    try:
        # Parse and Clean to JSON
        records = parse_file_to_json(content, filename)
        
        # Save to RawData using Bulk Insert and Row-Level Hashing
        valid_objects = []
        seen_hashes = set()
        
        for record in records:
            # Deterministic hash for the row dictionary
            row_hash = hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest()
            
            # 2. Row-Level Deduplication (MUST NOT CRASH)
            if row_hash in seen_hashes:
                continue
            seen_hashes.add(row_hash)
            
            valid_objects.append(RawData(file_id=file_id, row_hash=row_hash, json_data=record))
            
        if valid_objects:
            db.bulk_save_objects(valid_objects)
            
        inserted_rows = len(valid_objects)
        
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

@app.get("/api/v1/preview/{file_id}")
def preview_data(file_id: int, db: Session = Depends(get_db)):
    data = db.query(RawData).filter(RawData.file_id == file_id).limit(10).all()
    if not data:
        raise HTTPException(status_code=404, detail="Data not found")
    return {"file_id": file_id, "preview": [d.json_data for d in data]}
