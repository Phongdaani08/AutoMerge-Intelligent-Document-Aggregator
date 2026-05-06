from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import List

from config.settings import settings
from utils.logger import logger
from storage.database import engine, Base, get_db
from storage.models import RawFile, RawData
from ingestion.file_parser import parse_file_to_json

# Create DB tables
Base.metadata.create_all(bind=engine)

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

    # 3. Create RawFile record
    db_file = RawFile(file_name=file.filename, source="manual")
    db.add(db_file)
    db.commit()
    db.refresh(db_file)
    
    logger.info("FILE SAVED")
    logger.info(f"[UPLOAD] Saved file record ID {db_file.id} for {file.filename}")

    # 4. Background Processing (Temporarily Disabled for Debugging)
    # background_tasks.add_task(process_uploaded_file, db_file.id, content, file.filename, db)
    process_uploaded_file(db_file.id, content, file.filename, db)

    return {"message": "File uploaded successfully", "file_id": db_file.id}

def process_uploaded_file(file_id: int, content: bytes, filename: str, db: Session):
    logger.info("START PROCESSING")
    logger.info(f"START PROCESSING FILE {file_id}")
    try:
        # Parse to JSON
        records = parse_file_to_json(content, filename)
        
        # Save to RawData
        inserted_rows = 0
        for record in records:
            if record: # Validate data is not empty
                db_data = RawData(file_id=file_id, json_data=record)
                db.add(db_data)
                inserted_rows += 1
        
        # Update status
        db_file = db.query(RawFile).filter(RawFile.id == file_id).first()
        if db_file:
            db_file.status = "completed"
            
        db.commit()
        logger.info(f"INSERTED {inserted_rows} ROWS INTO raw_data FOR file_id={file_id}")
        logger.info(f"FINISHED PROCESSING FILE {file_id}")
        logger.info("PREVIEW READY")
        
    except Exception as e:
        logger.error(f"[ERROR] Failed processing file ID {file_id}: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        
        db_file = db.query(RawFile).filter(RawFile.id == file_id).first()
        if db_file:
            db_file.status = "failed"
            db.commit()
        # Raise HTTPException to prevent silent failure during direct call
        raise HTTPException(status_code=500, detail=f"Pipeline error: {str(e)}")

@app.get("/api/v1/preview/{file_id}")
def preview_data(file_id: int, db: Session = Depends(get_db)):
    data = db.query(RawData).filter(RawData.file_id == file_id).limit(10).all()
    if not data:
        raise HTTPException(status_code=404, detail="Data not found")
    return {"file_id": file_id, "preview": [d.json_data for d in data]}
