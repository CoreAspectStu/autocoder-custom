/**
 * Toast Notification System - Feature #231
 *
 * Displays success notifications for completed actions
 * - Multiple toasts stack vertically
 * - Auto-dismiss after 5 seconds
 * - Manual dismiss with X button
 * - Clear, concise messages
 */

class ToastManager {
  constructor() {
    this.container = null;
    this.toasts = new Map(); // toastId -> toast element
    this.nextId = 1;
    this.autoDismissDelay = 5000; // 5 seconds
  }

  /**
   * Initialize the toast manager
   */
  init() {
    this.container = document.getElementById('toast-container');
    if (!this.container) {
      console.warn('Toast container not found');
      return false;
    }
    return true;
  }

  /**
   * Show a success toast notification
   *
   * @param {Object} options - Toast options
   * @param {string} options.action - Action that completed (e.g., "Test completed")
   * @param {string} options.message - Clear success message
   * @param {string} [options.entityType] - Entity type (e.g., "journey", "scenario")
   * @param {string} [options.entityId] - Entity ID
   * @param {Object} [options.metadata] - Additional metadata to display
   * @param {number} [options.duration] - Auto-dismiss duration in ms (default: 5000)
   * @returns {string} Toast ID
   */
  show({ action, message, entityType, entityId, metadata, duration }) {
    if (!this.container && !this.init()) {
      console.error('Cannot show toast: container not available');
      return null;
    }

    const toastId = `toast-${this.nextId++}`;
    const dismissDelay = duration || this.autoDismissDelay;

    // Create toast element
    const toast = this.createToastElement({
      id: toastId,
      action,
      message,
      entityType,
      entityId,
      metadata
    });

    // Add to container
    this.container.appendChild(toast);
    this.toasts.set(toastId, toast);

    // Log for debugging
    console.log(`✅ Toast shown: ${action} - ${message}`);

    // Auto-dismiss after delay
    const timeoutId = setTimeout(() => {
      this.dismiss(toastId);
    }, dismissDelay);

    // Store timeout for potential manual dismissal
    toast.dataset.timeoutId = timeoutId;

    // Limit total toasts (remove oldest if > 5)
    this.enforceMaxToasts(5);

    return toastId;
  }

  /**
   * Create a toast DOM element
   */
  createToastElement({ id, action, message, entityType, entityId, metadata }) {
    const toast = document.createElement('div');
    toast.className = 'toast';
    toast.id = id;
    toast.setAttribute('role', 'alert');
    toast.setAttribute('aria-live', 'polite');
    toast.setAttribute('aria-atomic', 'true');

    // Build meta tags if provided
    let metaHtml = '';
    if (entityType || entityId) {
      const metaItems = [];
      if (entityType) {
        metaItems.push(`<span class="toast__meta-item">${this.escapeHtml(entityType)}</span>`);
      }
      if (entityId) {
        metaItems.push(`<span class="toast__meta-item">${this.escapeHtml(entityId)}</span>`);
      }
      if (metadata && Object.keys(metadata).length > 0) {
        // Show first metadata item
        const [key, value] = Object.entries(metadata)[0];
        metaItems.push(`<span class="toast__meta-item">${this.escapeHtml(key)}: ${this.escapeHtml(String(value))}</span>`);
      }
      if (metaItems.length > 0) {
        metaHtml = `<div class="toast__meta">${metaItems.join('')}</div>`;
      }
    }

    toast.innerHTML = `
      <div class="toast__icon" aria-hidden="true">✓</div>
      <div class="toast__content">
        <div class="toast__title">${this.escapeHtml(action)}</div>
        <div class="toast__message">${this.escapeHtml(message)}</div>
        ${metaHtml}
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
  }

  /**
   * Dismiss a toast notification
   *
   * @param {string} toastId - Toast ID to dismiss
   */
  dismiss(toastId) {
    const toast = this.toasts.get(toastId);
    if (!toast) {
      return;
    }

    // Clear auto-dismiss timeout
    if (toast.dataset.timeoutId) {
      clearTimeout(parseInt(toast.dataset.timeoutId));
    }

    // Add dismissing class for animation
    toast.classList.add('toast-dismissing');

    // Remove after animation completes
    setTimeout(() => {
      if (toast.parentNode) {
        toast.parentNode.removeChild(toast);
      }
      this.toasts.delete(toastId);
      console.log(`Toast dismissed: ${toastId}`);
    }, 300); // Match CSS transition duration
  }

  /**
   * Dismiss all toast notifications
   */
  dismissAll() {
    const toastIds = Array.from(this.toasts.keys());
    toastIds.forEach(id => this.dismiss(id));
  }

  /**
   * Enforce maximum number of toasts (remove oldest)
   */
  enforceMaxToasts(max) {
    if (this.toasts.size <= max) {
      return;
    }

    const toastsArray = Array.from(this.toasts.entries());
    const toastsToRemove = toastsArray.slice(0, toastsArray.length - max);

    toastsToRemove.forEach(([id]) => {
      this.dismiss(id);
    });
  }

  /**
   * Escape HTML to prevent XSS
   */
  escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  /**
   * Get count of active toasts
   */
  getActiveCount() {
    return this.toasts.size;
  }
}

// ============================================================================
// Global Toast Manager Instance
// ============================================================================

const toastManager = new ToastManager();

// Initialize on DOM ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => {
    toastManager.init();
  });
} else {
  toastManager.init();
}

// ============================================================================
// Demo Functions (for testing acceptance criteria)
// ============================================================================

function showTestSuccessToast() {
  toastManager.show({
    action: 'Test Completed',
    message: 'Login test passed successfully with 8/8 assertions',
    entityType: 'scenario',
    entityId: 'SCENARIO-001',
    metadata: { duration: '45s' }
  });
}

function showCardCreatedToast() {
  toastManager.show({
    action: 'Card Created',
    message: 'New journey card created successfully',
    entityType: 'journey',
    entityId: 'JOURNEY-20250126-004'
  });
}

function showSettingsSavedToast() {
  toastManager.show({
    action: 'Settings Saved',
    message: 'Your preferences have been updated'
  });
}

function showMultipleToasts() {
  // Simulate multiple rapid success actions
  const actions = [
    { action: 'Journey Extracted', message: 'User Authentication journey extracted', entityType: 'journey' },
    { action: 'Tests Generated', message: '6 test scenarios generated successfully', metadata: { count: 6 } },
    { action: 'Tests Executed', message: 'All tests passed (6/6)', metadata: { duration: '2m 15s' } },
    { action: 'Card Created', message: 'Kanban card created for completed journey', entityType: 'journey' }
  ];

  actions.forEach((opts, index) => {
    setTimeout(() => {
      toastManager.show(opts);
    }, index * 300); // Stagger by 300ms
  });
}

function clearAllToasts() {
  toastManager.dismissAll();
}

// ============================================================================
// WebSocket Integration (for real-time notifications)
// ============================================================================

/**
 * Connect to WebSocket server and listen for success events
 * This integrates with the EventManager's broadcast_success() method
 */
async function connectToastWebSocket() {
  try {
    const ws = new WebSocket('ws://localhost:8765');

    ws.addEventListener('open', () => {
      console.log('✓ Connected to toast notification server');
    });

    ws.addEventListener('message', (event) => {
      try {
        const data = JSON.parse(event.data);

        // Handle success events
        if (data.event_type === 'success') {
          toastManager.show({
            action: data.action || 'Success',
            message: data.message || 'Action completed successfully',
            entityType: data.entity_type,
            entityId: data.entity_id,
            metadata: data.metadata
          });
        }
      } catch (err) {
        console.error('Failed to parse WebSocket message:', err);
      }
    });

    ws.addEventListener('close', () => {
      console.log('WebSocket connection closed');
      // Attempt reconnect after 5 seconds
      setTimeout(connectToastWebSocket, 5000);
    });

    ws.addEventListener('error', (err) => {
      console.error('WebSocket error:', err);
    });

    return ws;
  } catch (err) {
    console.error('Failed to connect to WebSocket:', err);
    return null;
  }
}

// Auto-connect to WebSocket for real-time notifications (optional)
// Uncomment to enable:
// connectToastWebSocket();

// ============================================================================
// Export for use in other modules
// ============================================================================

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { ToastManager, toastManager };
}
