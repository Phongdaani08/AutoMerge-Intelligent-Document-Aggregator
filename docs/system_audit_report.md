# AutoMerge — Complete System Audit Report
**Role:** Principal Software Architect + Senior Backend Engineer  
**Date:** 2026-05-12  
**Scope:** Full codebase review — Read-Only, No modifications

---

## 1. Executive Summary

AutoMerge เป็นระบบรับ-ประมวลผลไฟล์ CSV/Excel ที่มี **Foundation ที่แข็งแกร่งกว่า Prototype ทั่วไปมาก** ระบบมีการออกแบบ Safety Mechanism หลายชั้น ได้แก่ File-Level Hashing, Row-Level Hashing, Semaphore Concurrency Control, Chunk-based Ingestion, Rollback Safety และ Background Task Isolation

**คะแนนรวม Production Readiness: 62/100**

> ระบบพร้อมสำหรับ Internal Tool / MVP แต่ยังขาด Observability, Rate Limiting, Auth Layer และ Horizontal Scaling Strategy ก่อนจะรองรับ Traffic จริงในระดับ Production

---

## 2. Current Features Implemented

| Feature | Status | คุณภาพ |
|---|---|---|
| Multi-file Upload | ✅ Active | ดี |
| Batch Upload (Frontend) | ✅ Active | ดี |
| Retry Mechanism (Frontend) | ✅ Active | ดีมาก |
| File-Level SHA-256 Deduplication | ✅ Active | ดีมาก |
| Row-Level SHA-256 Deduplication | ✅ Active | ดีมาก |
| Semaphore Concurrency Control | ✅ Active | ดี |
| Background Task Processing | ✅ Active | ดี |
| Chunk-based Ingestion (CSV) | ✅ Active | ดีมาก |
| Excel Full-load + Manual Chunk | ✅ Active | พอใช้ |
| Instant Preview (10 rows) | ✅ Active | ดี |
| Polling Status System | ✅ Active | ดี |
| DB Rollback on Error | ✅ Active | ดีมาก |
| Temp File Cleanup | ✅ Active | ดีมาก |
| CORS Restriction | ✅ Active (Phase A) | ดี |
| XSS Prevention | ✅ Active (Phase A) | ดีมาก |
| Config Centralization | ✅ Active (Phase A) | ดี |
| CSS Token System | ✅ Active (Phase B) | ดี |
| State Encapsulation | ✅ Active (Phase B3) | ดี |
| Auth / JWT | ❌ Not Active | ⚠️ Risk |
| Rate Limiting | ❌ Missing | ⚠️ Risk |
| File Logging to Disk | ❌ Missing | ⚠️ Risk |
| Health Check Endpoint | ❌ Missing | ควรมี |

---

## 3. System Architecture Overview

```
Browser (Vanilla JS)
    │
    │  HTTP POST /api/v1/upload (multipart/form-data)
    ▼
FastAPI (api/main.py)
    │
    ├─ [Sync] Validate Extension
    ├─ [Sync] Stream to Temp File + Calculate SHA-256
    ├─ [Sync] Duplicate Check → DB Query (RawFile.file_hash)
    ├─ [Sync] Create RawFile record (status=uploaded)
    ├─ [Sync] Read Preview 10 rows → Response
    │
    └─ [Async] background_tasks.add_task(process_uploaded_file)
                    │
                    ├─ asyncio.Semaphore(2) ← ควบคุม Concurrency
                    └─ asyncio.to_thread() ← แยก Blocking IO ออกจาก Event Loop
                            │
                            └─ process_uploaded_file_sync()
                                    │
                                    ├─ parse_file_in_chunks() [ingestion/]
                                    │       ├─ CSV: pd.read_csv(chunksize=5000)
                                    │       └─ Excel: pd.read_excel() + manual slice
                                    │
                                    ├─ Row SHA-256 Hash + in-memory dedup (seen_hashes)
                                    ├─ db.bulk_save_objects() per chunk
                                    ├─ RawFile.status = "completed"
                                    └─ db.commit() / rollback()
```

---

## 4. Backend Review

### 4.1 Upload Pipeline — `api/main.py`

**จุดแข็ง:**
- ใช้ `tempfile.mkstemp()` — ปลอดภัยกว่า `open()` ตรงๆ เพราะ OS จัดการ fd atomically
- Stream อ่านทีละ 8192 bytes — ป้องกัน Memory spike จากไฟล์ใหญ่
- Hash คำนวณระหว่าง Stream — ไม่ต้องอ่านไฟล์ซ้ำ (ประหยัด IO)
- Per-file try/except — ไฟล์หนึ่งพังไม่กระทบไฟล์อื่น

**จุดเสี่ยง:**
```python
# บรรทัด 116: Commit ก่อน Background Task ถูก Queue
db.commit()         # ← RawFile บันทึกแล้ว
db.refresh(db_file) # ← ดึง ID กลับมา
# ...แล้วค่อย
background_tasks.add_task(process_uploaded_file, ...) # บรรทัด 153
```
> ⚠️ **Risk**: ถ้า Server crash ระหว่าง commit กับ add_task → มี RawFile ที่ status="uploaded" ค้างอยู่ตลอดไป ไม่มี mechanism ฟื้นฟู (Orphaned Record)

```python
# บรรทัด 242: HTTPException ใน Background Sync Thread
raise HTTPException(status_code=500, detail="...")
```
> ❌ **Bug**: `HTTPException` ใน Background Task ไม่ส่งผลถึง Client เลย เพราะ Request จบไปแล้ว Exception นี้จะถูก Ignore โดย Uvicorn อย่างเงียบๆ — ควรเป็น `raise RuntimeError(...)` แทน

### 4.2 Concurrency — Semaphore

```python
ingestion_semaphore = None  # Global variable

def get_ingestion_semaphore():
    global ingestion_semaphore
    if ingestion_semaphore is None:
        ingestion_semaphore = asyncio.Semaphore(2)
    return ingestion_semaphore
```

**จุดแข็ง:** ควบคุมให้ประมวลผลไม่เกิน 2 ไฟล์พร้อมกัน ป้องกัน RAM/CPU Spike

**จุดเสี่ยง:**
- Lazy initialization ใน multi-coroutine context มีโอกาส Race Condition ตอน startup (ถ้า 2 requests มาพร้อมกันก่อน semaphore ถูกสร้าง)
- `asyncio.to_thread()` รัน Blocking IO บน Thread Pool ของ Python — ถ้า upload พร้อมกันหลายไฟล์มาก ThreadPool อาจเต็ม (default 32 threads)

### 4.3 Database Layer

**จุดแข็ง:**
- `pool_pre_ping=True` — ป้องกัน "Connection already closed" Error
- `pool_recycle=1800` — ป้องกัน Stale Connection จาก PostgreSQL timeout
- `UniqueConstraint('file_id', 'row_hash')` — DB-level guarantee ไม่มี Row ซ้ำ
- `bulk_save_objects()` ต่อ chunk — ดีกว่า insert ทีละแถวมาก

**จุดเสี่ยง:**
- Background Task ใช้ `SessionLocal()` โดยตรง ไม่ผ่าน `get_db()` generator — ถ้า Exception เกิดก่อน `finally: db.close()` อาจ leak connection
- ไม่มี Foreign Key constraint จริงระหว่าง `RawData.file_id` → `RawFile.id` (เป็นแค่ comment "conceptually") — cascade delete ไม่ทำงาน
- `db.bulk_save_objects()` ไม่ flush ระหว่าง chunks — ถ้าไฟล์ใหญ่มาก session อาจถือ object จำนวนมากค้างในหน่วยความจำ

---

## 5. Frontend Review

### 5.1 สถานะหลัง Phase A + B3

| Module | สถานะ | หมายเหตุ |
|---|---|---|
| `config.js` | ✅ แยกครบ | API_BASE_URL centralized |
| `state.js` (AppState) | ✅ Encapsulated | IIFE pattern, private state |
| `app.js` | 🔄 Partially refactored | ยังรวม API + Render + Orchestration |
| `api.js` | ⏳ Placeholder | รอ B4 |
| `renderer.js` | ⏳ Placeholder | รอ B5 |

### 5.2 Upload Batching (app.js)

```javascript
const batchSize = 5;
const totalBatches = Math.ceil(AppState.getFileCount() / batchSize);
```
**ดี:** จำกัด 5 ไฟล์ต่อ request ป้องกัน multipart body ใหญ่เกิน  
**ปัญหา:** `batchSize = 5` เป็น Magic Number ที่ยังไม่ได้ย้ายไป `config.js`

### 5.3 Retry Mechanism

```javascript
while (attempts <= maxRetries && !batchSuccess) {
    // retry ทุก 5 วินาที เฉพาะ Network Error หรือ 5xx
}
```
**ดีมาก:** แยก Client Error (4xx) ออกจาก Server Error (5xx) — ไม่ retry 4xx โดยไม่จำเป็น  
**ปัญหา:** ไม่มี Exponential Backoff — retry ทุก 5 วินาที fixed อาจกดซ้ำบน Server ที่กำลัง recover

### 5.4 Polling System

```javascript
async function startPolling(fileId, maxAttempts = 30) {
    // ทุก 2 วินาที × 30 ครั้ง = 60 วินาที timeout
}
```
**ดี:** มี maxAttempts guard (Phase A5) — ป้องกัน Memory Leak  
**ปัญหา:** ใช้ `setInterval` แต่ logic เป็น `async` — ถ้า network ช้า, interval ถัดไปอาจ overlap กับรอบก่อน

---

## 6. Security Review

### 6.1 สิ่งที่แก้แล้ว (Phase A)

| ช่องโหว่ | สถานะ |
|---|---|
| `innerHTML` + User Data (XSS) | ✅ แก้แล้ว — textContent/createElement |
| Hardcoded `localhost:8000` | ✅ แก้แล้ว — config.js |
| CORS `allow_origins=["*"]` | ✅ แก้แล้ว — .env ALLOWED_ORIGINS |
| Polling ไม่มี timeout | ✅ แก้แล้ว — maxAttempts=30 |
| `.env` ไม่มี template | ✅ แก้แล้ว — .env.example |

### 6.2 ช่องโหว่ที่ยังเหลือ

| ช่องโหว่ | ระดับ | ผลกระทบ |
|---|---|---|
| ไม่มี Authentication ใดๆ | 🔴 Critical | ใครก็ upload ได้ไม่จำกัด |
| ไม่มี Rate Limiting | 🔴 Critical | DDoS ง่ายมาก |
| `SECRET_KEY` ใน `.env` ยังเป็น Default | 🟠 High | ถ้า leak จะ forge token ได้ |
| ไม่มี HTTPS enforcement | 🟠 High | Man-in-the-middle risk |
| `file.filename` ไม่ Sanitize ก่อนบันทึก DB | 🟡 Medium | Path traversal risk ถ้านำไปใช้เปิดไฟล์ |
| Log ไม่ Redact ข้อมูล sensitive | 🟡 Medium | PII อาจรั่วใน log |

---

## 7. Performance Review

### 7.1 CSV vs Excel

| | CSV | Excel |
|---|---|---|
| Ingestion | `pd.read_csv(chunksize=5000)` — True streaming | `pd.read_excel()` — Load ทั้งไฟล์ก่อน |
| Memory | O(chunk_size) | O(N) ทั้งไฟล์ |
| ความเสี่ยง | ต่ำ | สูง — Excel 100MB = RAM หลาย GB |

**คำแนะนำ:** Excel ต้องการ Workaround เช่น `openpyxl` read row-by-row หรือจำกัดขนาดไฟล์ Excel ให้น้อยกว่า CSV

### 7.2 `seen_hashes` in-memory Set

```python
seen_hashes = set()  # เก็บใน RAM ตลอด process
```
> ⚠️ ไฟล์ 1 ล้านแถว = 1 ล้าน SHA-256 strings ใน set = ~64MB RAM ต่อไฟล์  
> ถ้า semaphore ปล่อย 2 ไฟล์พร้อมกัน = ~128MB เฉพาะ seen_hashes

---

## 8. Big O Analysis

| Operation | Best Case | Worst Case | หมายเหตุ |
|---|---|---|---|
| File Upload (N files) | O(N) | O(N) | Sequential per-file loop |
| SHA-256 File Hash | O(F) | O(F) | F = file size in bytes |
| DB Duplicate Check | O(log N) | O(log N) | มี INDEX บน file_hash |
| CSV Chunk Ingestion | O(R/C) chunks | O(R/C) chunks | R=rows, C=chunk_size |
| Row Hash + Dedup | O(R) | O(R) | set lookup O(1) avg |
| Bulk Insert per chunk | O(C) | O(C) | C=chunk_size=5000 |
| Frontend Batch Loop | O(N/5) batches | O(N/5 × 3) | 3 = max retries |
| Frontend Polling | O(1) per tick | O(30) max | 30 = maxAttempts |
| DOM Render (N files) | O(N) | O(N) | createElement loop |
| Preview Table Render | O(R×K) | O(R×K) | R=rows, K=columns |

---

## 9. Production Readiness Score

| Category | Score | เหตุผล |
|---|---|---|
| Upload Pipeline | 75/100 | แข็งแกร่ง แต่มี Orphaned Record risk |
| Concurrency Control | 70/100 | Semaphore ดี แต่ lazy init risk |
| Data Integrity | 85/100 | 2-layer hashing + UniqueConstraint |
| Frontend Architecture | 65/100 | กำลัง refactor (B4-B6 ยังไม่เสร็จ) |
| Security | 45/100 | ไม่มี Auth, ไม่มี Rate Limit |
| Observability | 30/100 | Log เฉพาะ stdout, ไม่มี metric |
| Database Layer | 70/100 | Pool ดี แต่ขาด FK constraint จริง |
| Scalability | 40/100 | Single node, ไม่รองรับ horizontal scale |
| **รวม** | **62/100** | MVP-ready, Not Production-ready |

---

## 10. Scalability Analysis

| Load Level | สถานะระบบ | คาดการณ์ |
|---|---|---|
| 1-5 users, ไฟล์เล็ก | ✅ ปกติ | ทำงานได้ดี |
| 10 users concurrent | 🟡 ระวัง | Semaphore queue ยาว, User รอนาน |
| 50+ users concurrent | 🔴 Collapse Risk | ThreadPool เต็ม, Connection Pool หมด |
| ไฟล์ Excel > 50MB | 🔴 OOM Risk | pd.read_excel() โหลดทั้งไฟล์ |
| 1M rows per file | 🟡 ระวัง | seen_hashes set ใหญ่, RAM สูง |

**Scaling Bottlenecks (เรียงตาม Priority):**
1. Single-process Uvicorn — ไม่ scale horizontal ได้โดยธรรมชาติ
2. Synchronous `db.bulk_save_objects()` ใน Thread — ไม่ใช่ async
3. Excel in-memory load — ไม่ได้ stream
4. No message queue (Celery/RQ) — Background tasks ใช้ RAM ของ process หลัก

---

## 11. Critical Risks

### 🔴 Risk 1: Orphaned RawFile Records
**เกิดเมื่อ:** Server crash หลัง `db.commit()` แต่ก่อน `background_tasks.add_task()`  
**ผลลัพธ์:** มี Record ที่ `status="uploaded"` ค้างตลอดไป ไม่มี data ใน raw_data  
**แก้ได้ด้วย:** Recovery Job / Scheduled Cleanup Task

### 🔴 Risk 2: HTTPException ใน Background Thread ถูก Ignore
**เกิดเมื่อ:** `process_uploaded_file_sync()` raise `HTTPException`  
**ผลลัพธ์:** Exception หายไปเงียบๆ, Client เห็น status="failed" แต่ไม่รู้สาเหตุ  
**แก้ได้ด้วย:** เปลี่ยนเป็น `raise RuntimeError(...)`

### 🟠 Risk 3: Semaphore Lazy Init Race Condition
**เกิดเมื่อ:** 2 requests มาพร้อมกันตอน startup ก่อน semaphore ถูกสร้าง  
**ผลลัพธ์:** อาจสร้าง semaphore 2 ตัว — concurrency limit ไม่ทำงาน  
**แก้ได้ด้วย:** สร้าง semaphore ใน `@app.on_event("startup")`

### 🟠 Risk 4: No Authentication
**เกิดเมื่อ:** Deploy บน Public Server  
**ผลลัพธ์:** ใครก็ upload ข้อมูลได้ ระบบจะเต็มทันที  
**แก้ได้ด้วย:** JWT Middleware หรือ API Key

### 🟡 Risk 5: Polling setInterval + async Overlap
**เกิดเมื่อ:** Network ช้า, fetch ใช้เวลา > 2 วินาที  
**ผลลัพธ์:** interval ถัดไปเริ่มก่อน response ก่อนหน้ากลับมา  
**แก้ได้ด้วย:** เปลี่ยนจาก `setInterval` → recursive `setTimeout`

---

## 12. File Hashing / Deduplication Audit

### คำตอบตรงๆ: ระบบ Hashing ยังมีอยู่ครบ และยังเชื่อมต่ออยู่ 100%

### Trace การทำงานจริง

```
POST /api/v1/upload
    │
    ├─ [บรรทัด 81] sha256_hash = hashlib.sha256()
    ├─ [บรรทัด 91] sha256_hash.update(chunk)   ← Hash คำนวณขณะ Stream
    ├─ [บรรทัด 101] file_hash = sha256_hash.hexdigest()
    │
    ├─ [บรรทัด 104] db.query(RawFile).filter(RawFile.file_hash == file_hash).first()
    │       ├─ พบ → status="duplicate" → return ทันที ✅
    │       └─ ไม่พบ → ดำเนินการต่อ
    │
    └─ [บรรทัด 114] RawFile(file_hash=file_hash, ...)  ← บันทึก hash ลง DB

Background Thread:
    ├─ [บรรทัด 205] row_hash = hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest()
    ├─ [บรรทัด 208] if row_hash in seen_hashes: continue  ← In-memory dedup
    └─ RawData(row_hash=row_hash, ...)
```

### 2-Layer Deduplication Strategy

| Layer | Algorithm | Scope | Storage |
|---|---|---|---|
| **File-Level** | SHA-256 (content) | ทั้งไฟล์ | `RawFile.file_hash` (DB, UNIQUE) |
| **Row-Level** | SHA-256 (JSON sorted) | แต่ละแถว | `seen_hashes` (RAM) + `RawData.row_hash` (DB) |

### ทำไม Row Hash ใช้ `sort_keys=True`?

```python
json.dumps(record, sort_keys=True)
```
เพราะ Dictionary ใน Python ไม่มีลำดับที่แน่นอนเสมอไป — `sort_keys=True` ทำให้ `{"b":1,"a":2}` และ `{"a":2,"b":1}` ได้ Hash เดียวกัน → **Deterministic, ถูกต้องมาก**

### ข้อจำกัดของ Row Hashing

> ⚠️ `seen_hashes` เป็น in-memory set ภายใน process เดียว — ถ้า restart server, set ล้างหมด แต่ `UniqueConstraint` ใน DB ยังคุ้มกันได้อยู่ เพราะมีทั้ง 2 ชั้น

---

## 13. Recommended Next Priorities

| Priority | งาน | ผลกระทบ |
|---|---|---|
| P0 🔴 | เพิ่ม Authentication (JWT/API Key) | Security Critical |
| P0 🔴 | เพิ่ม Rate Limiting (SlowAPI) | DDoS Prevention |
| P1 🟠 | แก้ `HTTPException` ใน Background Thread | Bug Fix |
| P1 🟠 | Startup Semaphore Initialization | Race Condition Fix |
| P1 🟠 | Orphaned Record Recovery Job | Data Integrity |
| P2 🟡 | เปลี่ยน Polling เป็น recursive setTimeout | UX + Correctness |
| P2 🟡 | Excel Streaming (openpyxl row-by-row) | Memory Safety |
| P2 🟡 | Logging to File (rotating) + Structured Log | Observability |
| P3 | เพิ่ม `/health` endpoint | Deployment Readiness |
| P3 | Move `batchSize=5`, `maxRetries=3` → config.js | Maintainability |
| P4 | Foreign Key constraint จริง RawData → RawFile | DB Integrity |
| P4 | Complete B4-B5-B6 Frontend Refactor | Maintainability |

---

## 14. Final Verdict

**สำหรับ Internal Tool / MVP:** ✅ พร้อมใช้งาน

**สำหรับ Production Public Deployment:** ❌ ยังไม่พร้อม — ต้องแก้ P0 ก่อน

> ระบบนี้มี Engineering Quality สูงกว่า Prototype ทั่วไปมาก โดยเฉพาะในส่วน Data Integrity (2-Layer Hashing), Memory Safety (Streaming), และ Error Isolation (Per-file try/except + Rollback) ซึ่งเป็นสิ่งที่ Developer ส่วนใหญ่ในระดับ Junior-Mid มักมองข้าม จุดที่ต้องปรับก่อน Production คือ Security Layer (Auth + Rate Limit) และ Observability (Structured Logging + Metrics) เป็นหลักครับ
