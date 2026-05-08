# AutoMerge Project Skills & Architecture Rules (AI Operational Brain)

นี่คือ "สมองส่วนปฏิบัติการ" (Operational Brain) สำหรับโปรเจค AutoMerge Intelligent Document Aggregator ข้อมูลนี้ใช้เพื่อสอน AI Agents และนักพัฒนาถึงกฎเกณฑ์ สถาปัตยกรรม และข้อห้าม (Anti-patterns) เพื่อป้องกันการ Refactor ที่ทำลายเสถียรภาพของระบบ

---

## 1. Project Identity
- **ชื่อโปรเจค:** AutoMerge Intelligent Document Aggregator
- **ลักษณะ:** Production-grade ingestion pipeline สำหรับรวบรวมไฟล์ Excel/CSV ในรอบเดือนของทีมธุรกิจ
- **บทบาทหลัก:** รับไฟล์ (Ingest), ตรวจสอบ (Validate), ป้องกันข้อมูลซ้ำ (Dedup) และจัดเก็บเป็นข้อมูลดิบ (Raw JSON Storage) อย่างปลอดภัย

## 2. System Goals
- รวบรวมข้อมูลดิบที่มีความหลากหลายทางโครงสร้าง (Schema) ให้มาอยู่ในระบบเดียว
- ป้องกันความผิดพลาดจากการอัปโหลดซ้ำ (Idempotency)
- ไม่ทำการ Block ผู้ใช้ระหว่างประมวลผล (Fast API Response)
- เตรียมข้อมูลให้พร้อมสำหรับระบบ Reconciliation และ Aggregation ในอนาคต

## 2.1 Business Context
- **ผู้ใช้งาน:** ทีมปฏิบัติการ (Operational) และทีมบัญชี ไม่ใช่วิศวกรหรือโปรแกรมเมอร์
- **ลักษณะข้อมูล (Dirty Excel):** ข้อมูลมาจากผู้ใช้หลายแผนก มักจะมีความสกปรก ขาดความสม่ำเสมอ และมีการเปลี่ยนคอลัมน์ (Schema Drift) อยู่ตลอดเวลา
- **Workflow ในชีวิตจริง:** คาดหวังว่าผู้ใช้จะอัปโหลดไฟล์ซ้ำซ้อนในโลกความเป็นจริง (เช่น อัปโหลดเพื่อตรวจสอบ หรือส่งไฟล์ผิด) ระบบจึงออกแบบมาให้ทนทานและรับมือกับ Duplicate Uploads อย่างเป็นธรรมชาติ
- **อนาคต:** ระบบเตรียมพร้อมสำหรับการดึงข้อมูลมาชนกัน (Reconciliation) เพื่อเตรียมกระทบยอดบัญชี ซึ่งเป็นหัวใจหลักในลำดับถัดไป

## 2.2 System Philosophy
ระบบนี้ยึดหลัก "System Philosophy" ที่เน้นเสถียรภาพมากกว่าความสมบูรณ์แบบทางเทคนิค:
**✅ สิ่งที่ให้ความสำคัญสูงสุด (Prioritizes):**
- **Ingestion Reliability & Safe Ingestion:** การรับข้อมูลต้องเสถียรที่สุดและไม่บล็อกการทำงาน
- **Operational Resilience & Data Preservation:** ทนทานต่อผู้ใช้และรักษาข้อมูลต้นฉบับให้ใกล้เคียงเดิมที่สุด
- **Rollback Safety & Idempotent Processing:** ผิดพลาดต้องย้อนกลับได้เสมอ และรันซ้ำได้โดยไม่ทำข้อมูลซ้ำซ้อน

**❌ สิ่งที่ไม่ให้ความสำคัญ (Over):**
- **Premature Optimization:** การพยายามเพิ่มความเร็วที่เกินความจำเป็น
- **Aggressive Normalization:** การบังคับจัดระเบียบตารางและคอลัมน์ให้สมบูรณ์แบบ
- **Unnecessary Distributed Complexity / Over-engineered Architecture:** การเพิ่มระบบหรือสถาปัตยกรรมที่ซับซ้อนเกินกว่าสถานการณ์จริง

## 3. Current Architecture
- **API Layer:** FastAPI (รับ Request, ตรวจสอบ, คืนค่าทันที)
- **Database Layer:** PostgreSQL + SQLAlchemy ORM (ใช้ `JSON` column เก็บข้อมูล)
- **Processing Layer:** FastAPI `BackgroundTasks` + Pandas
- **Storage Strategy:** เก็บ State ของไฟล์ใน `raw_files` และเก็บเนื้อหาแต่ละแถวใน `raw_data`

## 3.1 Current Operational Reality
ระบบปัจจุบันอยู่ในระดับความสมบูรณ์ที่พอดีสำหรับความต้องการเริ่มต้น:
- **Scale:** ทำงานแบบ Single-node (เซิร์ฟเวอร์เดียว) และ In-process worker model
- **Traffic:** คาดหวังระดับ Low-to-medium concurrency
- **Infrastructure:** ไม่มี Distributed Task Queue (เช่น Celery/Redis) เข้ามาเกี่ยวข้อง
- **Design Choice:** การจำกัดขนาดไฟล์และใช้ BackgroundTasks เป็นไปเพื่อ **"ความเรียบง่ายทางปฏิบัติการ (Operational Simplicity)"** เพื่อลดภาระการดูแลรักษาระบบ (Maintenance Cost) สำหรับวิศวกรและทำให้ Deploy ได้ง่ายที่สุด

## 3.2 Why JSON Storage Exists
การใช้ `JSON` เก็บข้อมูลระดับแถวในตาราง `raw_data` **ไม่ใช่ Database Design ที่แย่** แต่เป็น **"กลยุทธ์ที่ตั้งใจออกแบบมาสำหรับ Ingestion Pipeline"**:
- **Schema Drift Tolerance:** ทนทานต่อการถูกเพิ่มหรือลดคอลัมน์ Excel ในเดือนถัดๆ ไปโดยไม่ต้องแก้ Database Schema (ALTER TABLE)
- **Preserving Original Structure:** รักษาสภาพข้อมูลดั้งเดิม (Raw Source Data) จากทีมปฏิบัติการไว้สำหรับการ Audit อย่างโปร่งใส
- **Avoiding Fragile Mapping:** หลีกเลี่ยงความเปราะบาง (Fragile) จากการจับคู่คอลัมน์ Excel เข้ากับตาราง Relational แบบตายตัว
- **Delayed Normalization Philosophy:** เน้นเก็บก่อน แปลงทีหลัง (ELT concept) 

## 4. Full Data Flow
1. **Upload:** ผู้ใช้อัปโหลดผ่าน `/api/v1/upload`
2. **Validate:** ตรวจสอบ Extension และ Max File Size
3. **Hash (File):** สร้าง SHA-256 `file_hash` จากไบต์ของไฟล์
4. **Reject Duplicate:** หากมีไฟล์ซ้ำ คืนค่า 409 ทันที
5. **Save Pending:** บันทึกตาราง `raw_files` (สถานะ `uploaded`)
6. **Background Process:** โยนงานเข้า `BackgroundTasks`
7. **Clean:** ใช้ Pandas แปลงข้อมูล ลบช่องว่าง (Trim) และข้ามแถวว่าง
8. **Dedup (Row):** วนลูปสร้าง `row_hash` และกรองข้อมูลซ้ำในระดับบรรทัดด้วย Python `set()`
9. **Bulk Insert:** ส่งข้อมูลใหม่เข้า `raw_data` ผ่าน `bulk_save_objects`
10. **Commit:** `db.commit()` หรือ `db.rollback()` หากเกิด Error

## 5. Core Invariants (DO NOT BREAK)
- ห้ามเปลี่ยนกระบวนการรับไฟล์ไปเป็น Synchronous เด็ดขาด API ต้องตอบกลับทันที
- ห้ามเปลี่ยน `json_data` เป็น Relational Fixed Schema
  เพราะ Excel schema เปลี่ยนตลอด และระบบนี้ออกแบบมาเพื่อ Schema Drift Tolerance
- ห้ามลบกระบวนการทำ `file_hash` และ `row_hash`
- ห้ามใช้ Row ID ในไฟล์ Excel มาเป็น Primary Key ให้อิงจาก Hash เสมอ

## 6. Deduplication Strategy
- **File-Level:** สร้างจาก `hashlib.sha256(content)` ก่อนบันทึกไฟล์ หากซ้ำจะถูกตีกลับ (Reject 409)
- **Row-Level:** สร้างจาก `hashlib.sha256(json.dumps(record, sort_keys=True))` หากมีบรรทัดซ้ำในไฟล์เดียวกัน หรือคนละไฟล์ จะถูกข้าม (Skip silently) ไม่เกิด Error

## 7. Transaction Safety Rules
- การกระทำระดับ Bulk ต้องอยู่ภายใต้ Transaction เดียว
- หากกระบวนการ Background Worker ล้มเหลว **ต้อง** มีการเรียก `db.rollback()` เสมอ
- สถานะของไฟล์ (`status`) ต้องถูกอัปเดตเป็น `failed` เสมอในบล็อก `except` พร้อมระบุสาเหตุใน Log

## 8. SQLAlchemy Session Rules
- **API Layer:** รับ Session ผ่าน Dependency Injection (`Depends(get_db)`)
- **Background Task:** **ห้าม** ใช้ Session ร่วมกับ API เด็ดขาด ต้องสร้างใหม่ด้วย `db = SessionLocal()` และปิดด้วย `db.close()` ในบล็อก `finally:` เสมอ

## 9. Background Worker Rules
- ขณะนี้ใช้ `BackgroundTasks` ของ FastAPI งานจะถูกทำใน Process เดียวกันกับ API
- Worker ต้อง Idempotent (รันกี่ครั้งข้อมูลก็ไม่เพิ่มขึ้นแบบผิดปกติ)

## 10. Large File Constraints
- ปัจจุบันมีการตั้งลิมิตไฟล์ไว้ที่ `MAX_UPLOAD_SIZE` (10MB)
- ห้าม Bypass ลิมิตนี้จนกว่าจะเปลี่ยนวิธีการจัดการไฟล์ (ดูข้อ 15 และ 16)

## 11. Memory Safety Rules
- การอ่านไฟล์เข้า Memory ควรอ่านเท่าที่จำเป็น
- หลีกเลี่ยงการ Copy ข้อมูลขนาดใหญ่หลายรอบใน Python (เช่น การเก็บ List ของ Dict จำนวนมหาศาล)
- หากมีข้อมูลหลักแสนแถว การทำ `bulk_save_objects` รวดเดียวจะเกิด OOM ต้องแบ่งทำทีละก้อน (Chunking)

## 12. Error Handling Philosophy
- ด่านหน้า (API) รับมือกับ User Error (400, 409)
- ด่านหลัง (Worker) รับมือกับ Data/System Error (500) โดยไม่ทำให้แอปพลิเคชันหลักพัง
- ต้องจับ Exception ใน Background เสมอ และห้ามปล่อยผ่านโดยไม่ Log `traceback`

## 13. Production Safety Constraints
- การ Check Duplicate File (File-Hash) แม้จะมี Query เช็คก่อน Insert แต่อาจเกิด Race Condition ได้ (อัปโหลดไฟล์เดิมพร้อมกันเป๊ะ) ซึ่งระบบมี `UniqueConstraint` ใน DB คอยดักไว้เป็นปราการด่านสุดท้าย
- ความแม่นยำของ Row Hash (Determinism):
  - **Float/Int:** JSON parser อาจทำให้ `10.0` และ `10` มองเป็นคนละ Hash ได้
  - **Null/NaN:** ต้องถูกจัดการแปลงเป็น `null` อย่างถูกต้องก่อน Hash (ปัจจุบัน Pandas `.to_json()` จัดการส่วนนี้ให้)
  - **Key Ordering:** ถูกบังคับเสถียรภาพด้วย `sort_keys=True` 

## 14. Debugging Workflow
- ตรวจสอบ `raw_files` ว่าสถานะเป็น `uploaded`, `completed` หรือ `failed`
- หาก `failed` ให้ดูที่ API Log (Console) เพื่อค้นหา Traceback
- ตรวจสอบตาราง `raw_data` โดยใช้ `file_id` เพื่อดูว่าข้อมูลถูกบันทึกสมบูรณ์หรือไม่ผ่าน DBeaver

## 15. Current Technical Debt
- **Memory Risk:** มีการดึงไฟล์เก็บเป็น `bytes` เต็มก้อนใน RAM และส่งให้ Background Task ทำให้ Pandas กิน RAM เบิ้ลสองรอบ เสี่ยงต่อการ OOM เมื่อไฟล์มีขนาดใหญ่ขึ้น
- **Task Loss Risk:** หาก FastAPI ดับระหว่างประมวลผล (Restart/Crash) งานใน Background จะหายไปถาวร
- **Concurrency/Race Condition:** ยังไม่ได้จัดการ Lock ระดับไฟล์ที่รัดกุม 100%

## 16. Future Roadmap
1. เปลี่ยนจากนำไฟล์ใส่ RAM เป็นการเซฟลง Disk (Temp Storage) แล้วส่งแค่ Path ให้ Worker
2. แบ่งการ Insert สู่ Database เป็น Chunk (เช่น รอบละ 5,000 แถว)
3. ย้ายระบบจาก `BackgroundTasks` ไปใช้ External Broker (Celery/Redis)
4. เพิ่มการแปลง Data Type ให้อยู่ในฟอร์แมตมาตรฐาน (String-based) ก่อนการทำ `row_hash` เพื่อลดปัญหา Float Precision

## 17. AI Safety & Future AI Constraints (Anti-Patterns)
ส่วนนี้ออกแบบมาเป็นกฎเหล็กควบคุม AI Agent ในอนาคตที่เข้ามาแก้ไขโค้ด เพื่อป้องกันการทำลายสถาปัตยกรรมดั้งเดิม:

**🤖 AI Safety Constraints (ข้อบังคับสำหรับอนาคต):**
- **MUST** รักษาสถาปัตยกรรมแบบ Ingestion-first (รับข้อมูลไว ดำเนินการอยู่เบื้องหลัง) เสมอ
- **MUST** เข้าใจขีดจำกัดของ Scale ปัจจุบันก่อนที่จะเสนอการใช้ Distributed Systems 
- **MUST** รักษาการตรวจสอบความปลอดภัยของ Transaction และ Rollback Guarantees ทุกครั้งที่ปรับปรุง Worker

**🚫 Anti-Patterns (Things AI MUST NEVER DO):**
- **NEVER** พยายาม Refactor ตาราง JSON Storage กลับไปเป็น Relational Normalization แบบก้าวร้าว
- **NEVER** นำเสนอและสมมติว่ามี Infrastructure ขั้นสูงอยู่แล้ว (เช่น Kubernetes, Microservices, Celery, Redis หรือ Kafka)
- **NEVER** เสนอให้เขียนไฟล์ลง Database แบบ Synchronous (รอจนเขียนเสร็จแล้วค่อยตอบ User)
- **NEVER** แลกเปลี่ยน ORM กับ Raw SQL เว้นแต่จะเป็นคิวรี่ Report ที่ซับซ้อนจัดจริงๆ
- **NEVER** นำกระบวนการตรวจสอบข้อมูลซ้ำด้วย Hash (Hash-based Deduplication) ออกจากระบบเด็ดขาด

## 18. Recommended Development Workflow
- ทำความเข้าใจปัญหา ➔ ดู Log ในระบบ ➔ อัปเดต `file_parser.py` หากข้อมูลสกปรก ➔ ทดสอบด้วยไฟล์เล็ก ➔ เช็คสถานะการ Rollback หากเกิด Error

## 19. Current Stack
- **Framework:** FastAPI (Python)
- **Database:** PostgreSQL
- **ORM:** SQLAlchemy
- **Data Toolkit:** Pandas
- **Task Queue:** FastAPI BackgroundTasks (In-Memory)

## 20. Scaling Strategy
- **Step 1:** บรรเทาปัญหา Memory โดยใช้ File-based processing และ Database Insert Chunking
- **Step 2:** เพิ่ม Worker แยกรันคนละ Process ผ่าน Celery + Redis
- **Step 3:** Scale Worker Nodes แนวนอน (Horizontal) และใช้ Cloud Storage รับไฟล์ขนาดใหญ่

## 21. AI Change Management Rules

- AI MUST prefer incremental changes over full rewrites.
- AI MUST preserve existing architecture unless explicitly instructed.
- AI MUST explain trade-offs before introducing new infrastructure.
- AI MUST avoid introducing unnecessary abstraction layers.
- AI MUST prioritize maintainability and operational simplicity.
- AI MUST assume beginner-friendly maintainability for future developers.
- AI MUST preserve backward compatibility whenever possible.

### Safe Refactoring Principle
Prefer:
- small isolated changes
- additive improvements
- low-risk modifications

Avoid:
- architecture rewrites
- framework migrations
- large coupled refactors
- premature scalability optimizations

## AI Operational Learning Rules

เมื่อ AI แก้ปัญหาใหม่สำเร็จ:
- ต้องบันทึก root cause
- ต้องบันทึก debugging path
- ต้องบันทึกสิ่งที่ “ไม่ควรทำ”
- ต้องบันทึก pattern ที่ reusable
- ต้องบันทึก production risk ที่ค้นพบใหม่

หาก workflow ใหม่มีคุณค่าระยะยาว:
- ให้สร้าง subsection ใหม่ใน skill.md
- หรือสร้าง reusable workflow template

## Operational Learnings

### Multi-File Upload Testing & Swagger UI Bug
Symptoms:
- Swagger UI (FastAPI `/docs`) renders `List[UploadFile]` as `array<string>`.
- User gets `422 Unprocessable Entity` when pasting text into string inputs.
- Python test script throws `UnicodeEncodeError` in Windows Terminal.
- Test script returns `409 Conflict` on the second run with identical files.

Root Cause:
- Swagger UI has limitations rendering multiple file pickers for certain OpenAPI specs, causing users to mistakenly send strings.
- Windows Terminal defaults to `cp1252` encoding, failing on Thai `print()` statements.
- `409 Conflict` is the correct, expected behavior dictated by the `file_hash` deduplication safety rule.

Correct Fix & Reusable Debugging Workflow:
- **Testing Multi-File:** Do NOT use Swagger UI if it shows `array<string>`. Use Postman, cURL, or a Python `requests` script that generates and sends actual file objects (`rb`).
- **Terminal Encoding:** Use English logs for testing scripts or explicitly handle UTF-8 when testing on Windows CMD.
- **Verifying 409 Conflict:** Treat `409` on repeated test runs as "Success" of the deduplication system. To test `200 OK`, modify the dummy file content to generate a new `file_hash`.

Production Risk Note (Anti-Pattern):
- 🚫 **Fake 422 Panic:** Developers debugging `422` errors from Swagger might wrongly assume the Backend is broken and attempt to rewrite the `UploadFile` endpoint logic, violating stable architecture.
- 🚫 **Fake 409 Panic:** Developers getting `409` might think the upload failed and attempt to remove Hash-based deduplication (`skill.md` Core Invariant).

### Excel Encoding Issue
Symptoms:
- Thai characters corrupted
- Pandas parse failed

Root Cause:
- Wrong encoding assumption

Correct Fix:
- Use utf-8-sig fallback strategy

Avoid:
- Blind encoding conversion

## Standard Debug Workflow

1. Check raw_files status
2. Check traceback logs
3. Verify file_hash behavior
4. Check row_hash determinism
5. Verify rollback executed
6. Validate raw_data insert count

## Reusable Engineering Tasks

### Adding New Upload Validation
Checklist:
- preserve async ingest
- avoid RAM duplication
- preserve idempotency
- update validation response
- test duplicate upload

## 0. AI Quick Reference

### If modifying ingestion flow:
Read:
- §4 Full Data Flow
- §5 Core Invariants
- §17 AI Safety Rules

### If debugging failed uploads:
Read:
- §12 Error Handling
- §14 Debugging Workflow
- §15 Technical Debt

### If optimizing performance:
Read:
- §10 Large File Constraints
- §11 Memory Safety
- §20 Scaling Strategy

# ✅ Correct Background Task Session Pattern
db = SessionLocal()

try:
    ...
    db.commit()

except Exception:
    db.rollback()

finally:
    db.close()

# ❌ WRONG
bg.add_task(worker, db)


## Architecture Snapshot

Client Upload
    ↓
FastAPI API Layer
    ↓
Validation + File Hash
    ↓
raw_files (uploaded)
    ↓
BackgroundTasks Worker
    ↓
Pandas Cleaning + Row Hash Dedup
    ↓
raw_data JSON Storage
    ↓
Commit / Rollback