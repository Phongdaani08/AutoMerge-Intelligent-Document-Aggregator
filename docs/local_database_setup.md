# Local PostgreSQL Setup and Onboarding Guide

เอกสารนี้อธิบายขั้นตอนการตั้งค่า local development environment สำหรับ AutoMerge Document Aggregator โดยเฉพาะสำหรับทีมพัฒนารายใหม่

> โปรเจกต์นี้ใช้:
> - FastAPI backend
> - PostgreSQL database
> - SQLAlchemy ORM
> - `.env` configuration
> - CSV/Excel ingestion pipeline
> - SHA-256 file hashing
> - Row-level hashing
> - Background ingestion processing

---

## 1. Project Setup Overview

AutoMerge เป็นระบบ ingestion-first สำหรับไฟล์ CSV/Excel ที่ทำงานร่วมกับ PostgreSQL โดยมี:

- `api/main.py` — FastAPI application และ upload endpoint
- `config/settings.py` — โหลด `.env` ด้วย `pydantic-settings`
- `storage/database.py` — สร้าง SQLAlchemy engine / session / Base
- `storage/models.py` — ORM models สำหรับ `RawFile` และ `RawData`
- `ingestion/file_parser.py` — อ่านไฟล์ CSV/Excel แบบ chunk
- `.env.example` — template สำหรับ local config
- `requirements.txt` — dependencies

ระบบยังไม่มี migration tool เช่น Alembic ดังนั้น local setup จะใช้การสร้างตารางจาก ORM ด้วย `Base.metadata.create_all()` ที่เรียกจาก `api/main.py`

---

## 2. Required Software

ติดตั้งก่อน:

- Python 3.10+ (แนะนำ 3.11)
- PostgreSQL 14+ (ห้ามใช้ SQLite)
- Git
- Browser modern (สำหรับ frontend)

---

## 3. PostgreSQL Installation Instructions

### บน Windows

1. ดาวน์โหลด PostgreSQL จาก:
   - https://www.postgresql.org/download/windows/

2. ติดตั้งและจดรหัสผ่าน `postgres` user ไว้
3. เลือก port ที่ใช้
   - default คือ `5432`
   - repository ใช้ default `.env.example` เป็น `5433`
4. ตรวจสอบว่า `psql` ใช้งานได้

```powershell
psql --version
```

### บน WSL / Linux

```bash
sudo apt update
sudo apt install postgresql postgresql-contrib
sudo systemctl start postgresql
```

---

## 4. Database Creation Instructions

### 4.1 สร้าง database ใหม่

รันคำสั่งดังนี้ใน terminal:

```powershell
psql -U postgres -p 5433
```

ถ้าใช้ port 5432 ให้แก้เป็น:

```powershell
psql -U postgres -p 5432
```

จากนั้นสร้าง database:

```sql
CREATE DATABASE automerge_raw;
\q
```

### 4.2 สร้าง user ใหม่ (optional)

ถ้าต้องการ user แยกจาก `postgres`:

```sql
CREATE USER automerge_user WITH PASSWORD 'yourpassword';
GRANT ALL PRIVILEGES ON DATABASE automerge_raw TO automerge_user;
\q
```

---

## 5. `.env` Setup Instructions

### 5.1 คัดลอก template

ใน root repository:

```powershell
copy .env.example .env
```

### 5.2 ปรับค่าภายใน `.env`

แก้ค่าตาม environment ของคุณ:

```text
DATABASE_URL=postgresql://postgres:YOUR_PASSWORD@localhost:5433/automerge_raw
SECRET_KEY=REPLACE_WITH_SECURE_RANDOM_64_HEX_STRING
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
MAX_UPLOAD_SIZE=10485760
UPLOAD_DIR=temp_uploads
ALLOWED_ORIGINS=http://localhost:5500,http://127.0.0.1:5500
```

### 5.3 สร้าง `SECRET_KEY` จริง

รัน:

```powershell
python -c "import secrets; print(secrets.token_hex(32))"
```

แล้ววางค่าที่ได้ลงใน `.env`

### 5.4 ตรวจสอบ `DATABASE_URL`

ค่าใน `.env` ต้องถูกต้องกับ PostgreSQL local:

- Username
- Password
- Host
- Port
- Database name

หากใช้ port `5432` ให้ตั้ง `DATABASE_URL` เป็น `postgresql://postgres:YOUR_PASSWORD@localhost:5432/automerge_raw`

---

## 6. Python Virtual Environment Setup

ใน root ของ repository:

```powershell
py -m venv .venv
```

หรือถ้า `python` อยู่ใน PATH:

```powershell
python -m venv .venv
```

Activate environment:

```powershell
.venv\Scripts\activate
```

ถ้าจะปิด:

```powershell
deactivate
```

---

## 7. Dependency Installation

หลัง activate venv:

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

ตรวจสอบ dependencies ว่ามี:

- fastapi
- uvicorn
- sqlalchemy
- pandas
- openpyxl
- python-multipart
- pydantic
- pydantic-settings
- psycopg2-binary
- python-jose[cryptography]

---

## 8. Database Table Initialization

ระบบสร้าง table อัตโนมัติจาก ORM model ใน `api/main.py` ผ่าน `init_db()`

### สิ่งที่เกิดขึ้นตอน backend เริ่ม

- `config/settings.py` โหลด `.env`
- `storage/database.py` สร้าง SQLAlchemy engine จาก `DATABASE_URL`
- `api/main.py` เรียก `init_db()`
- `Base.metadata.create_all(bind=engine)` สร้างตารางถ้ายังไม่มี

### ตารางที่สร้าง

- `raw_files`
- `raw_data`

### ข้อสำคัญ

ปัจจุบันไม่มี Alembic หรือ migration system ใน repository
- ถ้าต้องแก้ schema ต้องระวัง manual migration
- โครงสร้าง table ปัจจุบันขึ้นกับ `storage/models.py`

---

## 9. Backend Startup

ใน root repository และ activate venv:

```powershell
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

### ตรวจสอบ

เปิด browser ที่:

```text
http://localhost:8000/
```

ถ้าทำงานถูกต้องจะเห็น JSON response:

```json
{"message":"Welcome to AutoMerge API"}
```

---

## 10. Frontend Startup

### วิธีรัน frontend ด้วย HTTP server

ใน root repository:

```powershell
python -m http.server 5500 --directory frontend
```

แล้วเปิด browser ที่:

```text
http://localhost:5500
```

### สิ่งสำคัญ

- ต้องเปิดผ่าน HTTP server ไม่ใช่ double-click
- `ALLOWED_ORIGINS` ใน `.env` ต้องมี `http://localhost:5500`
- หากใช้พอร์ตอื่น ปรับ `.env` ให้ตรง

---

## 11. Git Branch Workflow

### 11.1 เริ่มจาก `main`

```powershell
git checkout main
git pull origin main
```

### 11.2 สร้าง feature branch

```powershell
git checkout -b feature/<short-description>
```

### 11.3 พัฒนาและทดสอบ

- อย่า commit `.env`
- ใช้ branch แยกสำหรับทุกฟีเจอร์
- ถ้าเปลี่ยน schema DB ให้ปรึกษาทีมก่อน

### 11.4 commit และ push

```powershell
git add .
git commit -m "Add <feature>"
git push origin feature/<short-description>
```

---

## 12. Common Errors & Fixes

### 12.1 `psql: could not connect to server`

- PostgreSQL service ไม่รัน
- port ผิด
- ตรวจสอบ `postgresql.conf` และ `pg_hba.conf`

### 12.2 `FATAL: password authentication failed`

- password ไม่ตรง
- แก้ `.env` ให้ตรงกับ user/password จริง

### 12.3 `sqlalchemy.exc.OperationalError`

- `DATABASE_URL` ผิด
- DB ไม่ได้สร้าง
- host/port/DB name ผิด

### 12.4 `ModuleNotFoundError`

- ยังไม่ได้ activate venv
- หรือ `pip install -r requirements.txt` ไม่สำเร็จ

### 12.5 Frontend CORS หรือโหลดหน้าไม่ได้

- ต้องเปิด `frontend` ผ่าน `python -m http.server`
- เช็ค `ALLOWED_ORIGINS` ใน `.env`
- เปิด browser ด้วย `http://localhost:5500`

### 12.6 Upload file เกิน limit

- default limit = 10MB
- ถ้าต้องการเพิ่มให้แก้ `.env`

```text
MAX_UPLOAD_SIZE=20971520
```

---

## 13. Recommended Team Workflow

### ก่อนเริ่มทำงานวันแรก

1. `git pull origin main`
2. สร้าง `.venv`
3. ติดตั้ง dependencies
4. สร้าง database `automerge_raw`
5. คัดลอก `.env.example` เป็น `.env`
6. ใส่ค่า `DATABASE_URL` และ `SECRET_KEY`

### เมื่อพร้อมทดสอบ

1. รัน backend
2. รัน frontend
3. อัปโหลด CSV/Excel ตัวอย่าง
4. ตรวจสอบ status และ preview

### ถ้าจะเพิ่ม feature DB

- ห้ามแก้ schema โดยไม่ปรึกษา
- ปัจจุบันไม่มี Alembic
- ต้องเพิ่ม migration notes ใน PR

### ข้อแนะนำสำคัญ

- ระบบนี้เป็น ingestion pipeline ไม่ใช่ CRUD app
- PostgreSQL ต้องทำงานจริงเสมอ
- อย่าเปลี่ยนเป็น SQLite
- `.env` ต้องเก็บ local เท่านั้น

---

## 14. Quick Commands Reference

```powershell
# Clone repo
git clone <repo-url>
cd "AutoMerge Intelligent Document Aggregator"

# Create venv
py -m venv .venv
.venv\Scripts\activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Copy env template
copy .env.example .env

# Start backend
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

# Start frontend
python -m http.server 5500 --directory frontend
```

---

## 15. Notes on Existing Repo Behavior

- `api/main.py` เรียก `init_db()` บน startup เพื่อสร้างตารางจาก `storage/models.py`
- `storage/database.py` จะสร้าง engine จาก `settings.DATABASE_URL`
- `storage/models.py` มี `RawFile` และ `RawData` พร้อม `UniqueConstraint` สำหรับ row hash
- ไม่มี Alembic ใน repository
- frontend use `config.js`, `state.js`, `api.js`, `renderer.js` แต่ logic ปัจจุบันยังอยู่ใน `app.js`

---

## 16. Where to Find Key Files

| ไฟล์ | ความหมาย |
|---|---|
| `api/main.py` | Backend app, upload API, background ingestion, DB init |
| `config/settings.py` | โหลด `.env` และ config application |
| `storage/database.py` | SQLAlchemy engine/session/Base |
| `storage/models.py` | ORM models สำหรับ `raw_files`, `raw_data` |
| `ingestion/file_parser.py` | CSV/Excel parsing + chunking logic |
| `.env.example` | template สำหรับ local config |
| `requirements.txt` | dependencies list |

---

## 17. Final Checklist for New Developer

- [ ] PostgreSQL ติดตั้งและรันได้
- [ ] Database `automerge_raw` สร้างแล้ว
- [ ] `.env` ถูกต้องและไม่ commit
- [ ] Virtual environment active
- [ ] Dependencies ติดตั้งครบ
- [ ] Backend รันได้ที่ `http://localhost:8000`
- [ ] Frontend รันได้ที่ `http://localhost:5500`
- [ ] Upload CSV/Excel แล้วเห็น status

---

เอกสารนี้ออกแบบให้ทีมใหม่สามารถตั้งค่าและรันระบบได้ตรงตาม architecture ที่มีอยู่ โดยไม่แก้โครงสร้างหลักหรือเปลี่ยนไปใช้ฐานข้อมูลอื่น
