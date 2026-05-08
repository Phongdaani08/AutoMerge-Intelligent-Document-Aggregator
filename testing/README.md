# คู่มือการใช้งานเครื่องมือทดสอบระบบ (Safe Testing Tools)

เอกสารนี้อธิบายวิธีการใช้สคริปต์เพื่อจำลองข้อมูลสำหรับการทดสอบ (Load Test / Stress Test) ระบบ AutoMerge Ingestion Pipeline โดยไม่ต้องใช้ข้อมูลจริง และไม่กระทบต่อฐานข้อมูลระบบจริง 

## คำสั่งสร้างไฟล์จำลอง (`generate_test_files.py`)

---

### 1. ทดสอบปกติ
```bash
python testing/generate_test_files.py --files 5 --rows 1000
```
สร้าง 5 ไฟล์ CSV ไฟล์ละ 1,000 แถว ข้อมูลแต่ละไฟล์จะ **ต่างกัน** ทั้งหมด ใช้ทดสอบว่าระบบ Ingest ปกติผ่านหรือไม่ ทั้ง 5 ไฟล์ควร status: `completed`

---

### 2. ทดสอบ 409 Duplicate Detection
```bash
python testing/generate_test_files.py --files 3 --rows 500 --duplicate
```
สร้าง 3 ไฟล์ แต่ **ไฟล์ 2 และ 3 เป็น copy ของไฟล์ 1 ทุกไบต์** ทำให้ `file_hash` เหมือนกัน ผลที่คาดหวัง:
- ไฟล์ 1 → `completed`
- ไฟล์ 2, 3 → ระบบต้อง reject `409 Conflict`

---

### 3. ทดสอบ Load ไฟล์ใหญ่
```bash
python testing/generate_test_files.py --files 1 --rows 50000
```
สร้าง 1 ไฟล์ที่มี 50,000 แถว ขนาดใกล้ limit 10MB ใช้ทดสอบว่าระบบรับไฟล์ใหญ่ได้ไหม และ Background Worker ไม่ OOM ระหว่าง Chunk Insert

---

### 4. กำหนด Output Directory เอง
```bash
python testing/generate_test_files.py --files 5 --dir test_batch_jan
```
สร้าง 5 ไฟล์เหมือนคำสั่งแรก แต่เซฟลงโฟลเดอร์ `testing/test_batch_jan/` แทน `testing/generated/` ใช้เมื่ออยากแยก batch การทดสอบไม่ให้ปนกัน

---

## คำสั่งยิงทดสอบ API คู่ขนาน (`stress_upload.py`)

เมื่อเตรียมไฟล์ในโฟลเดอร์เรียบร้อยแล้ว ให้รันคำสั่งนี้เพื่อยิงไฟล์ทั้งหมดพร้อมกัน:

```bash
# ทดสอบระดับทั่วไป (แนะนำ)
python testing/stress_upload.py --workers 10

# หรือ ระบุไปตรงๆ
C:\Users\admin\AppData\Local\Programs\Python\Python310\python.exe testing/stress_upload.py --workers 10

# ทดสอบระดับพุ่งชน DB Pool Limit
python testing/stress_upload.py --workers 30
```

> [!WARNING]
> ไม่แนะนำให้ตั้งค่า `--workers` เกินขีดจำกัดของ DB Pool (`max_overflow=30`) เพราะจะเกิด TimeoutError ซึ่งเป็นกลไกการตัดโหลดปกติของระบบ
