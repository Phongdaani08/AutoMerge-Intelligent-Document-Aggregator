// ================= CONFIG =================
// อ่าน API_BASE_URL จาก config.js ที่โหลดก่อนหน้า
// ถ้าไม่มี config.js (เช่นเปิดไฟล์โดยตรง) ให้ fallback เป็น localhost
const API_BASE_URL = (window.APP_CONFIG && window.APP_CONFIG.API_BASE_URL)
    ? window.APP_CONFIG.API_BASE_URL
    : 'http://localhost:8000';

// ================= SECURITY HELPER =================
/**
 * [A1] XSS Prevention Helper
 * แปลง String ให้ปลอดภัยก่อนแสดงใน DOM
 * ใช้ทุกครั้งที่ข้อมูลมาจาก User Input หรือ API Response
 */
function escapeHTML(str) {
    if (str === null || str === undefined) return '';
    const div = document.createElement('div');
    div.appendChild(document.createTextNode(String(str)));
    return div.innerHTML;
}

// ================= STATE =================
// [B3] ย้าย selectedFiles และ globalPreviews ไปเป็น AppState (state.js)
// AppState โหลดก่อน app.js ใน index.html — ใช้งานได้ทันที

// ================= INITIALIZATION =================
document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('fileInput').addEventListener('change', handleFileSelect);
    document.getElementById('uploadBtn').addEventListener('click', uploadFile);
});

// ================= DOM/UI RENDERING =================

function handleFileSelect(event) {
    const newFiles = Array.from(event.target.files);
    AppState.addFiles(newFiles); // [B3] แทน: selectedFiles = selectedFiles.concat(newFiles)
    event.target.value = '';
    renderQueue();
}

function renderQueue() {
    const section = document.getElementById('queueSection');
    const list = document.getElementById('fileQueueList');

    if (AppState.getFileCount() === 0) { // [B3] แทน: selectedFiles.length === 0
        section.classList.add('hidden');
        return;
    }

    section.classList.remove('hidden');
    list.innerHTML = '';

    AppState.getFiles().forEach((file, index) => { // [B3] แทน: selectedFiles.forEach
        const li = document.createElement('li');
        const sizeKB = (file.size / 1024).toFixed(2);

        // [A1-FIX] แทน innerHTML ด้วย createElement + textContent
        // ป้องกันกรณีชื่อไฟล์มี <script> หรือ HTML Tag แปลกๆ
        const textSpan = document.createElement('span');
        const strong = document.createElement('strong');
        strong.textContent = file.name; // SAFE: textContent ไม่ parse HTML
        const sizeSpan = document.createElement('span');
        sizeSpan.className = 'file-size';
        sizeSpan.textContent = `(${sizeKB} KB)`;
        textSpan.appendChild(strong);
        textSpan.appendChild(document.createTextNode(' '));
        textSpan.appendChild(sizeSpan);

        const removeBtn = document.createElement('button');
        removeBtn.type = 'button';
        removeBtn.className = 'btn-danger';
        removeBtn.textContent = 'Remove';
        removeBtn.addEventListener('click', () => removeFile(index));

        li.appendChild(textSpan);
        li.appendChild(removeBtn);
        list.appendChild(li);
    });
}

function renderUploadedFiles(results) {
    const section = document.getElementById('uploadedSection');
    const list = document.getElementById('uploadedFileList');

    section.classList.remove('hidden');
    list.innerHTML = '';

    results.forEach(file => {
        const li = document.createElement('li');

        if (file.status === "success") {
            if (file.preview) {
                AppState.setPreview(file.file_id, file.preview); // [B3] แทน: globalPreviews[file.file_id] = file.preview
            }

            // [A1-FIX] แทน innerHTML ด้วย createElement ทั้งหมด
            // file.filename และ file.file_id มาจาก API — ต้องป้องกัน XSS
            const textSpan = document.createElement('span');

            const strong = document.createElement('strong');
            strong.textContent = file.filename; // SAFE

            const idText = document.createTextNode(` (ID: ${escapeHTML(String(file.file_id))})\u00a0`);

            const statusSpan = document.createElement('span');
            statusSpan.id = `statusSpan_${file.file_id}`;
            statusSpan.className = 'file-status status-blue';
            statusSpan.textContent = 'Saving to DB...'; // SAFE: static text

            textSpan.appendChild(strong);
            textSpan.appendChild(idText);
            textSpan.appendChild(statusSpan);

            const previewBtn = document.createElement('button');
            previewBtn.type = 'button';
            previewBtn.className = 'btn-info';
            previewBtn.textContent = 'Preview';
            previewBtn.addEventListener('click', () => showPreview(file.file_id, file.filename));

            li.appendChild(textSpan);
            li.appendChild(previewBtn);
            list.appendChild(li);

            startPolling(file.file_id);

        } else if (file.status === "duplicate") {
            // [A1-FIX] แทน innerHTML ด้วย createElement
            const outerSpan = document.createElement('span');
            const strong = document.createElement('strong');
            strong.textContent = file.filename; // SAFE
            const statusSpan = document.createElement('span');
            statusSpan.className = 'file-status status-orange';
            statusSpan.textContent = `Duplicate: ${file.message}`; // SAFE: textContent
            outerSpan.appendChild(strong);
            outerSpan.appendChild(document.createTextNode(' '));
            outerSpan.appendChild(statusSpan);
            li.appendChild(outerSpan);
            list.appendChild(li);

        } else if (file.status === "failed") {
            // [A1-FIX] แทน innerHTML ด้วย createElement
            const outerSpan = document.createElement('span');
            const strong = document.createElement('strong');
            strong.textContent = file.filename; // SAFE
            const statusSpan = document.createElement('span');
            statusSpan.className = 'file-status status-red';
            statusSpan.textContent = `Failed: ${file.message}`; // SAFE: textContent
            outerSpan.appendChild(strong);
            outerSpan.appendChild(document.createTextNode(' '));
            outerSpan.appendChild(statusSpan);
            li.appendChild(outerSpan);
            list.appendChild(li);
        }
    });
}

function showPreview(fileId, filename) {
    const previewTitle = document.getElementById('previewTitle');
    previewTitle.textContent = `Data Preview: ${filename} (First 10 rows)`; // SAFE: textContent
    document.getElementById('previewSection').classList.remove('hidden');
    document.getElementById('tableContainer').innerHTML = '';
    document.getElementById('jsonPreview').textContent = '';

    const previewData = AppState.getPreview(fileId); // [B3] แทน: globalPreviews[fileId]

    if (!previewData || previewData.length === 0) {
        // [A1-FIX] ส่วนนี้ไม่มี User Data จึงปลอดภัยที่จะใช้ innerHTML กับ Static String
        document.getElementById('tableContainer').innerHTML = '<p class="error-text">No instant preview available for this file.</p>';
        return;
    }

    document.getElementById('jsonPreview').textContent = JSON.stringify(previewData, null, 2); // SAFE: textContent

    // [A1-FIX] สร้าง Table ด้วย createElement แทน String Concatenation
    // Column Headers และ Cell Values มาจากไฟล์ที่ผู้ใช้อัปโหลด — ต้องป้องกัน XSS ทุกตัว
    const table = document.createElement('table');
    const thead = document.createElement('thead');
    const headerRow = document.createElement('tr');

    const keys = Object.keys(previewData[0]);
    keys.forEach(k => {
        const th = document.createElement('th');
        th.textContent = k; // SAFE: textContent ป้องกัน Column Name ที่เป็น HTML
        headerRow.appendChild(th);
    });
    thead.appendChild(headerRow);
    table.appendChild(thead);

    const tbody = document.createElement('tbody');
    previewData.forEach(row => {
        const tr = document.createElement('tr');
        keys.forEach(k => {
            const td = document.createElement('td');
            td.textContent = row[k] !== null ? row[k] : ''; // SAFE: textContent
            tr.appendChild(td);
        });
        tbody.appendChild(tr);
    });
    table.appendChild(tbody);

    document.getElementById('tableContainer').appendChild(table);
}

// ================= API & BUSINESS LOGIC =================

function removeFile(index) {
    AppState.removeFile(index); // [B3] แทน: selectedFiles.splice(index, 1)
    renderQueue();
}

async function uploadBatch(batchFiles) {
    const formData = new FormData();
    for (let i = 0; i < batchFiles.length; i++) {
        formData.append("files", batchFiles[i]);
    }

    try {
        // [A2-FIX] ใช้ API_BASE_URL จาก config แทน Hardcoded localhost
        const response = await fetch(`${API_BASE_URL}/api/v1/upload`, {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            const errorRes = await response.json().catch(() => ({}));
            const errorMsg = errorRes.detail || "Unknown error during batch upload";
            const error = new Error(errorMsg);
            error.status = response.status;
            throw error;
        }
        return await response.json();
    } catch (err) {
        throw err;
    }
}

async function uploadFile() {
    const status = document.getElementById('uploadStatus');

    if (AppState.getFileCount() === 0) { // [B3] แทน: selectedFiles.length === 0
        status.className = "status-red";
        status.textContent = "Please select at least one file from the queue.";
        return;
    }

    const batchSize = 5;
    const totalBatches = Math.ceil(AppState.getFileCount() / batchSize); // [B3] แทน: selectedFiles.length
    let allUploadedFiles = [];
    let filesProcessed = 0;
    const maxRetries = 3;

    status.className = "status-blue";

    try {
        for (let i = 0; i < totalBatches; i++) {
            const startIdx = i * batchSize;
            const endIdx = startIdx + batchSize;
            const batchFiles = AppState.sliceFiles(startIdx, endIdx); // [B3] แทน: selectedFiles.slice

            let attempts = 0;
            let batchSuccess = false;

            while (attempts <= maxRetries && !batchSuccess) {
                try {
                    if (attempts === 0) {
                        status.textContent = `Uploading batch ${i + 1} of ${totalBatches}... Please wait.`;
                    } else {
                        status.className = "status-orange";
                        status.textContent = `Batch ${i + 1}/${totalBatches} - Retrying... Attempt ${attempts}/${maxRetries}`;
                    }

                    const result = await uploadBatch(batchFiles);
                    if (result.results) {
                        allUploadedFiles = allUploadedFiles.concat(result.results);
                    }
                    filesProcessed += batchFiles.length;
                    batchSuccess = true;
                    status.className = "status-blue";
                } catch (error) {
                    const isNetworkError = !error.status;
                    const isServerError = error.status >= 500 && error.status < 600;

                    if ((isNetworkError || isServerError) && attempts < maxRetries) {
                        attempts++;
                        console.warn(`Batch ${i + 1} failed. Retrying in 5 seconds...`, error.message);
                        await new Promise(resolve => setTimeout(resolve, 5000));
                    } else {
                        throw error;
                    }
                }
            }
        }

        status.className = "status-green";
        status.textContent = `Success! Processed ${allUploadedFiles.length} file(s) across ${totalBatches} batch(es).`;

        AppState.clearFiles(); // [B3] แทน: selectedFiles = []
        renderQueue();
        renderUploadedFiles(allUploadedFiles);

    } catch (error) {
        status.className = "status-red";
        status.textContent = "Upload stopped: " + error.message;

        if (allUploadedFiles.length > 0) {
            renderUploadedFiles(allUploadedFiles);
        }

        if (filesProcessed > 0) {
            AppState.trimFiles(filesProcessed); // [B3] แทน: selectedFiles = selectedFiles.slice(filesProcessed)
            renderQueue();
        }
    }
}

// [A5-FIX] เพิ่ม maxAttempts เพื่อป้องกัน setInterval วิ่งตลอดไป
// หลัง 30 ครั้ง × 2 วินาที = 60 วินาที จะหยุดอัตโนมัติและแสดง Timeout
async function startPolling(fileId, maxAttempts = 30) {
    const span = document.getElementById(`statusSpan_${fileId}`);
    let attempts = 0;

    const interval = setInterval(async () => {
        attempts++;

        // [A5-FIX] Guard: หยุด Polling เมื่อเกิน maxAttempts
        if (attempts > maxAttempts) {
            clearInterval(interval);
            if (span) {
                span.textContent = 'Timeout: Status check stopped';
                span.className = 'file-status status-orange';
            }
            console.warn(`[Polling] Stopped for fileId=${fileId} after ${maxAttempts} attempts.`);
            return;
        }

        try {
            // [A2-FIX] ใช้ API_BASE_URL จาก config แทน Hardcoded localhost
            const response = await fetch(`${API_BASE_URL}/api/v1/status/${fileId}`);
            if (response.ok) {
                const result = await response.json();
                if (result.status === "completed") {
                    clearInterval(interval);
                    if (span) {
                        span.textContent = "Saved to DB";
                        span.className = "file-status status-green";
                    }
                } else if (result.status === "failed") {
                    clearInterval(interval);
                    if (span) {
                        span.textContent = "DB Error (Rolled back)";
                        span.className = "file-status status-red";
                    }
                }
                // ถ้าเป็น "uploaded" หรือ "processing" ให้ Poll ต่อตามปกติ
            } else {
                clearInterval(interval);
                if (span) {
                    span.textContent = "Status Unknown";
                    span.className = "file-status status-red";
                }
            }
        } catch (error) {
            console.error(`Error polling status for ${fileId}:`, error);
            // ไม่ clearInterval ทันที — ให้ Retry ต่อจนถึง maxAttempts
        }
    }, 2000);
}
