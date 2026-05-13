/**
 * api.js — API Layer (fetch wrappers)
 * ============================================================
 * [B4] Extracted API logic from app.js (Production-Ready)
 * Handles HTTP requests, retries, polling, and cancellation.
 * ============================================================
 */
const API = (() => {
    const ENDPOINTS = {
        upload: '/api/v1/upload',
        status: (id) => `/api/v1/status/${id}`,
        preview: (id) => `/api/v1/preview/${id}`
    };

    const getBaseUrl = () => {
        return (window.APP_CONFIG && window.APP_CONFIG.API_BASE_URL)
            ? window.APP_CONFIG.API_BASE_URL
            : 'http://localhost:8000';
    };

    /**
     * Internal HTTP Wrapper with Standardized Error Contract
     */
    async function _http(endpoint, options = {}) {
        const timeoutMs = options.timeoutMs || 30000; // Default 30s timeout
        const controller = new AbortController();
        let isTimeout = false;

        const timeoutId = setTimeout(() => {
            isTimeout = true;
            controller.abort();
        }, timeoutMs);

        // Connect external signal if provided (Backward Compatibility)
        if (options.signal) {
            if (options.signal.aborted) {
                controller.abort();
            } else {
                options.signal.addEventListener('abort', () => controller.abort());
            }
        }

        const fetchOptions = { ...options, signal: controller.signal };
        delete fetchOptions.timeoutMs; // Clean up custom option before fetch

        try {
            const response = await fetch(`${getBaseUrl()}${endpoint}`, fetchOptions);
            clearTimeout(timeoutId);
            if (!response.ok) {
                let data = {};
                try {
                    data = await response.json();
                } catch (e) {
                    // Ignore JSON parse errors
                }
                const error = new Error(data.detail || data.message || "Unknown API Error");
                error.status = response.status;
                error.code = data.code || `HTTP_${response.status}`;
                throw error;
            }
            const data = await response.json();
            return { success: true, data: data, error: null };
        } catch (error) {
            clearTimeout(timeoutId);
            // Transform fetch errors (network down, timeout, aborted) into standard contract
            if (!error.status) {
                if (isTimeout) {
                    error.status = 408;
                    error.code = 'TIMEOUT';
                    error.message = 'Request Timeout';
                } else if (error.name === 'AbortError') {
                    error.status = 499;
                    error.code = 'ABORTED';
                } else {
                    error.status = 0;
                    error.code = 'NETWORK_ERROR';
                }
            }
            throw error;
        }
    }

    /**
     * Upload a batch of files
     */
    async function uploadBatch(batchFiles, signal) {
        const formData = new FormData();
        for (let i = 0; i < batchFiles.length; i++) {
            formData.append("files", batchFiles[i]);
        }
        return _http(ENDPOINTS.upload, {
            method: 'POST',
            body: formData,
            signal: signal
        });
    }

    /**
     * Upload batch with Exponential Backoff Retry logic
     */
    async function uploadWithRetry({ batchFiles, maxRetries = 3, onRetry, signal }) {
        let attempts = 0;
        let lastResult = null;

        while (attempts <= maxRetries) {
            if (signal && signal.aborted) {
                const abortErr = new Error("Upload cancelled");
                abortErr.name = "AbortError";
                throw abortErr;
            }

            try {
                if (onRetry) {
                    onRetry(attempts, maxRetries);
                }
                
                lastResult = await uploadBatch(batchFiles, signal);
                return lastResult; // Success
            } catch (error) {
                if (error.name === 'AbortError') {
                    throw error; // Don't retry if aborted
                }

                const isNetworkError = error.status === 0;
                const isTimeoutError = error.status === 408;
                const isServerError = error.status >= 500 && error.status < 600;

                if ((isNetworkError || isTimeoutError || isServerError) && attempts < maxRetries) {
                    attempts++;
                    // Exponential backoff: 2s, 4s, 8s
                    const delay = 1000 * (2 ** attempts);
                    console.warn(`[API] Batch failed. Retrying in ${delay/1000}s...`, error.message);
                    
                    await new Promise((resolve, reject) => {
                        const timeoutId = setTimeout(resolve, delay);
                        if (signal) {
                            signal.addEventListener('abort', () => {
                                clearTimeout(timeoutId);
                                reject(new DOMException('Aborted', 'AbortError'));
                            }, { once: true });
                        }
                    });
                } else {
                    throw error;
                }
            }
        }
        return lastResult;
    }

    /**
     * Poll status for a given file with Cancellation Control
     */
    function startPolling(fileId, options = {}) {
        const { maxAttempts = 30, onComplete, onError, onTimeout } = options;
        let attempts = 0;
        let isCancelled = false;
        let timeoutId = null;

        const poll = async () => {
            if (isCancelled) return;
            attempts++;

            if (attempts > maxAttempts) {
                console.warn(`[API] Polling stopped for fileId=${fileId} after ${maxAttempts} attempts.`);
                if (onTimeout) onTimeout('Timeout: Status check stopped');
                return;
            }

            try {
                const result = await _http(ENDPOINTS.status(fileId));
                if (isCancelled) return;

                if (result.success && result.data.status === "completed") {
                    if (onComplete) onComplete('Saved to DB');
                    return;
                } else if (result.success && result.data.status === "failed") {
                    if (onError) onError('DB Error (Rolled back)');
                    return;
                }
                // If uploaded/processing, continue polling
            } catch (error) {
                if (isCancelled) return;
                console.error(`[API] Error polling status for ${fileId}:`, error);
                if (error.status !== 0 && error.status !== 500 && error.status !== 502 && error.status !== 503 && error.status !== 504) {
                    if (onError) onError('Status Unknown');
                    return; // Stop polling if not network or server error
                }
            }

            if (!isCancelled) {
                timeoutId = setTimeout(poll, 2000);
            }
        };

        timeoutId = setTimeout(poll, 2000);

        return {
            stop: () => {
                isCancelled = true;
                if (timeoutId) clearTimeout(timeoutId);
            }
        };
    }

    /**
     * Fetch preview data from database
     */
    async function fetchPreview(fileId, signal) {
        return _http(ENDPOINTS.preview(fileId), { signal });
    }

    return {
        uploadBatch,
        uploadWithRetry,
        startPolling,
        fetchPreview
    };
})();
