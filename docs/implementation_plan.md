# AutoMerge — แผนการพัฒนาระบบ (Implementation Plan)
วันที่: 2026-05-12 | อ้างอิงจาก: System Audit Report

---

## TASK-001: แก้ไข HTTPException ใน Background Thread
**Priority:** P0 | **Complexity:** Small | **Role:** Backend Engineer

### 1. ปัญหา
`process_uploaded_file_sync()` ใน `api/main.py` บรรทัด 242 raise `HTTPException` ใน Background Thread ซึ่งไม่ใช่ HTTP context จึงถูก Uvicorn ดักจับโดยเงียบ Client ไม่ได้รับ error จริง

### 2. พฤติกรรมปัจจุบัน
```python
raise HTTPException(status_code=500, detail="ไม่สามารถประมวลผลไฟล์ได้...")
# Exception นี้หายไปเงียบๆ ไม่แจ้ง Client
```

### 3. ความเสี่ยง
- File status ค้างที่ "failed" โดยไม่มี error message ที่ชัดเจน
- Log ไม่บันทึก traceback ที่ถูกต้อง
- ไม่สามารถ debug ได้ในอนาคต

### 4. Scope
- `api/main.py` function `process_uploaded_file_sync()`

### 5. แนวทางแก้ไข
เปลี่ยนจาก `raise HTTPException(...)` เป็น `raise RuntimeError(...)` แล้วให้ caller จัดการ update status = "failed" พร้อม error_message ลง DB

### 6. Acceptance Criteria
- เมื่อ processing ล้มเหลว: `RawFile.status = "failed"` และมี error log ที่อ่านออก
- Frontend Polling รับ status="failed" และแสดงผลถูกต้อง
- ไม่มี `HTTPException` ใน non-HTTP context อีก

---

## TASK-002: แก้ไข Semaphore Initialization Race Condition
**Priority:** P0 | **Complexity:** Small | **Role:** Backend Engineer

### 1. ปัญหา
`get_ingestion_semaphore()` ใช้ Lazy Initialization บน Global Variable ถ้า 2 Requests มาพร้อมกันก่อน semaphore ถูกสร้าง อาจได้ Semaphore 2 ตัว — ทำให้ Concurrency limit ไม่ทำงาน

### 2. พฤติกรรมปัจจุบัน
```python
ingestion_semaphore = None
def get_ingestion_semaphore():
    global ingestion_semaphore
    if ingestion_semaphore is None:
        ingestion_semaphore = asyncio.Semaphore(2)  # Race condition!
    return ingestion_semaphore
```

### 3. แนวทางแก้ไข
ย้ายการสร้าง Semaphore ไปที่ `@app.on_event("startup")` เพื่อให้สร้างครั้งเดียวก่อนรับ Request

### 4. Acceptance Criteria
- Semaphore สร้างครั้งเดียวตอน startup
- ไม่มี Race Condition แม้ request แรกๆ มาพร้อมกัน
- Log แสดง "Semaphore initialized" ตอน startup

---

## TASK-003: Orphaned RawFile Recovery Job
**Priority:** P1 | **Complexity:** Medium | **Role:** Backend Engineer

### 1. ปัญหา
ถ้า Server crash หลัง `db.commit()` (สร้าง RawFile) แต่ก่อน Background Task ถูก Queue — จะมี RawFile ที่ `status="uploaded"` ค้างอยู่ตลอดไป ไม่มี data ใน raw_data

### 2. Scope
- เพิ่ม Scheduled Cleanup Task หรือ Startup Recovery
- `api/main.py` ส่วน startup
- `storage/models.py` เพิ่ม column `error_message`

### 3. แนวทางแก้ไข
เพิ่ม Startup Recovery: ตอน Server เริ่ม ให้ Query หา RawFile ที่ status="uploaded" และ upload_time เก่ากว่า 1 ชั่วโมง แล้ว update เป็น status="failed" พร้อม error_message="Orphaned: Server restart"

### 4. Acceptance Criteria
- ตอน Server restart: Orphaned records ถูก mark เป็น "failed" อัตโนมัติ
- ไม่มี Record ที่ค้าง status="uploaded" นานกว่า threshold ที่กำหนด
- Log บันทึก recovery ทุกครั้ง

---

## TASK-004: Row-Level Deduplication Bug Investigation
**Priority:** P1 | **Complexity:** Large | **Role:** Backend Engineer + QA

### 1. ปัญหา
Row-level hashing มีอยู่ในโค้ด (`seen_hashes`, `row_hash`, `UniqueConstraint`) แต่ Preview ที่แสดงผลยังแสดงแถวซ้ำ ต้องหาสาเหตุที่แท้จริง

### 2. Root Cause วิเคราะห์แล้ว
**สาเหตุหลัก:** Preview Button แสดงข้อมูลจาก Instant Preview Cache (ข้อมูลดิบจากไฟล์) ไม่ใช่จากข้อมูลที่ Deduplicate แล้วใน DB

```
Upload Response → preview_data (raw file, bรรทัด 123 main.py)
AppState.setPreview(file_id, preview_data)  ← เก็บข้อมูลดิบ
showPreview() → AppState.getPreview() → แสดงข้อมูลดิบ  ← ไม่มี dedup!
```

**สาเหตุรอง (ต้องตรวจสอบ):** อาจมีปัญหาใน Hash Normalization:
- Pandas `to_dict()` อาจ Return numpy types (`numpy.int64`, `numpy.float64`) แทน Python native types
- `json.dumps()` กับ numpy types อาจ Serialize ต่างกัน → Hash ไม่ตรงกัน
- NaN → None conversion อาจไม่ consistent ระหว่าง chunks

### 3. Scope การแก้ไข

**Fix 1 (UX — ด่วนที่สุด):** แก้ Frontend ให้ Preview Button Query จาก DB (`/api/v1/preview/{file_id}`) หลัง status=completed แทนที่จะใช้ Cache ดิบ

**Fix 2 (Data Integrity):** เพิ่ม explicit type normalization ก่อน hash:
```python
# ใน file_parser.py process_chunk()
# บังคับ Python native types หลัง to_dict()
def normalize_for_hash(record: dict) -> dict:
    result = {}
    for k, v in record.items():
        if hasattr(v, 'item'):  # numpy scalar
            v = v.item()        # convert to Python native
        result[k] = v
    return result
```

**Fix 3 (Verification):** เพิ่ม log เพื่อยืนยัน dedup count ต่อไฟล์:
```
logger.info(f"File {file_id}: {total} rows, {skipped} duplicates skipped, {inserted} inserted")
```

### 4. Acceptance Criteria
- อัปโหลดไฟล์ที่มี 100 แถว ซึ่ง 30 แถวซ้ำ → DB มี 70 แถว
- Preview Button หลัง status=completed แสดงข้อมูลจาก DB (70 แถว ไม่มีซ้ำ)
- Log แสดง dedup count ชัดเจน
- numpy types ถูก normalize ก่อน hash เสมอ
- `sort_keys=True` ยังคงอยู่ครบ

---

## TASK-005: Authentication System
**Priority:** P0 | **Complexity:** Large | **Role:** Backend Engineer

### 1. ปัญหา
ไม่มี Authentication ใดๆ — ใครก็ POST `/api/v1/upload` ได้โดยไม่จำกัด

### 2. Scope
- `api/main.py` เพิ่ม JWT Middleware
- `storage/models.py` เพิ่ม User model
- `config/settings.py` เพิ่ม JWT settings
- Frontend: เพิ่ม Login flow และ token management
- `.env` เพิ่ม `SECRET_KEY`, `ALGORITHM`

### 3. แนวทางแก้ไข
- ใช้ `python-jose` (มีใน requirements.txt แล้ว) สร้าง JWT
- เพิ่ม `/api/v1/auth/login` endpoint
- เพิ่ม `Depends(get_current_user)` ใน upload endpoint
- Frontend เก็บ token ใน `localStorage` และส่งใน Authorization header

### 4. Acceptance Criteria
- Request ที่ไม่มี token ได้รับ 401
- Token หมดอายุได้รับ 401
- Login ด้วย credentials ที่ถูกต้องได้รับ token
- Upload endpoint ยังทำงานได้ปกติเมื่อมี valid token

---

## TASK-006: Rate Limiting
**Priority:** P0 | **Complexity:** Small | **Role:** Backend Engineer / DevOps

### 1. ปัญหา
ไม่มี Rate Limiting — สามารถส่ง Request ได้ไม่จำกัด เสี่ยงต่อ DDoS และ Resource Exhaustion

### 2. Scope
- ติดตั้ง `slowapi` หรือตั้งค่า Nginx upstream limit
- `api/main.py` เพิ่ม Limiter middleware
- `requirements.txt` เพิ่ม `slowapi`

### 3. แนวทางแก้ไข
```
Upload endpoint: max 10 requests/minute per IP
Status endpoint: max 60 requests/minute per IP
```

### 4. Acceptance Criteria
- เมื่อ IP ส่ง request เกิน limit ได้รับ 429 Too Many Requests
- Response มี `Retry-After` header
- Legitimate users ไม่ได้รับผลกระทบ

---

## TASK-007: Structured Logging System
**Priority:** P1 | **Complexity:** Medium | **Role:** Backend Engineer

### 1. ปัญหา
`utils/logger.py` เขียน log เฉพาะไปที่ stdout ไม่มี persistent file, ไม่มี log rotation, ไม่มี structured format สำหรับ parsing

### 2. Scope
- `utils/logger.py` เพิ่ม FileHandler + RotatingFileHandler
- เพิ่ม JSON structured logging format
- เพิ่ม correlation_id ต่อ request
- `.env` เพิ่ม `LOG_LEVEL`, `LOG_FILE_PATH`

### 3. แนวทางแก้ไข
```python
# utils/logger.py
handler = RotatingFileHandler(
    'logs/automerge.log',
    maxBytes=10*1024*1024,  # 10MB
    backupCount=5
)
```

### 4. Acceptance Criteria
- Log บันทึกลงไฟล์ที่ rotate อัตโนมัติ
- Format เป็น JSON (timestamp, level, message, file_id, request_id)
- Error log แยกออกเป็น `errors.log`
- Log ไม่สูญหายเมื่อ Server restart

---

## TASK-008: Health Check Endpoint
**Priority:** P1 | **Complexity:** Small | **Role:** Backend Engineer

### 1. ปัญหา
ไม่มี `/health` endpoint — Load Balancer / Monitoring ไม่สามารถตรวจสอบสถานะ Server ได้

### 2. Scope
- `api/main.py` เพิ่ม GET `/health` endpoint

### 3. แนวทางแก้ไข
```python
@app.get("/health")
def health_check(db: Session = Depends(get_db)):
    # ตรวจ DB connection
    # ตรวจ Semaphore status
    # Return: {"status": "ok", "db": "connected", "version": "x.x"}
```

### 4. Acceptance Criteria
- GET `/health` ส่งคืน 200 เมื่อระบบปกติ
- GET `/health` ส่งคืน 503 เมื่อ DB ไม่ตอบสนอง
- Response มี version และ timestamp

---

## TASK-009: Polling Overlap Fix
**Priority:** P2 | **Complexity:** Small | **Role:** Frontend Engineer

### 1. ปัญหา
`startPolling()` ใช้ `setInterval` แต่ logic เป็น `async` — ถ้า network ช้า (fetch > 2 วินาที) interval ถัดไปเริ่มก่อน response ก่อนหน้ากลับมา ทำให้มี concurrent fetch ซ้อนกัน

### 2. Scope
- `frontend/app.js` function `startPolling()`

### 3. แนวทางแก้ไข
เปลี่ยนจาก `setInterval` เป็น recursive `setTimeout` ที่เริ่มนับหลัง fetch เสร็จ:
```javascript
async function poll() {
    const result = await fetch(...);
    if (result.status !== "completed") {
        setTimeout(poll, 2000); // นับใหม่หลัง response
    }
}
setTimeout(poll, 2000);
```

### 4. Acceptance Criteria
- ไม่มี concurrent fetch จาก Polling เดียวกัน
- Timeout 60 วินาที ยังทำงานปกติ
- ถ้า fetch ช้า ระยะเวลา polling ยืดออก ไม่ทับซ้อน

---

## TASK-010: Frontend Phase B4 — API Layer Extraction
**Priority:** P2 | **Complexity:** Medium | **Role:** Frontend Engineer

### 1. ปัญหา
`uploadBatch()` และ `startPolling()` ยังอยู่ใน `app.js` รวมกับ Orchestration Logic — ไม่มีการแยก API Layer

### 2. Scope
- `frontend/js/api.js` ย้าย `uploadBatch()` และ `startPolling()` มาไว้ที่นี่
- `frontend/app.js` เรียกผ่าน `API.uploadBatch()` และ `API.startPolling()`
- `frontend/index.html` ไม่ต้องเปลี่ยน (api.js โหลดอยู่แล้ว)

### 3. แนวทางแก้ไข
```javascript
// js/api.js
const API = (() => {
    async function uploadBatch(batchFiles) { ... }
    async function startPolling(fileId, maxAttempts) { ... }
    return { uploadBatch, startPolling };
})();
```

### 4. Acceptance Criteria
- Upload / Retry / Polling ทำงานเหมือนเดิมทุกอย่าง
- `app.js` ไม่มี `fetch()` call โดยตรงอีกต่อไป
- ทดสอบ Upload, Batch, Retry, Polling ผ่านทั้งหมด

---

## TASK-011: Frontend Phase B5 — Renderer Layer Extraction
**Priority:** P2 | **Complexity:** Medium | **Role:** Frontend Engineer

### 1. ปัญหา
`renderQueue()`, `renderUploadedFiles()`, `showPreview()` ยังอยู่ใน `app.js` — DOM Logic ปนกับ Business Logic

### 2. Scope
- `frontend/js/renderer.js` ย้าย 3 functions มาไว้ที่นี่
- `frontend/app.js` เรียกผ่าน `Renderer.renderQueue()` ฯลฯ

### 3. แนวทางแก้ไข
```javascript
// js/renderer.js
const Renderer = (() => {
    function renderQueue() { ... }
    function renderUploadedFiles(results) { ... }
    function showPreview(fileId, filename) { ... }
    return { renderQueue, renderUploadedFiles, showPreview };
})();
```

### 4. Acceptance Criteria
- UI แสดงผลเหมือนเดิมทุกอย่าง
- `app.js` เหลือเฉพาะ Event Listeners และ Orchestration
- XSS Prevention (`textContent`/`createElement`) ยังครบทุกจุด

---

## TASK-012: Frontend Phase B6 — Final Cleanup
**Priority:** P2 | **Complexity:** Small | **Role:** Frontend Engineer

### 1. ปัญหา
หลัง B4 และ B5 เสร็จ `app.js` ยังอาจมีโค้ดเหลือที่ควรย้ายหรือ clean up

### 2. Scope
- `frontend/app.js` ทำความสะอาดให้เหลือเฉพาะ Initialization + Event Binding
- ย้าย `batchSize = 5` และ `maxRetries = 3` ไป `config.js`
- ตรวจสอบ comment ที่ล้าสมัย

### 3. Acceptance Criteria
- `app.js` มีความยาวไม่เกิน 60 บรรทัด
- ไม่มี Magic Number ใน app.js
- ทุก constant อยู่ใน config.js

---

## TASK-013: Preview Data Fix — Query DB After Dedup
**Priority:** P2 | **Complexity:** Medium | **Role:** Fullstack Engineer

### 1. ปัญหา
Preview Button แสดงข้อมูลดิบจาก Upload Response Cache ซึ่งไม่ผ่าน Row-level Deduplication ทำให้ User เห็นแถวซ้ำ

### 2. Scope
- `frontend/app.js` แก้ `showPreview()` ให้ fetch จาก `GET /api/v1/preview/{file_id}` หลัง status=completed
- `AppState` เพิ่ม flag ว่า preview มาจาก raw หรือ DB
- `frontend/js/api.js` (Phase B4) เพิ่ม `fetchPreview(fileId)`

### 3. แนวทางแก้ไข
```javascript
async function showPreview(fileId, filename) {
    const cachedPreview = AppState.getPreview(fileId);
    if (cachedPreview && cachedPreview._source === 'db') {
        renderPreviewTable(cachedPreview.data);
    } else {
        // Fetch from DB (deduplicated data)
        const response = await fetch(`${API_BASE_URL}/api/v1/preview/${fileId}`);
        const data = await response.json();
        AppState.setPreview(fileId, { _source: 'db', data: data.preview });
        renderPreviewTable(data.preview);
    }
}
```

### 4. Acceptance Criteria
- Preview Button หลัง status=completed แสดงข้อมูลจาก DB
- ไฟล์ที่มีแถวซ้ำ: Preview แสดงเฉพาะแถวที่ unique
- ถ้า status ยัง processing: แสดง "กำลังประมวลผล..."

---

## TASK-014: Excel Memory Safety
**Priority:** P2 | **Complexity:** Large | **Role:** Backend Engineer

### 1. ปัญหา
`pd.read_excel()` โหลดทั้งไฟล์ลง RAM ก่อน — ไฟล์ Excel 100MB อาจใช้ RAM 500MB+ ส่งผลให้เกิด OOM

### 2. Scope
- `ingestion/file_parser.py` function `parse_file_in_chunks()`
- เพิ่ม file size check ก่อน read_excel
- พิจารณาใช้ `openpyxl` iterator mode สำหรับไฟล์ใหญ่

### 3. แนวทางแก้ไข
Tier-based approach:
- Excel < 20MB: ใช้ `pd.read_excel()` เดิม (เร็ว)
- Excel 20-50MB: warning log + ใช้ `openpyxl` worksheet iterator
- Excel > 50MB: reject พร้อม error "File too large for Excel format, please convert to CSV"

### 4. Acceptance Criteria
- Excel < 20MB: ทำงานเหมือนเดิม
- Excel > 50MB: reject ทันที ไม่โหลดลง RAM
- Log แสดง file size และ processing strategy ที่เลือก

---

## TASK-015: Database Foreign Key Constraint
**Priority:** P3 | **Complexity:** Small | **Role:** Backend Engineer

### 1. ปัญหา
`RawData.file_id` มี comment ว่า "Foreign key conceptually" แต่ไม่มี FK constraint จริงใน DB — Cascade delete ไม่ทำงาน

### 2. Scope
- `storage/models.py` เพิ่ม ForeignKey บน `RawData.file_id`
- เขียน DB migration script
- ทดสอบ cascade behavior

### 3. แนวทางแก้ไข
```python
file_id = Column(Integer, ForeignKey('raw_files.id', ondelete='CASCADE'), index=True)
```

### 4. Acceptance Criteria
- ลบ RawFile → RawData ที่เกี่ยวข้องถูกลบอัตโนมัติ
- Migration script ทำงานบน DB ที่มีข้อมูลอยู่แล้วได้
- Existing data ไม่เสียหาย

---

## TASK-016: Upload Validation Improvements
**Priority:** P1 | **Complexity:** Small | **Role:** Backend Engineer

### 1. ปัญหา
- `file.filename` ถูกบันทึกลง DB โดยไม่ Sanitize — Path Traversal risk
- ไม่มีการตรวจสอบ MIME type จริง (ตรวจแค่ extension)

### 2. Scope
- `api/main.py` เพิ่ม filename sanitization ก่อน `db_file = RawFile(...)`
- เพิ่ม MIME type check ด้วย `python-magic` หรือ content sniffing

### 3. แนวทางแก้ไข
```python
import re
safe_filename = re.sub(r'[^a-zA-Z0-9_.\-]', '_', file.filename)
```

### 4. Acceptance Criteria
- Filename ที่มี `../` หรือ `<script>` ถูก sanitize ก่อนบันทึก
- ไฟล์ที่ rename extension แต่ content ผิดประเภทถูก reject
- Original filename ยังแสดงให้ user เห็นได้ใน UI

---

## สรุป Priority Matrix

| Task | Priority | Complexity | Role |
|---|---|---|---|
| TASK-001: Fix HTTPException in Background | P0 | Small | Backend |
| TASK-002: Fix Semaphore Race Condition | P0 | Small | Backend |
| TASK-005: Authentication System | P0 | Large | Backend |
| TASK-006: Rate Limiting | P0 | Small | Backend/DevOps |
| TASK-003: Orphaned Record Recovery | P1 | Medium | Backend |
| TASK-004: Row Dedup Bug Fix | P1 | Large | Backend+QA |
| TASK-007: Structured Logging | P1 | Medium | Backend |
| TASK-008: Health Check Endpoint | P1 | Small | Backend |
| TASK-016: Upload Validation | P1 | Small | Backend |
| TASK-009: Polling Overlap Fix | P2 | Small | Frontend |
| TASK-010: Frontend B4 (API Layer) | P2 | Medium | Frontend |
| TASK-011: Frontend B5 (Renderer) | P2 | Medium | Frontend |
| TASK-012: Frontend B6 (Cleanup) | P2 | Small | Frontend |
| TASK-013: Preview DB Query Fix | P2 | Medium | Fullstack |
| TASK-014: Excel Memory Safety | P2 | Large | Backend |
| TASK-015: FK Constraint | P3 | Small | Backend |

---

## Sprint Recommendation

### Sprint 1 (1-2 สัปดาห์): Critical Bug Fixes
- TASK-001, TASK-002, TASK-004 (Dedup Bug)

### Sprint 2 (2 สัปดาห์): Security Foundation
- TASK-005 (Auth), TASK-006 (Rate Limit), TASK-016 (Validation)

### Sprint 3 (1-2 สัปดาห์): Reliability
- TASK-003 (Orphaned), TASK-007 (Logging), TASK-008 (Health)

### Sprint 4 (2 สัปดาห์): Frontend Refactor
- TASK-009, TASK-010, TASK-011, TASK-012, TASK-013

### Sprint 5 (1 สัปดาห์): Performance
- TASK-014 (Excel), TASK-015 (FK)

---
*สร้างโดย: System Audit Review | วันที่: 2026-05-12*
