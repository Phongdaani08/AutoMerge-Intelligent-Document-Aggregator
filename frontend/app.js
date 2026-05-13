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

// ================= DOM ELEMENTS =================
const fileInput = document.getElementById('fileInput');
const dropZone = document.getElementById('dropZone');
const queueList = document.getElementById('queueList');
const uploadBtn = document.getElementById('uploadBtn');

// ================= LIFECYCLE & CANCELLATION =================
let globalUploadController = null;
const activePollers = new Map();

function updatePollingDOM(fileId, className, text, stopPolling = false) {
    const span = document.getElementById(`statusSpan_${fileId}`);
    if (!span) {
        console.warn(`[DOM] Element statusSpan_${fileId} missing, clearing poller.`);
        if (activePollers.has(fileId)) {
            activePollers.get(fileId).stop();
            activePollers.delete(fileId);
        }
        return;
    }
    span.textContent = text;
    span.className = `file-status ${className}`;
    if (stopPolling) {
        activePollers.delete(fileId);
    }
}

// ================= EVENT LISTENERS =================

function handleFileSelect(event) {
    const newFiles = Array.from(event.target.files);
    AppState.addFiles(newFiles); // [B3] แทน: selectedFiles = selectedFiles.concat(newFiles)
    event.target.value = '';
    renderQueue();
}

// ================= INITIALIZATION =================
document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('fileInput').addEventListener('change', handleFileSelect);
    document.getElementById('uploadBtn').addEventListener('click', uploadFile);
});

// ================= DOM/UI RENDERING =================



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

            if (activePollers.has(file.file_id)) {
                activePollers.get(file.file_id).stop();
            }

            // [B4] ใช้ API.startPolling ส่ง callback กลับมาอัปเดต DOM
            const poller = API.startPolling(file.file_id, {
                maxAttempts: 30,
                onComplete: (msg) => updatePollingDOM(file.file_id, "status-green", msg, true),
                onError: (msg) => updatePollingDOM(file.file_id, "status-red", msg, true),
                onTimeout: (msg) => updatePollingDOM(file.file_id, "status-orange", msg, true)
            });
            activePollers.set(file.file_id, poller);

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

async function uploadFile() {
    const status = document.getElementById('uploadStatus');

    if (AppState.getFileCount() === 0) { // [B3] แทน: selectedFiles.length === 0
        status.className = "status-red";
        status.textContent = "Please select at least one file from the queue.";
        return;
    }

    if (globalUploadController) {
        globalUploadController.abort();
    }
    globalUploadController = new AbortController();
    const signal = globalUploadController.signal;

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

            // [B4] Use API.uploadWithRetry
            const result = await API.uploadWithRetry({
                batchFiles,
                maxRetries,
                signal,
                onRetry: (attempts, max) => {
                    if (attempts === 0) {
                        status.textContent = `Uploading batch ${i + 1} of ${totalBatches}... Please wait.`;
                        status.className = "status-blue";
                    } else {
                        status.className = "status-orange";
                        status.textContent = `Batch ${i + 1}/${totalBatches} - Retrying... Attempt ${attempts}/${max}`;
                    }
                }
            });

            if (result && result.success && result.data && result.data.results) {
                allUploadedFiles = allUploadedFiles.concat(result.data.results);
            }
            filesProcessed += batchFiles.length;
            status.className = "status-blue";
        }

        status.className = "status-green";
        status.textContent = `Success! Processed ${allUploadedFiles.length} file(s) across ${totalBatches} batch(es).`;

        AppState.clearFiles(); // [B3] แทน: selectedFiles = []
        renderQueue();
        renderUploadedFiles(allUploadedFiles);

    } catch (error) {
        if (error.name === 'AbortError') {
            status.className = "status-orange";
            status.textContent = "Upload cancelled.";
            return;
        }

        status.className = "status-red";
        status.textContent = "Upload stopped: " + error.message;

        if (allUploadedFiles.length > 0) {
            renderUploadedFiles(allUploadedFiles);
        }

        if (filesProcessed > 0) {
            AppState.trimFiles(filesProcessed); // [B3] แทน: selectedFiles = selectedFiles.slice(filesProcessed)
            renderQueue();
        }
    } finally {
        globalUploadController = null;
    }
}

