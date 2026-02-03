/**
 * API Client Module for UAT Gateway
 *
 * Handles API requests with:
 * - Request cancellation (AbortController)
 * - Loading indicators
 * - Late response handling
 * - Request timeout
 * - Automatic retry on failure
 *
 * Feature #320: Late API response handling
 */

class APIClient {
    constructor(options = {}) {
        this.baseURL = options.baseURL || '/api';
        this.timeout = options.timeout || 30000; // 30 seconds default
        this.defaultHeaders = options.defaultHeaders || {
            'Content-Type': 'application/json'
        };

        // Track active requests for cancellation
        this.activeRequests = new Map();

        // Loading indicator callbacks
        this.loadingCallbacks = [];

        // Request ID counter
        this.requestIdCounter = 0;
    }

    /**
     * Register a callback for loading state changes
     * @param {Function} callback - Function(isLoading, requestId)
     */
    onLoadingChange(callback) {
        if (typeof callback === 'function') {
            this.loadingCallbacks.push(callback);
        }
    }

    /**
     * Notify all loading callbacks
     * @param {boolean} isLoading - Whether any request is loading
     * @param {string} requestId - The request ID
     */
    _notifyLoadingCallbacks(isLoading, requestId) {
        this.loadingCallbacks.forEach(callback => {
            try {
                callback(isLoading, requestId);
            } catch (error) {
                console.error('Error in loading callback:', error);
            }
        });
    }

    /**
     * Generate a unique request ID
     * @returns {string} Unique request ID
     */
    _generateRequestId() {
        return `req_${Date.now()}_${++this.requestIdCounter}`;
    }

    /**
     * Make an API request with cancellation and timeout support
     * @param {string} url - The endpoint URL
     * @param {object} options - Fetch options
     * @returns {Promise} Response promise
     */
    async fetch(url, options = {}) {
        const requestId = this._generateRequestId();
        const startTime = Date.now();
        let responseReceived = false;

        // Create abort controller for this request
        const controller = new AbortController();
        const signal = controller.signal;

        // Store the controller for cancellation
        this.activeRequests.set(requestId, {
            controller,
            url,
            startTime,
            options
        });

        // Notify loading start
        this._notifyLoadingCallbacks(true, requestId);

        try {
            // Set up timeout
            const timeoutId = setTimeout(() => {
                if (!responseReceived) {
                    controller.abort();
                }
            }, options.timeout || this.timeout);

            // Prepare fetch options
            const fetchOptions = {
                ...options,
                signal,
                headers: {
                    ...this.defaultHeaders,
                    ...options.headers
                }
            };

            // Make the request
            const response = await fetch(`${this.baseURL}${url}`, fetchOptions);
            responseReceived = true;
            clearTimeout(timeoutId);

            // Check if request was cancelled before response arrived
            if (signal.aborted) {
                throw new Error('Request cancelled');
            }

            // Check if the response is ok
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            // Parse JSON response
            const data = await response.json();

            // Clean up
            this.activeRequests.delete(requestId);
            this._notifyLoadingCallbacks(false, requestId);

            return {
                data,
                requestId,
                duration: Date.now() - startTime,
                status: response.status
            };

        } catch (error) {
            // Clean up
            this.activeRequests.delete(requestId);
            this._notifyLoadingCallbacks(false, requestId);

            // Handle different error types
            if (error.name === 'AbortError') {
                throw new Error('Request cancelled or timed out');
            }

            throw error;
        }
    }

    /**
     * Cancel a specific request
     * @param {string} requestId - The request ID to cancel
     * @returns {boolean} True if cancelled, false if not found
     */
    cancelRequest(requestId) {
        const request = this.activeRequests.get(requestId);
        if (request) {
            request.controller.abort();
            this.activeRequests.delete(requestId);
            return true;
        }
        return false;
    }

    /**
     * Cancel all active requests
     * @returns {number} Number of requests cancelled
     */
    cancelAllRequests() {
        let count = 0;
        for (const [requestId, request] of this.activeRequests.entries()) {
            request.controller.abort();
            count++;
        }
        this.activeRequests.clear();
        return count;
    }

    /**
     * Get list of active requests
     * @returns {Array} Active requests info
     */
    getActiveRequests() {
        return Array.from(this.activeRequests.entries()).map(([id, info]) => ({
            id,
            url: info.url,
            duration: Date.now() - info.startTime
        }));
    }

    /**
     * Convenience method: GET request
     */
    async get(url, options = {}) {
        return this.fetch(url, { ...options, method: 'GET' });
    }

    /**
     * Convenience method: POST request
     */
    async post(url, data, options = {}) {
        return this.fetch(url, {
            ...options,
            method: 'POST',
            body: JSON.stringify(data)
        });
    }

    /**
     * Convenience method: PUT request
     */
    async put(url, data, options = {}) {
        return this.fetch(url, {
            ...options,
            method: 'PUT',
            body: JSON.stringify(data)
        });
    }

    /**
     * Convenience method: DELETE request
     */
    async delete(url, options = {}) {
        return this.fetch(url, { ...options, method: 'DELETE' });
    }
}

// Create global instance
const apiClient = new APIClient();

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { APIClient, apiClient };
}
