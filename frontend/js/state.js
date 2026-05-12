/**
 * state.js — Encapsulated Application State
 * ============================================================
 * [B3] แทนที่ Global Variables ใน app.js:
 *   let selectedFiles = []        → AppState.addFiles / getFiles / ...
 *   let globalPreviews = {}       → AppState.setPreview / getPreview
 *
 * ใช้ IIFE (Immediately Invoked Function Expression) เพื่อ:
 * - ซ่อน _files และ _previews ไม่ให้เข้าถึงโดยตรงจากภายนอก
 * - ป้องกัน accidental mutation จากโค้ดส่วนอื่น
 * - เปิดเฉพาะ API ที่จำเป็นผ่าน return object
 *
 * ไม่มี Logic การ render หรือ API call ที่นี่ — State เท่านั้น
 * ============================================================
 */
const AppState = (() => {
    // Private state — ไม่สามารถเข้าถึงได้โดยตรงจากภายนอก
    let _files = [];
    let _previews = {};

    return {
        // --- File Queue ---

        /** ดึง Array ของไฟล์ทั้งหมด (read-only reference) */
        getFiles: () => _files,

        /** จำนวนไฟล์ที่อยู่ใน queue */
        getFileCount: () => _files.length,

        /** เพิ่มไฟล์ใหม่เข้า queue (concat ปลอดภัยกว่า push หลายตัว) */
        addFiles: (newFiles) => { _files = _files.concat(newFiles); },

        /** ลบไฟล์ตาม index (สำหรับปุ่ม Remove) */
        removeFile: (index) => { _files.splice(index, 1); },

        /** ล้าง queue ทั้งหมด (หลัง upload สำเร็จ) */
        clearFiles: () => { _files = []; },

        /** ดึง slice ของไฟล์สำหรับการทำ batch */
        sliceFiles: (start, end) => _files.slice(start, end),

        /** ตัด N ไฟล์แรกออก (หลัง upload บางส่วนเสร็จ) */
        trimFiles: (count) => { _files = _files.slice(count); },

        // --- Preview Cache ---

        /** บันทึก preview data ของไฟล์ที่ upload สำเร็จ */
        setPreview: (fileId, data) => { _previews[fileId] = data; },

        /** ดึง preview data ตาม fileId */
        getPreview: (fileId) => _previews[fileId],
    };
})();
