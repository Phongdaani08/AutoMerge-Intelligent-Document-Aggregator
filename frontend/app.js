// ================= STATE =================
let selectedFiles = [];
let globalPreviews = {}; // Store previews by fileId

// ================= INITIALIZATION =================
document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('fileInput').addEventListener('change', handleFileSelect);
    document.getElementById('uploadBtn').addEventListener('click', uploadFile);
});

// ================= DOM/UI RENDERING =================

function handleFileSelect(event) {
    const newFiles = Array.from(event.target.files);
    selectedFiles = selectedFiles.concat(newFiles);
    event.target.value = '';
    renderQueue();
}

function renderQueue() {
    const section = document.getElementById('queueSection');
    const list = document.getElementById('fileQueueList');

    if (selectedFiles.length === 0) {
        section.classList.add('hidden');
        return;
    }

    section.classList.remove('hidden');
    list.innerHTML = '';

    selectedFiles.forEach((file, index) => {
        const li = document.createElement('li');
        const sizeKB = (file.size / 1024).toFixed(2);

        const textSpan = document.createElement('span');
        textSpan.innerHTML = `<strong>${file.name}</strong> <span class="file-size">(${sizeKB} KB)</span>`;
        
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
                globalPreviews[file.file_id] = file.preview;
            }

            const textSpan = document.createElement('span');
            textSpan.innerHTML = `<strong>${file.filename}</strong> (ID: ${file.file_id}) <span id="statusSpan_${file.file_id}" class="file-status status-blue">Saving to DB...</span>`;
            
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
            li.innerHTML = `<span><strong>${file.filename}</strong> <span class="file-status status-orange">Duplicate: ${file.message}</span></span>`;
            list.appendChild(li);
            
        } else if (file.status === "failed") {
            li.innerHTML = `<span><strong>${file.filename}</strong> <span class="file-status status-red">Failed: ${file.message}</span></span>`;
            list.appendChild(li);
        }
    });
}

function showPreview(fileId, filename) {
    const previewTitle = document.getElementById('previewTitle');
    previewTitle.innerText = `Data Preview: ${filename} (First 10 rows)`;
    document.getElementById('previewSection').classList.remove('hidden');
    document.getElementById('tableContainer').innerHTML = '';
    document.getElementById('jsonPreview').innerText = '';

    const previewData = globalPreviews[fileId];

    if (!previewData || previewData.length === 0) {
        document.getElementById('tableContainer').innerHTML = '<p class="error-text">No instant preview available for this file.</p>';
        return;
    }

    document.getElementById('jsonPreview').innerText = JSON.stringify(previewData, null, 2);

    const keys = Object.keys(previewData[0]);
    let tableHTML = '<table><tr>';
    keys.forEach(k => tableHTML += `<th>${k}</th>`);
    tableHTML += '</tr>';

    previewData.forEach(row => {
        tableHTML += '<tr>';
        keys.forEach(k => tableHTML += `<td>${row[k] !== null ? row[k] : ''}</td>`);
        tableHTML += '</tr>';
    });
    tableHTML += '</table>';
    document.getElementById('tableContainer').innerHTML = tableHTML;
}

// ================= API & BUSINESS LOGIC =================

function removeFile(index) {
    selectedFiles.splice(index, 1);
    renderQueue();
}

async function uploadBatch(batchFiles) {
    const formData = new FormData();
    for (let i = 0; i < batchFiles.length; i++) {
        formData.append("files", batchFiles[i]);
    }
    
    try {
        const response = await fetch('http://localhost:8000/api/v1/upload', {
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

    if (selectedFiles.length === 0) {
        status.className = "status-red";
        status.innerText = "Please select at least one file from the queue.";
        return;
    }

    const batchSize = 5;
    const totalBatches = Math.ceil(selectedFiles.length / batchSize);
    let allUploadedFiles = [];
    let filesProcessed = 0;
    const maxRetries = 3;

    status.className = "status-blue";
    
    try {
        for (let i = 0; i < totalBatches; i++) {
            const startIdx = i * batchSize;
            const endIdx = startIdx + batchSize;
            const batchFiles = selectedFiles.slice(startIdx, endIdx);
            
            let attempts = 0;
            let batchSuccess = false;
            
            while (attempts <= maxRetries && !batchSuccess) {
                try {
                    if (attempts === 0) {
                        status.innerText = `Uploading batch ${i + 1} of ${totalBatches}... Please wait.`;
                    } else {
                        status.className = "status-orange";
                        status.innerText = `Batch ${i + 1}/${totalBatches} - Retrying... Attempt ${attempts}/${maxRetries}`;
                    }
                    
                    const result = await uploadBatch(batchFiles);
                    if (result.results) {
                        allUploadedFiles = allUploadedFiles.concat(result.results);
                    }
                    filesProcessed += batchFiles.length;
                    batchSuccess = true;
                    status.className = "status-blue"; // reset color on success
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
        status.innerText = `Success! Processed ${allUploadedFiles.length} file(s) across ${totalBatches} batch(es).`;

        selectedFiles = [];
        renderQueue();
        renderUploadedFiles(allUploadedFiles);
        
    } catch (error) {
        status.className = "status-red";
        status.innerText = "Upload stopped: " + error.message;
        
        if (allUploadedFiles.length > 0) {
            renderUploadedFiles(allUploadedFiles);
        }
        
        if (filesProcessed > 0) {
            selectedFiles = selectedFiles.slice(filesProcessed);
            renderQueue();
        }
    }
}

async function startPolling(fileId) {
    const span = document.getElementById(`statusSpan_${fileId}`);

    const interval = setInterval(async () => {
        try {
            const response = await fetch(`http://localhost:8000/api/v1/status/${fileId}`);
            if (response.ok) {
                const result = await response.json();
                if (result.status === "completed") {
                    clearInterval(interval);
                    span.innerText = "Saved to DB";
                    span.className = "file-status status-green";
                } else if (result.status === "failed") {
                    clearInterval(interval);
                    span.innerText = "DB Error (Rolled back)";
                    span.className = "file-status status-red";
                }
            } else {
                clearInterval(interval);
                span.innerText = "Status Unknown";
                span.className = "file-status status-red";
            }
        } catch (error) {
            console.error(`Error polling status for ${fileId}:`, error);
        }
    }, 2000);
}
