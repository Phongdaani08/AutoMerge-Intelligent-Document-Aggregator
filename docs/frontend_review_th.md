# 🔍 AutoMerge — Professional Frontend Architecture Review
> ตรวจสอบ ณ วันที่: 2026-05-12 | Reviewer: Senior Frontend Architect

---

## Overall Assessment

AutoMerge เป็นโปรเจกขนาดเล็ก (Vanilla HTML/CSS/JS + FastAPI Backend) ที่มี **Backend ที่แข็งแกร่งกว่า Frontend มาก**
ในระดับ Backend มีการจัดการ Chunked Parsing, Semaphore Concurrency, Row-Level Dedup และ Rollback Safety ได้อย่างดี
แต่ฝั่ง **Frontend นั้นยังอยู่ในระดับ MVP Prototype** ที่ไม่มีการแยก Concerns, ไม่มี Design System, ไม่มี Error Boundary
และยังมี Security Risk สำคัญที่ต้องแก้ก่อน Deploy จริง

---

## Critical Problems

### 🔴 P0 — ปัญหาระดับ Critical (ต้องแก้ก่อน Production)

| # | ปัญหา | ไฟล์ | ความเสี่ยง |
|---|-------|------|-----------|
| 1 | **XSS Risk**: ใช้ `innerHTML` ฝังข้อมูลจาก API โดยตรง (`file.filename`, `file.message`) | `app.js:82,86` | HIGH — ผู้ไม่หวังดีอัปโหลดชื่อไฟล์ที่มี `<script>` tag ได้ |
| 2 | **Hardcoded API URL**: `http://localhost:8000` ฝังตรงใน JS | `app.js:136,238` | HIGH — ไม่สามารถ Deploy ไป Environment อื่นได้โดยไม่แก้โค้ด |
| 3 | **CORS `allow_origins=["*"]`**: เปิดรับทุก Origin โดยไม่จำกัด | `api/main.py:40` | HIGH — ยอมรับ Cross-Origin Request จาก Domain ใดก็ได้ |
| 4 | **Polling ไม่มี Timeout**: `setInterval` ใน `startPolling()` จะวิ่งตลอดไปถ้า API ไม่ตอบ | `app.js:236` | MEDIUM — Memory Leak และ API Request ล้นในระยะยาว |
| 5 | **`.env` มี Credential จริง** commit อยู่ใน Repo structure | `.env` | HIGH — `SECRET_KEY=supersecretkey-change-in-production` ยังไม่ถูกเปลี่ยน |

---

## Folder Structure Review

### โครงสร้างปัจจุบัน

```
AutoMerge/
├── frontend/
│   ├── index.html        ← HTML, Structure, Layout ทุกอย่างรวมอยู่ที่นี่
│   ├── style.css         ← CSS ทุกอย่างในไฟล์เดียว ไม่มี Design Token
│   └── app.js            ← State + API + DOM Manipulation + Business Logic ปนกัน
├── api/
│   └── main.py           ← Routing + Business Logic + DB Access + Background Worker ปนกัน
├── config/settings.py
├── storage/
│   ├── database.py
│   └── models.py
├── ingestion/file_parser.py
├── mapping/              ← ว่างเปล่า (เพียง __init__.py)
├── processing/           ← ว่างเปล่า (เพียง __init__.py)
├── testing/              ← ไม่มี Test Framework จริง (เป็น Script เปล่า)
└── docs/
```

### ปัญหาโครงสร้าง

1. **`mapping/` และ `processing/`** เป็นโฟลเดอร์ว่าง — ทำให้เกิด "ghost architecture" ที่ไม่มีเนื้อหา สับสนทีม
2. **`frontend/`** มีไฟล์เพียง 3 ไฟล์ ทำงานทุกอย่างปนกันหมด — ไม่ scale
3. **`api/main.py`** ทำหน้าที่เกิน 4 บทบาทในไฟล์เดียว (Router, Service, Repository, Worker Orchestrator)
4. **`testing/`** ไม่มี `pytest`, `unittest` หรือ Framework จริง — เป็นแค่ Script สำหรับ Manual Run

---

## Frontend Architecture Review

### State Management

```javascript
// app.js:2-3 — Global Mutable State
let selectedFiles = [];
let globalPreviews = {};
```

**ปัญหา:**
- State เป็น Global Mutable Variable ไม่มี encapsulation
- `globalPreviews` เก็บข้อมูล Preview ทั้งหมดใน Memory ตลอดอายุ Session — ถ้า Upload 100 ไฟล์, Object นี้จะพองขึ้นเรื่อยๆ ไม่มีการ clear
- ไม่มี State Machine — ไม่รู้ว่า App อยู่ใน State ไหน (idle / uploading / error)

**แนะนำ:** ห่อ State ด้วย Module Pattern หรือ Simple Store

```javascript
// แทนที่ Global Variables ด้วย Encapsulated Store
const AppState = (() => {
    let _files = [];
    let _previews = new Map(); // ใช้ Map แทน Object — จัดการ Memory ได้ดีกว่า
    let _uploadPhase = 'idle'; // 'idle' | 'uploading' | 'done' | 'error'

    return {
        getFiles: () => [..._files],
        addFiles: (files) => { _files = _files.concat(files); },
        removeFile: (idx) => { _files.splice(idx, 1); },
        clearFiles: () => { _files = []; },
        setPreview: (id, data) => { _previews.set(id, data); },
        getPreview: (id) => _previews.get(id),
        getPhase: () => _uploadPhase,
        setPhase: (phase) => { _uploadPhase = phase; },
    };
})();
```

---

### Component Design

**ปัญหาหลัก: God Function**

`uploadFile()` (app.js:154–230) ทำงานหลายอย่างเกินไปในฟังก์ชันเดียว:
- ✗ Validation ว่ามีไฟล์ไหม
- ✗ คำนวณ Batch
- ✗ Retry Logic (3 ครั้ง)
- ✗ Update UI Status
- ✗ เรียก API
- ✗ จัดการ State หลัง Upload สำเร็จ/ล้มเหลว

**Single Responsibility Principle ถูกละเมิด** — ฟังก์ชันเดียวควรทำงานเดียว

**แนะนำ: แยกเป็น Layer ที่ชัดเจน**

```
app.js (Orchestrator เท่านั้น)
    ↓ เรียกใช้
uploadService.js   (API calls, retry logic)
    ↓ เรียกใช้
uiRenderer.js      (DOM manipulation เท่านั้น)
    ↓ อ่านจาก
appState.js        (State เท่านั้น)
```

---

### XSS Vulnerability — วิเคราะห์เชิงลึก

```javascript
// app.js:82 — DANGEROUS
li.innerHTML = `<span><strong>${file.filename}</strong>
    <span class="file-status status-orange">Duplicate: ${file.message}</span></span>`;

// app.js:86 — DANGEROUS
li.innerHTML = `<span><strong>${file.filename}</strong>
    <span class="file-status status-red">Failed: ${file.message}</span></span>`;
```

ข้อมูล `file.filename` และ `file.message` มาจาก API Response — ถ้า Backend ถูก Compromise หรือผู้ใช้ส่งชื่อไฟล์ว่า `<img src=x onerror=alert(1)>.csv` จะ Execute ได้ทันที

**แก้ไขทันที:**
```javascript
// สร้าง Helper ป้องกัน XSS
function escapeHTML(str) {
    const div = document.createElement('div');
    div.appendChild(document.createTextNode(String(str)));
    return div.innerHTML;
}

// ใช้แทน innerHTML ที่ฝัง User Data
const nameEl = document.createElement('strong');
nameEl.textContent = file.filename; // textContent = SAFE
```

---

### Table Rendering — XSS ตัวที่สอง

```javascript
// app.js:110 — DANGEROUS (Data จาก Database ฝังใน HTML โดยตรง)
keys.forEach(k => tableHTML += `<th>${k}</th>`);
keys.forEach(k => tableHTML += `<td>${row[k] !== null ? row[k] : ''}</td>`);
```

Column Headers และ Cell Values มาจาก User-Uploaded Files — ต้องผ่าน `escapeHTML()` ทุกครั้ง

---

## UI/UX Review

### ปัญหา UI

| ปัญหา | ผลกระทบ |
|-------|---------|
| ไม่มี Loading State ระหว่างอัปโหลด (ปุ่มไม่ถูก Disable) | ผู้ใช้คลิก Upload ซ้ำหลายครั้ง ส่งไฟล์ซ้ำได้ |
| `<pre>` แสดง Raw JSON ควบคู่กับ Table | ซ้ำซ้อน สับสน — เลือกอย่างใดอย่างหนึ่ง |
| Polling ทุก 2 วินาที ไม่มี Visual Indicator (Spinner) | ผู้ใช้ไม่รู้ว่าระบบกำลังทำอะไรอยู่ |
| CSS ใช้สี Raw Keyword (`color: red`, `color: blue`) | ไม่มี Design Consistency |
| ไม่มี Responsive Design สำหรับมือถือ | `max-width: 800px` ไม่มี Media Query |
| ไม่มี Empty State | หน้าว่างเมื่อไม่มีไฟล์ ดูไม่เป็นมืออาชีพ |

### CSS Design System

```css
/* ปัจจุบัน — ไม่มี Token */
button { background-color: #007bff; }
.status-red { color: red; }

/* ควรเป็น — มี CSS Custom Properties */
:root {
    --color-primary: #2563eb;
    --color-danger: #dc2626;
    --color-success: #16a34a;
    --color-warning: #d97706;
    --color-text-muted: #6b7280;
    --radius-sm: 4px;
    --radius-md: 8px;
    --spacing-sm: 8px;
    --spacing-md: 16px;
    --spacing-lg: 24px;
}
```

---

## Performance Review

### Polling Architecture

```javascript
// app.js:236 — ปัญหา: setInterval ไม่มี Max Retry
const interval = setInterval(async () => { ... }, 2000);
// ถ้า file_id นี้ไม่มีวันเป็น "completed" หรือ "failed"
// interval จะวิ่งตลอดไป = Memory Leak + API Spam
```

**แก้ไข: ใส่ Max Poll Count**
```javascript
async function startPolling(fileId, maxAttempts = 30) {
    let attempts = 0;
    const interval = setInterval(async () => {
        attempts++;
        if (attempts >= maxAttempts) {
            clearInterval(interval);
            // แสดง "Timeout" ให้ผู้ใช้
            return;
        }
        // ... polling logic
    }, 2000);
}
```

### Excel Loading — Backend Issue ที่กระทบ Frontend

```python
# file_parser.py:57 — โหลด Excel ทั้งไฟล์ขึ้น RAM
df = pd.read_excel(file_path)  # ถ้าไฟล์ใหญ่ = OOM ทันที
```

ถ้า Upload ไฟล์ Excel 500MB จะ crash เนื่องจาก `read_excel` ไม่มี `chunksize` นี่คือ Scalability Bottleneck ที่ Frontend ต้องรายงาน Error ให้ผู้ใช้ได้รับรู้

### Re-render ทุก Keystroke

```javascript
// renderQueue() เรียก list.innerHTML = '' แล้ว re-build ทั้งหมดทุกครั้ง
// ถ้า selectedFiles มี 1000 ไฟล์ = DOM Thrashing
```

---

## Security Review

| ปัญหา | ระดับ | สถานะ |
|-------|-------|-------|
| XSS via `innerHTML` + User Data | 🔴 Critical | ยังไม่แก้ |
| Hardcoded `http://localhost:8000` | 🔴 High | ยังไม่แก้ |
| `CORS allow_origins=["*"]` | 🔴 High | ยังไม่แก้ |
| `.env` มี `SECRET_KEY` ที่ยังเป็น Default | 🔴 High | ยังไม่แก้ |
| Polling ไม่มี Auth Header | 🟡 Medium | ยังไม่แก้ |
| ไม่มี `python-dotenv` `.env.example` | 🟡 Medium | ยังไม่แก้ |
| `HTTPException` raise ใน Background Thread | 🟡 Medium | มีผลน้อย แต่ผิด Pattern |
| `declarative_base()` deprecated ใน SQLAlchemy 2.x | 🟡 Medium | ควรแก้ |
| `requirements.txt` ไม่ Pin Version | 🟡 Medium | ยังไม่แก้ |

### `.env` — Critical

```
# .env (ที่มีอยู่จริงในโปรเจก)
SECRET_KEY=supersecretkey-change-in-production
```

ถ้า `.gitignore` ถูก override หรือ push โดยบังเอิญ Key นี้จะ Leaked ทันที
**ต้องสร้าง `.env.example` และใช้ Key Generator จริงๆ**

---

## Code Quality Review

### `api/main.py` — Monolithic Endpoint

ไฟล์เดียว 268 บรรทัด ทำงานถึง 5 บทบาท:

```
main.py
├── DB Schema Migration (init_db)
├── FastAPI App Factory
├── Upload HTTP Endpoint
├── Background Task Orchestration
├── Background Task Implementation (Sync + Async)
├── Preview Endpoint
└── Status Endpoint
```

**ควรแยกเป็น:**
```
api/
├── routes/
│   ├── upload.py        ← HTTP Endpoint เท่านั้น
│   └── files.py         ← Preview + Status Endpoints
├── services/
│   └── file_service.py  ← Business Logic
└── workers/
    └── ingestion_worker.py ← Background Processing
```

### `settings.py` — Anti-Pattern

```python
# settings.py:8 — ใช้ os.getenv ซ้อนกับ BaseSettings
PROJECT_NAME: str = os.getenv("PROJECT_NAME", "AutoMerge Document Aggregator")
```

`pydantic_settings.BaseSettings` อ่าน `.env` อัตโนมัติอยู่แล้ว ไม่ต้องเรียก `os.getenv` ซ้ำซ้อน และไม่ต้องเรียก `load_dotenv()` เองอีก

**ที่ถูกต้อง:**
```python
class Settings(BaseSettings):
    PROJECT_NAME: str = "AutoMerge Document Aggregator"
    DATABASE_URL: str  # ไม่ต้อง os.getenv — BaseSettings จัดการให้
    SECRET_KEY: str

    model_config = SettingsConfigDict(env_file=".env")  # Pydantic v2 style
```

### Naming Inconsistency

```python
# models.py
file_name = Column(String)   # snake_case

# api/main.py response  
{"filename": file.filename}  # ไม่มี underscore — inconsistent กับ model
```

---

## Suggested Improvements

### Priority 1 — Security (ทำก่อนเพื่อน)

- [ ] แทนที่ `innerHTML` ทุกจุดที่รับ User Data ด้วย `textContent` หรือ `escapeHTML()`
- [ ] ย้าย API URL ออกจาก Hardcode ไปไว้ใน `config.js` หรือ `window.__APP_CONFIG__`
- [ ] จำกัด CORS ใน `api/main.py` ให้เฉพาะ Origin ที่รู้จัก
- [ ] เปลี่ยน `SECRET_KEY` เป็น Random 32-byte Hex จริงๆ
- [ ] สร้าง `.env.example` ที่ไม่มี Credential จริง

### Priority 2 — Architecture

- [ ] แยก `api/main.py` ออกเป็น routes / services / workers
- [ ] สร้าง `frontend/js/` folder และแยก `api.js`, `state.js`, `renderer.js`, `app.js`
- [ ] ลบโฟลเดอร์ว่าง `mapping/` และ `processing/` หรือสร้างเนื้อหาให้ครบ

### Priority 3 — Frontend Quality

- [ ] เพิ่ม CSS Custom Properties เป็น Design Token
- [ ] Disable ปุ่ม Upload ระหว่างอัปโหลด
- [ ] ใส่ Max Attempt ใน `startPolling()`
- [ ] ลบ `<pre id="jsonPreview">` ออก (ซ้ำซ้อนกับ Table)
- [ ] เพิ่ม Responsive CSS

### Priority 4 — Stability & Maintainability

- [ ] Pin version ใน `requirements.txt` (เช่น `fastapi==0.115.0`)
- [ ] แก้ `settings.py` ให้ใช้ Pydantic v2 style ถูกต้อง
- [ ] เปลี่ยน `declarative_base()` เป็น `DeclarativeBase` (SQLAlchemy 2.x)
- [ ] เพิ่ม `pytest` tests อย่างน้อยสำหรับ `file_parser.py` และ `/api/v1/upload`

---

## Refactored Structure Example

```
AutoMerge/
├── .env                          ← local only, gitignored
├── .env.example                  ← [NEW] template ที่ commit ได้
├── requirements.txt              ← Pin versions ทุกตัว
│
├── frontend/
│   ├── index.html
│   ├── css/
│   │   ├── tokens.css            ← [NEW] Design Tokens (CSS Variables)
│   │   ├── components.css        ← [NEW] Component styles
│   │   └── layout.css            ← [NEW] Layout styles
│   └── js/
│       ├── config.js             ← [NEW] API_BASE_URL, constants
│       ├── state.js              ← [NEW] Encapsulated App State
│       ├── api.js                ← [NEW] fetch wrappers เท่านั้น
│       ├── renderer.js           ← [NEW] DOM Manipulation เท่านั้น
│       └── app.js                ← [REFACTOR] Orchestrator เท่านั้น
│
├── api/
│   ├── __init__.py
│   ├── app.py                    ← [NEW] FastAPI factory + middleware
│   ├── routes/
│   │   ├── upload.py             ← [NEW] POST /upload
│   │   └── files.py              ← [NEW] GET /status, /preview
│   ├── services/
│   │   └── file_service.py       ← [NEW] Business Logic
│   └── workers/
│       └── ingestion_worker.py   ← [NEW] Background Processing
│
├── config/
│   └── settings.py               ← [REFACTOR] Pydantic v2 style
├── storage/
│   ├── database.py
│   └── models.py                 ← [REFACTOR] SQLAlchemy 2.x style
├── ingestion/
│   └── file_parser.py
├── tests/                        ← [RENAME จาก testing/]
│   ├── conftest.py               ← [NEW] pytest fixtures
│   ├── test_file_parser.py       ← [NEW]
│   ├── test_upload_endpoint.py   ← [NEW]
│   └── tools/                    ← [MOVE] stress_upload, generate_test_files
└── docs/
```

---

## Final Verdict

> **⚠️ Good Foundation but Needs Refactoring**

### เหตุผล

| ด้าน | คะแนน | ความเห็น |
|------|--------|---------|
| Backend Architecture | 7/10 | Chunking, Dedup, Semaphore ดีมาก แต่ api/main.py ใหญ่เกิน |
| Frontend Architecture | 3/10 | Monolithic JS ไม่มี Separation of Concerns เลย |
| Security | 4/10 | XSS, Hardcoded URL, Wildcard CORS — ต้องแก้ทั้งหมดก่อน Deploy |
| Code Quality | 5/10 | Backend ดีกว่า Frontend มาก naming inconsistent |
| Testing | 2/10 | ไม่มี Automated Test จริง มีแค่ Manual Script |
| Production Readiness | 3/10 | ยังไม่พร้อม — Security Risk ยังเปิดอยู่ |

Backend ของโปรเจกนี้แสดงให้เห็นว่าผู้พัฒนาเข้าใจ System Design ในระดับดี
แต่ Frontend ยังอยู่ในระดับ Prototype และมี Security Issue ที่ **ต้องแก้ก่อนเปิดให้ผู้ใช้งานจริงทุกกรณี**
