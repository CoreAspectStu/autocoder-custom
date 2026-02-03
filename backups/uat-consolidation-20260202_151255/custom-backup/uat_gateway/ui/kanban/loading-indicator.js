/**
 * Loading Indicator Component for UAT Gateway
 *
 * Provides visual feedback for API requests:
 * - Global loading spinner
 * - Per-request loading indicators
 * - Request cancellation buttons
 * - Loading progress tracking
 *
 * Feature #320: Late API response handling
 */

class LoadingIndicator {
    constructor(options = {}) {
        this.container = options.container || document.body;
        this.position = options.position || 'top-right'; // top-right, top-left, bottom-right, bottom-left, center
        this.showCancel = options.showCancel !== false; // Show cancel button by default
        this.activeRequests = new Map();

        // Create container element
        this.element = this._createContainer();
        this.container.appendChild(this.element);
    }

    /**
     * Create the loading indicator container
     */
    _createContainer() {
        const container = document.createElement('div');
        container.className = 'loading-indicator-container';
        container.id = 'loading-indicator-container';

        // Position styles
        const positions = {
            'top-right': { top: '20px', right: '20px', bottom: 'auto', left: 'auto' },
            'top-left': { top: '20px', left: '20px', bottom: 'auto', right: 'auto' },
            'bottom-right': { bottom: '20px', right: '20px', top: 'auto', left: 'auto' },
            'bottom-left': { bottom: '20px', left: '20px', top: 'auto', right: 'auto' },
            'center': { top: '50%', left: '50%', transform: 'translate(-50%, -50%)' }
        };

        const pos = positions[this.position] || positions['top-right'];

        container.style.cssText = `
            position: fixed;
            top: ${pos.top};
            right: ${pos.right};
            bottom: ${pos.bottom};
            left: ${pos.left};
            ${pos.transform ? `transform: ${pos.transform};` : ''}
            z-index: 10000;
            display: flex;
            flex-direction: column;
            gap: 10px;
            pointer-events: none;
        `;

        return container;
    }

    /**
     * Show a loading indicator for a request
     * @param {string} requestId - The request ID
     * @param {string} message - Loading message
     * @param {Function} onCancel - Callback when cancel is clicked
     */
    show(requestId, message = 'Loading...', onCancel = null) {
        // Don't show duplicate indicators
        if (this.activeRequests.has(requestId)) {
            return;
        }

        const indicator = document.createElement('div');
        indicator.className = 'loading-indicator';
        indicator.id = `loading-${requestId}`;
        indicator.style.cssText = `
            background: white;
            border-radius: 8px;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
            padding: 12px 16px;
            display: flex;
            align-items: center;
            gap: 12px;
            min-width: 200px;
            max-width: 350px;
            pointer-events: auto;
            animation: slideIn 0.3s ease-out;
        `;

        // Spinner
        const spinner = document.createElement('div');
        spinner.className = 'loading-spinner';
        spinner.style.cssText = `
            width: 18px;
            height: 18px;
            border: 2px solid #f3f3f3;
            border-top: 2px solid #667eea;
            border-radius: 50%;
            animation: spin 1s linear infinite;
            flex-shrink: 0;
        `;

        // Message
        const messageEl = document.createElement('span');
        messageEl.className = 'loading-message';
        messageEl.textContent = message;
        messageEl.style.cssText = `
            font-size: 14px;
            color: #333;
            flex: 1;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        `;

        indicator.appendChild(spinner);
        indicator.appendChild(messageEl);

        // Cancel button
        if (this.showCancel && onCancel) {
            const cancelBtn = document.createElement('button');
            cancelBtn.className = 'loading-cancel-btn';
            cancelBtn.innerHTML = '✕';
            cancelBtn.title = 'Cancel request';
            cancelBtn.style.cssText = `
                background: #ef4444;
                color: white;
                border: none;
                border-radius: 4px;
                width: 24px;
                height: 24px;
                cursor: pointer;
                font-size: 16px;
                line-height: 1;
                display: flex;
                align-items: center;
                justify-content: center;
                flex-shrink: 0;
                transition: background 0.2s;
            `;

            cancelBtn.addEventListener('mouseenter', () => {
                cancelBtn.style.background = '#dc2626';
            });

            cancelBtn.addEventListener('mouseleave', () => {
                cancelBtn.style.background = '#ef4444';
            });

            cancelBtn.addEventListener('click', () => {
                if (onCancel) {
                    onCancel(requestId);
                }
                this.hide(requestId);
            });

            indicator.appendChild(cancelBtn);
        }

        this.element.appendChild(indicator);
        this.activeRequests.set(requestId, indicator);

        // Add CSS animations if not already present
        this._ensureStyles();
    }

    /**
     * Hide a loading indicator
     * @param {string} requestId - The request ID
     */
    hide(requestId) {
        const indicator = this.activeRequests.get(requestId);
        if (indicator) {
            indicator.style.animation = 'slideOut 0.3s ease-out';
            setTimeout(() => {
                if (indicator.parentNode) {
                    indicator.parentNode.removeChild(indicator);
                }
                this.activeRequests.delete(requestId);
            }, 300);
        }
    }

    /**
     * Update the loading message
     * @param {string} requestId - The request ID
     * @param {string} message - New message
     */
    update(requestId, message) {
        const indicator = this.activeRequests.get(requestId);
        if (indicator) {
            const messageEl = indicator.querySelector('.loading-message');
            if (messageEl) {
                messageEl.textContent = message;
            }
        }
    }

    /**
     * Hide all loading indicators
     */
    hideAll() {
        for (const [requestId, indicator] of this.activeRequests.entries()) {
            this.hide(requestId);
        }
    }

    /**
     * Ensure CSS animations are present
     */
    _ensureStyles() {
        if (document.getElementById('loading-indicator-styles')) {
            return;
        }

        const style = document.createElement('style');
        style.id = 'loading-indicator-styles';
        style.textContent = `
            @keyframes spin {
                0% { transform: rotate(0deg); }
                100% { transform: rotate(360deg); }
            }

            @keyframes slideIn {
                from {
                    opacity: 0;
                    transform: translateY(-20px);
                }
                to {
                    opacity: 1;
                    transform: translateY(0);
                }
            }

            @keyframes slideOut {
                from {
                    opacity: 1;
                    transform: translateY(0);
                }
                to {
                    opacity: 0;
                    transform: translateY(-20px);
                }
            }

            .loading-indicator-container {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            }
        `;

        document.head.appendChild(style);
    }

    /**
     * Destroy the loading indicator
     */
    destroy() {
        this.hideAll();
        if (this.element.parentNode) {
            this.element.parentNode.removeChild(this.element);
        }
    }
}

// Create global instance
const loadingIndicator = new LoadingIndicator();

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { LoadingIndicator, loadingIndicator };
}
