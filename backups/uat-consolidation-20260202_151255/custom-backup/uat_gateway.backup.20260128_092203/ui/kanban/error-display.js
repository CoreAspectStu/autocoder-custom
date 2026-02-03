/**
 * API Error Display System - Feature #325
 *
 * Displays user-friendly error messages from API errors
 * - Shows error message from backend
 * - Shows suggested action
 * - Logs error to console for debugging (only in DEBUG mode)
 * - Integrates with toast notification system
 *
 * Feature #423: No console errors or warnings in production
 * - Console logging is disabled by default
 * - Set window.DEBUG = true to enable debug logging
 */

/**
 * Debug logging function - only logs if DEBUG mode is enabled
 * Feature #423: Prevents console errors/warnings in production
 *
 * @param {string} level - Log level ('error', 'warn', 'info', 'log')
 * @param {...any} args - Arguments to log
 */
function debugLog(level, ...args) {
  // Only log if DEBUG mode is explicitly enabled
  if (typeof window !== 'undefined' && window.DEBUG === true) {
    const consoleFn = console[level] || console.log;
    consoleFn(...args);
  }
}

/**
 * Display an API error to the user
 *
 * @param {Object} errorResponse - Error response from API
 * @param {string} errorResponse.error - User-friendly error message
 * @param {string} errorResponse.error_code - Error code
 * @param {string} errorResponse.action - Suggested action to resolve
 * @param {string} errorResponse.timestamp - When the error occurred
 * @param {string} [customMessage] - Optional custom error message
 */
function displayApiError(errorResponse, customMessage = null) {
  // Log full error for debugging (only in DEBUG mode)
  debugLog('error', 'API Error:', errorResponse);

  // Use custom message if provided, otherwise use backend message
  const errorMessage = customMessage || errorResponse.error || 'An unexpected error occurred';
  const errorAction = errorResponse.action || 'Please try again or contact support if the problem persists';
  const errorCode = errorResponse.error_code || 'UNKNOWN_ERROR';

  // Show error as a toast notification (if toast manager is available)
  if (typeof toastManager !== 'undefined' && toastManager.showError) {
    toastManager.showError({
      action: 'Error',
      message: errorMessage,
      suggestedAction: errorAction,
      errorCode: errorCode
    });
  } else {
    // Fallback: Show alert if toast manager not available
    alert(`${errorMessage}\n\n${errorAction}`);
  }

  // Return error info for potential further handling
  return {
    message: errorMessage,
    action: errorAction,
    code: errorCode,
    timestamp: errorResponse.timestamp,
    fullResponse: errorResponse
  };
}

/**
 * Display a network/connection error
 *
 * @param {Error} error - The error object
 * @param {string} [url] - The URL that failed
 */
function displayNetworkError(error, url = null) {
  debugLog('error', 'Network Error:', error, url);

  let errorMessage = 'Network connection failed';
  let errorAction = 'Check your internet connection and try again';

  if (error.message) {
    if (error.message.includes('fetch')) {
      errorMessage = 'Unable to reach the server';
      errorAction = 'Check if the server is running and try again';
    } else if (error.message.includes('timeout')) {
      errorMessage = 'Request timed out';
      errorAction = 'The server took too long to respond. Please try again';
    } else if (error.message.includes('abort')) {
      errorMessage = 'Request was cancelled';
      errorAction = 'The request was cancelled. Please retry if needed';
    }
  }

  const errorInfo = {
    error: errorMessage,
    error_code: 'NETWORK_ERROR',
    action: errorAction,
    timestamp: new Date().toISOString()
  };

  return displayApiError(errorInfo);
}

/**
 * Display a validation error
 *
 * @param {Object} validationErrors - Validation error details
 */
function displayValidationError(validationErrors) {
  debugLog('error', 'Validation Error:', validationErrors);

  let errorMessage = 'Please check your input';
  let errorAction = 'Fix the highlighted fields and try again';

  // If validation errors have details, show them
  if (validationErrors.detail) {
    errorMessage = validationErrors.detail;
  } else if (Array.isArray(validationErrors.errors)) {
    // Multiple field errors
    const fields = validationErrors.errors.map(e => e.field).join(', ');
    errorMessage = `Please check: ${fields}`;
    errorAction = 'Correct the invalid fields and submit again';
  }

  const errorInfo = {
    error: errorMessage,
    error_code: 'VALIDATION_ERROR',
    action: errorAction,
    timestamp: new Date().toISOString()
  };

  return displayApiError(errorInfo);
}

/**
 * Wrap API call with automatic error display
 *
 * @param {Promise} apiCall - The API call promise
 * @param {Object} options - Options
 * @param {string} [options.errorMessage] - Custom error message
 * @param {Function} [options.onSuccess] - Success callback
 * @param {Function} [options.onError] - Error callback
 * @returns {Promise} Promise that resolves with data or rejects with error
 */
async function withErrorDisplay(apiCall, options = {}) {
  const {
    errorMessage = null,
    onSuccess = null,
    onError = null
  } = options;

  try {
    const result = await apiCall;

    if (onSuccess) {
      onSuccess(result.data || result);
    }

    return result;
  } catch (error) {
    // Handle different error types
    if (error.response) {
      // API returned an error response
      const errorData = error.response.data || error.response;
      displayApiError(errorData, errorMessage);
    } else if (error.request) {
      // Request was made but no response
      displayNetworkError(error, error.config?.url);
    } else {
      // Error in setting up the request
      displayApiError({
        error: errorMessage || error.message || 'An unexpected error occurred',
        error_code: 'CLIENT_ERROR',
        action: 'Please try again or contact support',
        timestamp: new Date().toISOString()
      });
    }

    if (onError) {
      onError(error);
    }

    throw error;
  }
}

// ============================================================================
// Enhanced Toast Manager with Error Support
// ============================================================================

/**
 * Add error display support to ToastManager
 * Call this after toast-notifications.js is loaded
 */
function enhanceToastManager() {
  if (typeof ToastManager === 'undefined') {
    debugLog('warn', 'ToastManager not available, skipping error enhancement');
    return;
  }

  // Add showError method to ToastManager
  ToastManager.prototype.showError = function(options) {
    if (!this.container && !this.init()) {
      debugLog('error', 'Cannot show error toast: container not available');
      return null;
    }

    const {
      action = 'Error',
      message,
      suggestedAction = 'Please try again',
      errorCode = 'ERROR',
      duration = 8000  // Errors stay longer (8s instead of 5s)
    } = options;

    const toastId = `error-${this.nextId++}`;

    // Create error toast element
    const toast = this.createErrorToastElement({
      id: toastId,
      action,
      message,
      suggestedAction,
      errorCode
    });

    // Add to container
    this.container.appendChild(toast);
    this.toasts.set(toastId, toast);

    // Log for debugging
    console.log(`❌ Error toast shown: ${action} - ${message}`);

    // Auto-dismiss after delay (longer for errors)
    const timeoutId = setTimeout(() => {
      this.dismiss(toastId);
    }, duration);

    // Store timeout
    toast.dataset.timeoutId = timeoutId;

    // Limit total toasts
    this.enforceMaxToasts(5);

    return toastId;
  };

  // Method to create error toast element
  ToastManager.prototype.createErrorToastElement = function(options) {
    const { id, action, message, suggestedAction, errorCode } = options;

    const toast = document.createElement('div');
    toast.className = 'toast toast--error';
    toast.id = id;
    toast.setAttribute('role', 'alert');
    toast.setAttribute('aria-live', 'assertive');
    toast.setAttribute('aria-atomic', 'true');

    toast.innerHTML = `
      <div class="toast__icon toast__icon--error" aria-hidden="true">⚠</div>
      <div class="toast__content">
        <div class="toast__title">${this.escapeHtml(action)}</div>
        <div class="toast__message">${this.escapeHtml(message)}</div>
        <div class="toast__action">${this.escapeHtml(suggestedAction)}</div>
        <div class="toast__error-code">Error: ${this.escapeHtml(errorCode)}</div>
      </div>
      <button class="toast__close" aria-label="Close notification" data-toast-id="${id}">×</button>
      <div class="toast__progress"></div>
    `;

    // Add click handler for close button
    const closeBtn = toast.querySelector('.toast__close');
    closeBtn.addEventListener('click', () => {
      this.dismiss(id);
    });

    return toast;
  };

  console.log('✅ ToastManager enhanced with error display support');
}

// ============================================================================
// Auto-enhance on load
// ============================================================================

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', enhanceToastManager);
} else {
  enhanceToastManager();
}

// ============================================================================
// Exports
// ============================================================================

if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    displayApiError,
    displayNetworkError,
    displayValidationError,
    withErrorDisplay,
    enhanceToastManager
  };
}
