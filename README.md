# AutoMerge — Intelligent Document Aggregator

ระบบรับ-ประมวลผลและจัดเก็บไฟล์ CSV/Excel แบบ Asynchronous พร้อม Deduplication สองชั้น

---

## Overview

AutoMerge เป็น Backend Ingestion Pipeline ที่รับไฟล์ CSV และ Excel จาก Frontend แล้วประมวลผลในเบื้องหลังแบบ Non-blocking โดยใช้ FastAPI Background Tasks ร่วมกับ asyncio Semaphore เพื่อควบคุม Concurrency

ระบบออกแบบมาให้รองรับไฟล์ขนาดใหญ่อย่างปลอดภัย โดยไม่โหลดทุกอย่างลง RAM พร้อมกัน และมีกลไก Deduplication ทั้งในระดับไฟล์ (SHA-256 File Hash) และระดับแถว (SHA-256 Row Hash) เพื่อป้องกันข้อมูลซ้ำในฐานข้อมูล

**สถานะปัจจุบัน:** MVP-ready / Internal Tool — ยังไม่พร้อมสำหรับ Public Production (ดูส่วน Known Limitations)

---

## Features

### Backend

| Feature | รายละเอียด |
|---|---|
| Multi-file Upload | รับหลายไฟล์ใน Request เดียว |
| File-Level Deduplication | SHA-256 hash ของ content ทั้งไฟล์ |
| Row-Level Deduplication | SHA-256 hash ของแต่ละแถว (deterministic) |
| Chunk Ingestion (CSV) | `pd.read_csv(chunksize=5000)` — True Streaming |
| Excel Ingestion | `pd.read_excel()` + manual slicing |
| Background Processing | FastAPI `BackgroundTasks` + `asyncio.to_thread()` |
| Semaphore Control | จำกัดการประมวลผลพร้อมกันสูงสุด 2 ไฟล์ |
| Instant Preview | อ่าน 10 แถวแรกขณะ Upload (ก่อน Background Task) |
| Rollback Safety | `db.rollback()` ทุกครั้งที่เกิด Exception |
| Temp File Cleanup | ลบไฟล์ชั่วคราวอัตโนมัติหลังประมวลผล |
| Status Polling | Endpoint ติดตามสถานะ `uploaded → processing → completed/failed` |

### Frontend

| Feature | รายละเอียด |
|---|---|
| Batch Upload | ส่งทีละ 5 ไฟล์ต่อ Request |
| Retry Mechanism | Retry สูงสุด 3 ครั้ง เฉพาะ Network Error / 5xx |
| Polling System | ตรวจสถานะทุก 2 วินาที สูงสุด 30 ครั้ง (60 วินาที) |
| XSS Prevention | ใช้ `textContent` / `createElement` แทน `innerHTML` ทุกจุด |
| Encapsulated State | `AppState` IIFE Module แทน Global Variables |
| Restricted CORS | Origin จาก `.env` แทน `allow_origins=["*"]` |
| Config Centralization | `config.js` สำหรับ API Base URL |

---

## System Architecture

```
Browser (Vanilla JS)
    │
    │  POST /api/v1/upload  (multipart/form-data)
    │  Batch: 5 files/request, Retry: max 3x
    ▼
┌─────────────────────────────────────────────────┐
│  FastAPI  (api/main.py)                         │
│                                                 │
│  [Synchronous - Request Thread]                 │
│  1. Validate file extension                     │
│  2. Stream to temp file + compute SHA-256       │
│  3. Duplicate check → query RawFile.file_hash   │
│  4. Create RawFile record (status=uploaded)     │
│  5. Read instant preview (10 rows, raw)         │
│  6. Schedule background task → return response  │
│                                                 │
│  [Asynchronous - Background]                    │
│  asyncio.Semaphore(2)  ← max 2 concurrent       │
│  asyncio.to_thread()   ← off event loop         │
│       │                                         │
│       ▼                                         │
│  process_uploaded_file_sync()                   │
│  ├─ parse_file_in_chunks()  (chunk=5000 rows)   │
│  ├─ SHA-256 row hash per record                 │
│  ├─ in-memory dedup (seen_hashes set)           │
│  ├─ db.bulk_save_objects() per chunk            │
│  └─ status = completed / failed                 │
└─────────────────────────────────────────────────┘
    │
    ▼
PostgreSQL
  raw_files  (file metadata + hash + status)
  raw_data   (row hash + json_data)
```

---

## Tech Stack

| Layer | Technology | Version |
|---|---|---|
| Backend Framework | FastAPI | 0.135+ |
| ORM | SQLAlchemy | 2.0+ |
| Data Processing | Pandas | 2.x |
| Excel Support | openpyxl | 3.x |
| Database | PostgreSQL | 14+ |
| DB Driver | psycopg2-binary | 2.9+ |
| Config Management | pydantic-settings | 2.x |
| ASGI Server | Uvicorn | 0.45+ |
| Frontend | Vanilla JS + HTML + CSS | — |

---

## Folder Structure

```
AutoMerge/
│
├── api/
│   └── main.py              # FastAPI app, upload endpoint, background tasks
│
├── config/
│   └── settings.py          # pydantic-settings config (loads from .env)
│
├── ingestion/
│   └── file_parser.py       # CSV/Excel chunked parser + row cleaner
│
├── storage/
│   ├── database.py          # SQLAlchemy engine + connection pool
│   └── models.py            # RawFile, RawData models
│
├── utils/
│   └── logger.py            # Centralized logger (stdout)
│
├── mapping/                 # Reserved — schema mapping layer (not implemented)
├── processing/              # Reserved — transformation layer (not implemented)
│
├── frontend/
│   ├── index.html
│   ├── app.js               # App orchestration
│   ├── css/
│   │   ├── tokens.css       # CSS Custom Properties (design tokens)
│   │   ├── layout.css       # Page structure
│   │   └── components.css   # UI components
│   └── js/
│       ├── config.js        # API_BASE_URL
│       ├── state.js         # AppState (encapsulated IIFE)
│       ├── api.js           # Reserved — API layer (Phase B4)
│       └── renderer.js      # Reserved — DOM rendering (Phase B5)
│
├── testing/                 # Test scripts
├── .env                     # Local secrets (gitignored)
├── .env.example             # Template (committed)
├── requirements.txt
└── README.md
```

---

## Upload Flow

### ขั้นตอนการทำงานจาก Browser ถึง Database

```
1. User เลือกไฟล์ → fileInput.change event
2. Frontend จัดคิวไฟล์ใน AppState._files
3. กด Upload → แบ่ง batch ทีละ 5 ไฟล์
4. POST /api/v1/upload

   Backend (Synchronous):
   ├─ ตรวจ Extension (.csv / .xlsx / .xls)
   ├─ Stream ไฟล์ → temp file (8192 bytes/chunk)
   ├─ คำนวณ SHA-256 ระหว่าง stream (ไม่ต้องอ่านซ้ำ)
   ├─ Query DB: มี file_hash นี้อยู่แล้วไหม?
   │   └─ ใช่ → return status="duplicate"
   ├─ INSERT RawFile (status=uploaded)
   ├─ อ่าน 10 แถวแรก → instant preview
   └─ ลงทะเบียน background task

5. Response กลับ Frontend ทันที (ไม่รอ processing)
6. Frontend เริ่ม Polling ทุก 2 วินาที

   Backend (Background - Async):
   ├─ รอ Semaphore (max 2 concurrent)
   ├─ asyncio.to_thread() → thread pool
   ├─ parse_file_in_chunks() → yield 5000 rows/chunk
   ├─ ต่อแถว: SHA-256 hash → dedup → bulk insert
   ├─ UPDATE status = "completed"
   └─ ลบ temp file

7. Frontend Polling ได้รับ status=completed → แสดงผล
```

---

## Hashing & Deduplication Strategy

ระบบใช้ Deduplication 2 ชั้นเป็นอิสระต่อกัน

### ชั้นที่ 1: File-Level Deduplication

```python
# คำนวณ SHA-256 ขณะ Stream ไฟล์ — ไม่ต้องโหลดทั้งไฟล์ก่อน
sha256_hash = hashlib.sha256()
while chunk := await file.read(8192):
    sha256_hash.update(chunk)
    f_out.write(chunk)

file_hash = sha256_hash.hexdigest()

# Query ก่อน Insert
existing = db.query(RawFile).filter(RawFile.file_hash == file_hash).first()
if existing:
    return {"status": "duplicate"}
```

- เปรียบเทียบ Content จริง ไม่ใช่ชื่อไฟล์
- `file_hash` column มี `UNIQUE` constraint ใน DB
- ป้องกันการอัปโหลดไฟล์เดิมซ้ำโดยสมบูรณ์

### ชั้นที่ 2: Row-Level Deduplication

```python
seen_hashes = set()  # in-memory per file

for record in records_chunk:
    # sort_keys=True เพื่อให้ Hash เป็น Deterministic
    # ไม่ว่า key จะเรียงลำดับอย่างไรใน dict
    row_hash = hashlib.sha256(
        json.dumps(record, sort_keys=True).encode()
    ).hexdigest()

    if row_hash in seen_hashes:
        continue  # ข้ามแถวซ้ำ

    seen_hashes.add(row_hash)
    valid_objects.append(RawData(row_hash=row_hash, json_data=record))
```

- `seen_hashes` set ทำงานใน RAM ต่อไฟล์หนึ่ง
- `UniqueConstraint('file_id', 'row_hash')` ใน DB เป็น Safety Net อีกชั้น
- ใช้ `sort_keys=True` เพื่อให้ `{"b":1,"a":2}` กับ `{"a":2,"b":1}` ได้ Hash เดียวกัน

### ข้อสำคัญด้าน Architecture

> **ระวัง:** Instant Preview ที่แสดงหลัง Upload ทันที อ่านมาจากไฟล์ดิบก่อน Background Task ทำงาน จึงอาจแสดงแถวซ้ำได้ ข้อมูลที่ Deduplicate จริงอยู่ใน `raw_data` table และสามารถดึงได้จาก `GET /api/v1/preview/{file_id}` หลัง status=completed

---

## Concurrency & Background Processing

### ทำไมต้องใช้ Semaphore

FastAPI Background Tasks รัน async functions บน Event Loop เดียวกัน การประมวลผลไฟล์ใช้ Pandas ซึ่งเป็น CPU-bound และ IO-bound พร้อมกัน ถ้าปล่อยให้รันพร้อมกันทุกไฟล์จะกิน RAM และ CPU จนระบบล่ม

```python
ingestion_semaphore = asyncio.Semaphore(2)  # max 2 ไฟล์พร้อมกัน

async def process_uploaded_file(file_id, file_path, filename):
    async with sem:  # ไฟล์ที่ 3+ จะรอที่นี่
        await asyncio.to_thread(
            process_uploaded_file_sync,  # Blocking function
            file_id, file_path, filename
        )
```

- `asyncio.Semaphore(2)` → ไม่เกิน 2 ไฟล์ประมวลผลพร้อมกัน
- `asyncio.to_thread()` → รัน Pandas บน Thread Pool แยกออกจาก Event Loop
- Event Loop ไม่ถูก Block → Server ยังรับ Request อื่นได้ระหว่างประมวลผล

### Chunk Ingestion — ทำไมต้อง Chunk

```python
# CSV: True Streaming — pandas อ่านทีละ 5000 แถว
for chunk_df in pd.read_csv(file_path, chunksize=5000):
    records = process_chunk(chunk_df)
    # insert แล้วทิ้ง chunk ออกจาก memory

# Excel: ไม่รองรับ chunksize natively
# ต้องโหลดทั้งไฟล์ก่อน แล้วค่อย slice เอง
df = pd.read_excel(file_path)
for start in range(0, len(df), 5000):
    chunk_df = df.iloc[start:start+5000].copy()
```

> **ข้อจำกัด Excel:** ไฟล์ Excel ขนาดใหญ่ถูกโหลดทั้งหมดลง RAM ก่อน ทำให้ไฟล์ Excel 100MB อาจใช้ RAM หลาย GB ขอแนะนำให้จำกัดขนาด Excel ไว้ที่ไม่เกิน 20MB ต่อไฟล์

---

## Security Improvements

การปรับปรุงด้านความปลอดภัยที่ได้ทำไปแล้ว (Phase A Refactor):

| รายการ | ก่อน | หลัง |
|---|---|---|
| XSS | `innerHTML` + User data | `textContent` + `createElement` |
| CORS | `allow_origins=["*"]` | Origins จาก `ALLOWED_ORIGINS` ใน `.env` |
| API URL | Hardcoded `localhost:8000` | `config.js` centralized |
| Env Secrets | ไม่มี template | `.env.example` พร้อม commit |
| Polling | ไม่มี timeout | maxAttempts=30 (60 วินาที) |

**ยังไม่มี (ดู Known Limitations):**
- Authentication / Authorization
- Rate Limiting
- HTTPS enforcement
- Input sanitization บน filename ก่อนบันทึก DB

---

## Setup Instructions

### Requirements

- Python 3.10+
- PostgreSQL 14+
- Node.js (ไม่จำเป็น — ใช้ Python HTTP Server แทนได้)

### 1. Clone และ Setup

```bash
git clone https://github.com/Phongdaani08/AutoMerge-Intelligent-Document-Aggregator.git
cd AutoMerge-Intelligent-Document-Aggregator
```

### 2. สร้าง Virtual Environment

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux/macOS
source .venv/bin/activate
```

### 3. ติดตั้ง Dependencies

```bash
pip install -r requirements.txt
```

### 4. ตั้งค่า Environment Variables

```bash
cp .env.example .env
# แก้ไขค่าใน .env ให้ตรงกับ Environment ของคุณ
```

### 5. สร้าง Database

```bash
# สร้าง database ชื่อ automerge_raw ใน PostgreSQL ของคุณก่อน
psql -U postgres -c "CREATE DATABASE automerge_raw;"
```

Database Schema จะถูกสร้างอัตโนมัติตอน Server เริ่มต้น ผ่าน `Base.metadata.create_all()`

---

## Environment Variables

```bash
# .env.example

# --- Database ---
DATABASE_URL=postgresql://postgres:YOUR_PASSWORD@localhost:5433/automerge_raw

# --- Security ---
# สร้าง Secret Key ด้วย: python -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY=REPLACE_WITH_SECURE_RANDOM_64_HEX_STRING
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# --- Upload ---
MAX_UPLOAD_SIZE=10485760     # 10MB in bytes
UPLOAD_DIR=temp_uploads

# --- CORS (คั่นหลาย origin ด้วย comma) ---
# Local Dev:
ALLOWED_ORIGINS=http://localhost:5500,http://127.0.0.1:5500
# Production: เปลี่ยนเป็น domain จริง
# ALLOWED_ORIGINS=https://app.yourdomain.com
```

| Variable | Default | คำอธิบาย |
|---|---|---|
| `DATABASE_URL` | — | PostgreSQL connection string |
| `SECRET_KEY` | — | JWT secret (เปลี่ยนก่อน deploy) |
| `MAX_UPLOAD_SIZE` | 10485760 | ขนาดไฟล์สูงสุด (bytes) |
| `UPLOAD_DIR` | temp_uploads | โฟลเดอร์ไฟล์ชั่วคราว |
| `ALLOWED_ORIGINS` | localhost:5500 | Origins ที่อนุญาต CORS |

---

## Running the Project

### Backend

```bash
# Development (Auto-reload)
.venv\Scripts\python.exe -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

# Production (ปรับ workers ตาม CPU)
.venv\Scripts\python.exe -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers 2
```

### Frontend

```bash
# วิธีที่ 1: Python HTTP Server (แนะนำ)
.venv\Scripts\python.exe -m http.server 5500 --directory frontend

# วิธีที่ 2: VS Code Live Server
# คลิกขวาที่ index.html → Open with Live Server
```

> **สำคัญ:** ห้ามเปิด `index.html` โดยตรง (double-click) เพราะ Browser จะส่ง `Origin: null` ซึ่งถูก CORS Block ต้องเปิดผ่าน HTTP Server เสมอ

### API Endpoints

| Method | Endpoint | คำอธิบาย |
|---|---|---|
| GET | `/` | Health check |
| POST | `/api/v1/upload` | อัปโหลดไฟล์ (multipart/form-data) |
| GET | `/api/v1/status/{file_id}` | ตรวจสถานะการประมวลผล |
| GET | `/api/v1/preview/{file_id}` | ดู 10 แถวแรกจาก DB (หลัง dedup) |
| GET | `/docs` | Swagger UI |

### ตัวอย่าง API Request

```bash
# Upload ไฟล์
curl -X POST http://localhost:8000/api/v1/upload \
  -F "files=@data.csv" \
  -F "files=@report.xlsx"

# ตรวจสถานะ
curl http://localhost:8000/api/v1/status/1

# ดู Preview จาก DB (deduplicated)
curl http://localhost:8000/api/v1/preview/1
```

ตัวอย่าง Response จาก Upload:

```json
{
  "success_count": 2,
  "duplicate_count": 0,
  "failed_count": 0,
  "results": [
    {
      "filename": "data.csv",
      "status": "success",
      "file_id": 1,
      "preview": [
        {"name": "Alice", "age": 30},
        {"name": "Bob", "age": 25}
      ]
    }
  ]
}
```

---

## Known Limitations

ข้อจำกัดที่ทราบอยู่และยังไม่ได้แก้ไข:

| ข้อจำกัด | ผลกระทบ | แนวทางแก้ไข |
|---|---|---|
| ไม่มี Authentication | ใครก็ Upload ได้ | JWT Middleware |
| ไม่มี Rate Limiting | DDoS ได้ง่าย | SlowAPI / Nginx limit |
| Excel โหลด Full RAM | OOM บนไฟล์ใหญ่ | openpyxl row iteration |
| Single-node architecture | ไม่ scale horizontal | Celery + Redis |
| ไม่มี Distributed Queue | Background tasks ใน process เดียว | RQ / Celery |
| Instant Preview ไม่ผ่าน Dedup | Preview อาจแสดงแถวซ้ำ | Query DB หลัง processing |
| Orphaned Records | Server crash ทิ้ง status=uploaded ค้าง | Recovery Job |
| Log เฉพาะ stdout | ไม่มี Audit Trail | File Logger + Rotation |
| HTTPException ใน Background Thread | Exception ถูก ignore | เปลี่ยนเป็น RuntimeError |

---

## Future Improvements / Roadmap

### Priority P0 — Security (ต้องทำก่อน Public Deploy)

- [ ] JWT Authentication Middleware
- [ ] Per-IP Rate Limiting (SlowAPI)
- [ ] HTTPS Enforcement
- [ ] Filename Sanitization

### Priority P1 — Reliability

- [ ] Background Task Recovery Job (ล้าง Orphaned Records)
- [ ] Semaphore Initialization บน `@app.on_event("startup")`
- [ ] Structured Logging (JSON format) + File Rotation
- [ ] `/health` endpoint สำหรับ Load Balancer

### Priority P2 — Performance

- [ ] Excel Streaming ด้วย `openpyxl` row-by-row
- [ ] Polling เปลี่ยนจาก `setInterval` → recursive `setTimeout`
- [ ] Frontend Preview Button Query จาก DB แทน Cache ดิบ
- [ ] Connection Pool Monitoring

### Priority P3 — Scalability

- [ ] Celery + Redis สำหรับ Distributed Task Queue
- [ ] S3 หรือ Object Storage แทน Local Temp File
- [ ] Horizontal Scaling บน Kubernetes

---

## Production Readiness Notes

```
ระบบนี้เหมาะสำหรับ:
  ✓ Internal Tool สำหรับทีม Data Engineer
  ✓ MVP Demo / Proof of Concept
  ✓ Single-team Usage บน Private Network

ยังไม่เหมาะสำหรับ:
  ✗ Public Internet Deployment (ไม่มี Auth / Rate Limit)
  ✗ High-throughput Production (Single-node เท่านั้น)
  ✗ ไฟล์ Excel ขนาดใหญ่ > 50MB (OOM Risk)
```

### Production Readiness Score

| ด้าน | คะแนน | หมายเหตุ |
|---|---|---|
| Data Integrity | 85/100 | 2-Layer Hashing + UniqueConstraint |
| Upload Pipeline | 75/100 | แข็งแกร่ง มี Orphaned Record risk |
| Concurrency | 70/100 | Semaphore ดี แต่ Single-node |
| Security | 45/100 | ไม่มี Auth / Rate Limit |
| Observability | 30/100 | stdout เท่านั้น ไม่มี Metrics |
| **รวม** | **62/100** | MVP-ready |

---

## Engineering Notes — Design Tradeoffs

### ทำไมไม่ใช้ Celery ตั้งแต่แรก

ระบบใช้ FastAPI `BackgroundTasks` + `asyncio.Semaphore` แทน Celery เพราะในระยะ MVP การเพิ่ม Redis + Celery Worker เพิ่ม Operational Complexity สูงมาก สำหรับ Single-node ที่ไม่ต้องการ Distributed Queue การใช้ Semaphore ควบคุม 2 Concurrent Tasks เป็น Tradeoff ที่ยอมรับได้

### ทำไมเก็บ Data เป็น JSON Column

`RawData.json_data` เก็บข้อมูลแถวเป็น JSON แทนการ Map ลง Fixed Schema เพราะ CSV/Excel ต่างไฟล์มีคอลัมน์ต่างกัน การใช้ JSON ป้องกัน Schema Migration ที่ยุ่งยากในระยะนี้ แลกกับ Query Performance ที่ต่ำกว่า Normalized Table

### ทำไม Row Hash ใช้ `json.dumps(sort_keys=True)`

Dictionary ใน Python ไม่รับประกันลำดับ Key เสมอไปใน Context ที่ต่างกัน การใช้ `sort_keys=True` ทำให้ Hash เป็น Deterministic 100% ไม่ว่า pandas จะ Return key ลำดับใด ผลลัพธ์ Hash เดียวกันเสมอสำหรับข้อมูลเดียวกัน

### Preview Data Gap

Instant Preview ที่แสดงหลัง Upload ทันทีมาจากไฟล์ดิบ ไม่ใช่ข้อมูลที่ผ่าน Deduplication แล้ว นี่เป็น Intentional Design Tradeoff เพื่อให้ UX รู้สึก "เร็ว" แต่สร้าง Confusion เรื่อง Duplicate Rows เป็น Known Issue ที่จะแก้ใน Roadmap P2

---

## Screenshots

> *(Section นี้สงวนไว้สำหรับ Screenshots ของระบบจริง)*

```
[ Upload Interface Screenshot ]
[ Preview Table Screenshot ]
[ Batch Progress Screenshot ]
[ Duplicate Detection Screenshot ]
```

---

## License

MIT License

Copyright (c) 2026 AutoMerge Project

Permission is hereby granted, free of charge, to any person obtaining a copy of this software to use, copy, modify, merge, and distribute, subject to the following conditions: The above copyright notice and this permission notice shall be included in all copies.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND.

---

*README นี้สะท้อนสถานะระบบ ณ วันที่ 2026-05-12*  
*อัปเดตล่าสุดโดย: Engineering Team*
