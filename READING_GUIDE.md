# 🗺️ คู่มือการไล่อ่านโค้ดโปรเจค AutoMerge (Reading Guide)

หากต้องการทำความเข้าใจโปรเจคตั้งแต่เริ่มต้นจนจบ แนะนำให้ไล่อ่านไฟล์ตามลำดับดังต่อไปนี้ครับ เพื่อให้เห็นภาพรวมของ Data Flow จากการตั้งค่าระบบ ไปจนถึงการประมวลผล:

---

### 🟢 ลำดับที่ 1: ส่วนการตั้งค่าและฐานข้อมูล (Infrastructure Layer)
ควรเริ่มอ่านจากส่วนนี้เพื่อให้รู้ว่าระบบต่อกับอะไร และหน้าตาตารางเก็บข้อมูลเป็นอย่างไร

1. **`config/settings.py`**
   * **หน้าที่:** เป็นไฟล์ศูนย์กลางที่เก็บการตั้งค่าทั้งหมดของโปรเจค เช่น URL ของ Database (ตอนนี้คุณตั้งเป็น PostgreSQL แล้ว), Secret Key, และนามสกุลไฟล์ที่อนุญาต
   * **จุดสังเกต:** ดูคลาส `Settings` ซึ่งจัดการ Environment Variables

2. **`storage/database.py`**
   * **หน้าที่:** เป็นตัวกลางในการสร้าง Connection กับ Database ด้วย SQLAlchemy 
   * **จุดสังเกต:** ดูการสร้าง `engine`, `SessionLocal` และฟังก์ชัน `get_db()` ซึ่งเป็นตัวจ่าย Database Session ให้กับ API

3. **`storage/models.py`**
   * **หน้าที่:** กำหนดหน้าตาตารางใน Database (Schema)
   * **จุดสังเกต:** ดูโครงสร้างตาราง `RawFile` (เก็บประวัติการอัปโหลดไฟล์) และ `RawData` (เก็บข้อมูลแต่ละบรรทัดแบบ JSON) สังเกตคอลัมน์ `file_hash` และ `row_hash` ที่เราทำไว้กันข้อมูลซ้ำ

---

### 🟡 ลำดับที่ 2: ส่วนการรับและดึงข้อมูล (API Layer)
ส่วนนี้คือหัวใจหลักของแอปพลิเคชัน เป็นด่านหน้าในการรับคำสั่งจากผู้ใช้

4. **`api/main.py`** (ควรอ่านใช้เวลาเยอะที่สุด)
   * **หน้าที่:** ไฟล์หลักที่ใช้รัน FastAPI Server และรับ Request ทั้งหมด
   * **ลำดับการอ่านข้างในไฟล์:**
     1. ดูส่วนบน: การตั้งค่า `CORS` และ `init_db()` (เช็ค Schema ตอนเริ่ม Server)
     2. ดู API `def upload_file(...)`: ด่านแรกที่รับไฟล์, ป้องกันไฟล์ซ้ำ (File-level Deduplication), และสั่ง Background Task
     3. ดู API `def preview_data(...)`: (อยู่ด้านล่างสุด) เป็น API ง่ายๆ สำหรับดึงข้อมูล 10 บรรทัดแรกไปโชว์
   * **จุดสังเกต:** สังเกตว่า `upload_file` จะไม่ทำงานหนักด้วยตัวเอง แต่จะโยนให้ Worker ผ่าน `background_tasks.add_task`

---

### 🟠 ลำดับที่ 3: ส่วนประมวลผลหลังบ้าน (Processing Layer)
ส่วนนี้คือ Worker ที่ทำงานอยู่เบื้องหลังหลังจากที่ User อัปโหลดไฟล์เสร็จแล้ว

5. **กลับมาดูที่ `api/main.py` -> ฟังก์ชัน `process_uploaded_file`**
   * **หน้าที่:** ทำงานเบื้องหลัง (Background Worker)
   * **จุดสังเกต:** ดูการสร้าง `db = SessionLocal()` ของตัวเอง, การป้องกันข้อมูลซ้ำระดับบรรทัด (Row-level Deduplication ด้วย `seen_hashes`), และการทำ `bulk_save_objects` รวมถึง `db.rollback()`

6. **`ingestion/file_parser.py`**
   * **หน้าที่:** ตัวแกะไฟล์ Excel/CSV และทำความสะอาดข้อมูล
   * **จุดสังเกต:** 
     1. ดู `parse_file_to_json` ว่ามันใช้ Pandas อ่านไฟล์ยังไง และดึงมาเป็น JSON แบบไหน
     2. ดูฟังก์ชันย่อย `clean_and_validate_row` ว่ามันตัดช่องว่าง (Trim) และทิ้งบรรทัดว่างๆ ออกไปยังไง

---

### 🔵 ลำดับที่ 4: ส่วนแสดงผล (Frontend Layer)

7. **`frontend/index.html`**
   * **หน้าที่:** หน้าเว็บสำหรับทดสอบยิง API ไปหาหลังบ้าน
   * **จุดสังเกต:** ดูโค้ด JavaScript ฟังก์ชัน `uploadFile()` ว่ามันเอาไฟล์ส่งเป็น `FormData` ไปที่ Endpoint อะไร และดึง `fetchPreview()` มาแสดงผลเป็นตารางอย่างไร

---

**🎯 สรุป Flow การอ่านสั้นๆ:**
`settings.py` ➔ `database.py` ➔ `models.py` ➔ `main.py (upload_file)` ➔ `main.py (process_uploaded_file)` ➔ `file_parser.py` ➔ `index.html`
