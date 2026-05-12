/**
 * AutoMerge Frontend Configuration
 * ====================================================
 * [A2] แยก API Base URL ออกจาก app.js
 *
 * วิธีใช้งาน:
 * - Local Dev  → API_BASE_URL = http://localhost:8000
 * - Staging    → เปลี่ยน API_BASE_URL เป็น https://staging.yourdomain.com
 * - Production → เปลี่ยน API_BASE_URL เป็น https://api.yourdomain.com
 *
 * ไฟล์นี้ต้องถูกโหลดก่อน app.js ใน index.html เสมอ:
 *   <script src="js/config.js"></script>
 *   <script src="app.js"></script>
 */
window.APP_CONFIG = {
    API_BASE_URL: 'http://localhost:8000'
};
