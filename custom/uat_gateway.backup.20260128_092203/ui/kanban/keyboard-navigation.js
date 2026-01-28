/**
 * Keyboard Navigation JavaScript Module
 *
 * Feature #236: UAT gateway supports keyboard navigation
 *
 * Provides comprehensive keyboard navigation support including:
 * - Logical tab order
 * - Arrow key navigation
 * - Keyboard shortcuts
 * - Modal focus trapping
 * - Escape key handling
 * - Enter key activation
 */

(function() {
    'use strict';

    // ========================================
    // STATE MANAGEMENT
    // ========================================

    const state = {
        focusTrapSelectors: [],
        previousFocusElement: null,
        keyboardNavigationActive: false,
        shortcuts: new Map(),
        currentFocusIndex: -1
    };

    // ========================================
    // DEFAULT KEYBOARD SHORTCUTS
    // ========================================

    const defaultShortcuts = [
        {
            key: 'Alt+m',
            description: 'Skip to main content',
            action: () => navigateToElement('#main-content', 'main'),
            category: 'navigation'
        },
        {
            key: 'Alt+n',
            description: 'Skip to navigation',
            action: () => navigateToElement('nav', 'navigation'),
            category: 'navigation'
        },
        {
            key: 'Alt+c',
            description: 'Skip to card grid',
            action: () => navigateToElement('.uat-card-grid', 'card grid'),
            category: 'navigation'
        },
        {
            key: 'Alt+f',
            description: 'Focus filter controls',
            action: () => navigateToElement('[data-filter-type]', 'filter controls'),
            category: 'filter'
        },
        {
            key: 'Escape',
            description: 'Close modal or dialog',
            action: () => closeActiveModal(),
            category: 'modal'
        },
        {
            key: '?',
            description: 'Show keyboard shortcuts help',
            action: () => showKeyboardHelp(),
            category: 'help'
        }
    ];

    // ========================================
    // NAVIGATION FUNCTIONS
    // ========================================

    /**
     * Navigate to a specific element
     */
    function navigateToElement(selector, label) {
        const element = document.querySelector(selector);
        if (element) {
            element.focus();
            announceToScreenReader(`Navigated to ${label}`);
            return true;
        } else {
            console.warn(`Keyboard navigation: Element not found: ${selector}`);
            return false;
        }
    }

    /**
     * Close the active modal
     */
    function closeActiveModal() {
        const modal = document.querySelector('.modal[role="dialog"]:not(.hidden), .modal:not(.hidden)');
        if (modal) {
            const closeButton = modal.querySelector('.modal-close, [data-action="close"], [aria-label="Close"]');
            if (closeButton) {
                closeButton.click();
                announceToScreenReader('Modal closed');
            }
            // Restore focus to previous element
            if (state.previousFocusElement) {
                state.previousFocusElement.focus();
            }
            return true;
        }
        return false;
    }

    /**
     * Show keyboard shortcuts help
     */
    function showKeyboardHelp() {
        // Create help modal if it doesn't exist
        let helpModal = document.getElementById('keyboard-shortcuts-help');

        if (!helpModal) {
            helpModal = createHelpModal();
        }

        helpModal.classList.remove('hidden');
        helpModal.querySelector('.modal-close').focus();
        announceToScreenReader('Keyboard shortcuts help displayed');
    }

    /**
     * Create keyboard shortcuts help modal
     */
    function createHelpModal() {
        const modal = document.createElement('div');
        modal.id = 'keyboard-shortcuts-help';
        modal.className = 'modal';
        modal.setAttribute('role', 'dialog');
        modal.setAttribute('aria-labelledby', 'keyboard-help-title');
        modal.setAttribute('aria-modal', 'true');

        const categories = {};
        state.shortcuts.forEach((shortcut, key) => {
            if (!categories[shortcut.category]) {
                categories[shortcut.category] = [];
            }
            categories[shortcut.category].push({ key, ...shortcut });
        });

        let shortcutsHTML = '';
        for (const [category, shortcuts] of Object.entries(categories)) {
            shortcutsHTML += `
                <h4>${category.charAt(0).toUpperCase() + category.slice(1)}</h4>
                <ul class="keyboard-shortcuts-list">
                    ${shortcuts.map(s => `
                        <li>
                            <kbd>${s.key}</kbd>
                            <span>${s.description}</span>
                        </li>
                    `).join('')}
                </ul>
            `;
        }

        modal.innerHTML = `
            <div class="modal-overlay" aria-hidden="true"></div>
            <div class="modal-content" role="document">
                <header class="modal-header">
                    <h2 id="keyboard-help-title">Keyboard Shortcuts</h2>
                    <button class="modal-close" aria-label="Close" data-action="close">&times;</button>
                </header>
                <div class="modal-body">
                    ${shortcutsHTML}
                    <p class="keyboard-tip">💡 Tip: Press <kbd>?</kbd> anytime to show this help</p>
                </div>
            </div>
        `;

        document.body.appendChild(modal);

        // Add close functionality
        modal.querySelector('.modal-close').addEventListener('click', () => {
            modal.classList.add('hidden');
        });

        modal.querySelector('.modal-overlay').addEventListener('click', () => {
            modal.classList.add('hidden');
        });

        return modal;
    }

    // ========================================
    // ARROW KEY NAVIGATION
    // ========================================

    /**
     * Handle arrow key navigation in lists/grids
     */
    function handleArrowNavigation(event) {
        const key = event.key;
        const target = event.target;

        // Find parent list/grid
        const list = target.closest('.uat-card-grid, [role="listbox"], [role="list"]');
        if (!list) return;

        const items = getFocusableItems(list);
        if (items.length === 0) return;

        const currentIndex = items.indexOf(target);
        if (currentIndex === -1) return;

        let nextIndex = currentIndex;

        switch (key) {
            case 'ArrowDown':
                event.preventDefault();
                nextIndex = (currentIndex + 1) % items.length;
                break;
            case 'ArrowUp':
                event.preventDefault();
                nextIndex = (currentIndex - 1 + items.length) % items.length;
                break;
            case 'ArrowRight':
                // For grid layout, move right
                if (list.classList.contains('uat-card-grid')) {
                    event.preventDefault();
                    nextIndex = (currentIndex + 1) % items.length;
                }
                break;
            case 'ArrowLeft':
                // For grid layout, move left
                if (list.classList.contains('uat-card-grid')) {
                    event.preventDefault();
                    nextIndex = (currentIndex - 1 + items.length) % items.length;
                }
                break;
            case 'Home':
                event.preventDefault();
                nextIndex = 0;
                break;
            case 'End':
                event.preventDefault();
                nextIndex = items.length - 1;
                break;
            default:
                return;
        }

        items[nextIndex].focus();
        announceToScreenReader(`Item ${nextIndex + 1} of ${items.length}`);
    }

    /**
     * Get all focusable items in a container
     */
    function getFocusableItems(container) {
        const selectors = [
            '[tabindex="0"]',
            'button:not([disabled])',
            'a[href]',
            'input:not([disabled])',
            'select:not([disabled])',
            'textarea:not([disabled])',
            '[role="button"]:not([disabled])'
        ];

        return Array.from(container.querySelectorAll(selectors.join(', ')))
            .filter(el => el.offsetParent !== null); // Only visible elements
    }

    // ========================================
    // KEYBOARD EVENT HANDLING
    // ========================================

    /**
     * Handle keyboard events
     */
    function handleKeyDown(event) {
        const key = event.key;
        const target = event.target;
        const tagName = target.tagName.toLowerCase();

        // Mark keyboard navigation as active
        state.keyboardNavigationActive = true;
        setTimeout(() => {
            state.keyboardNavigationActive = false;
        }, 100);

        // Check for keyboard shortcuts
        const keyCombo = buildKeyCombo(event);
        if (state.shortcuts.has(keyCombo)) {
            const shortcut = state.shortcuts.get(keyCombo);
            if (shortcut.action()) {
                event.preventDefault();
                return;
            }
        }

        // Handle Escape key
        if (key === 'Escape') {
            if (closeActiveModal()) {
                event.preventDefault();
                return;
            }
        }

        // Handle arrow key navigation
        if (['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(key)) {
            handleArrowNavigation(event);
            return;
        }

        // Handle Space/Enter for role="button" elements
        if ((key === ' ' || key === 'Enter') && target.getAttribute('role') === 'button') {
            event.preventDefault();
            target.classList.add('keyboard-activating');
            target.click();
            setTimeout(() => {
                target.classList.remove('keyboard-activating');
            }, 150);
            return;
        }

        // Handle Ctrl+F for filter focus
        if (key === 'f' && event.ctrlKey) {
            event.preventDefault();
            navigateToElement('[data-filter-type]', 'filter controls');
            return;
        }
    }

    /**
     * Build keyboard shortcut combination string
     */
    function buildKeyCombo(event) {
        const parts = [];
        if (event.ctrlKey) parts.push('Ctrl');
        if (event.altKey) parts.push('Alt');
        if (event.shiftKey) parts.push('Shift');
        if (event.metaKey) parts.push('Meta');
        parts.push(event.key);
        return parts.join('+');
    }

    // ========================================
    // FOCUS MANAGEMENT
    // ========================================

    /**
     * Handle focus events
     */
    function handleFocus(event) {
        const target = event.target;

        // Store previous focus (for modal restoration)
        if (!target.closest('.modal')) {
            state.previousFocusElement = target;
        }

        // Add focus-visible class for browsers that don't support :focus-visible
        if (state.keyboardNavigationActive) {
            target.classList.add('keyboard-focus');
        }

        // Announce important elements to screen readers
        const announcement = target.getAttribute('aria-label') ||
                            target.getAttribute('title') ||
                            target.textContent?.trim().split(' ')[0];
        if (announcement) {
            // Subtle announcement for navigation feedback
            // announceToScreenReader(`Focused on ${announcement}`);
        }
    }

    /**
     * Handle blur events
     */
    function handleBlur(event) {
        event.target.classList.remove('keyboard-focus');
    }

    // ========================================
    // ACCESSIBILITY HELPERS
    // ========================================

    /**
     * Announce message to screen readers
     */
    function announceToScreenReader(message) {
        let announcer = document.getElementById('screen-reader-announcer');

        if (!announcer) {
            announcer = document.createElement('div');
            announcer.id = 'screen-reader-announcer';
            announcer.setAttribute('role', 'status');
            announcer.setAttribute('aria-live', 'polite');
            announcer.setAttribute('aria-atomic', 'true');
            announcer.className = 'sr-only';
            document.body.appendChild(announcer);
        }

        announcer.textContent = message;
        setTimeout(() => {
            announcer.textContent = '';
        }, 1000);
    }

    // ========================================
    // INITIALIZATION
    // ========================================

    /**
     * Initialize focusable elements
     */
    function initializeFocusableElements() {
        // Make all UAT cards focusable
        document.querySelectorAll('.uat-card').forEach((card, index) => {
            if (!card.hasAttribute('tabindex')) {
                card.setAttribute('tabindex', '0');
            }
            if (!card.hasAttribute('role')) {
                card.setAttribute('role', 'button');
            }
            if (!card.hasAttribute('aria-label')) {
                const title = card.querySelector('.uat-card__title')?.textContent || `Card ${index + 1}`;
                card.setAttribute('aria-label', title);
            }
        });

        // Ensure all buttons are focusable
        document.querySelectorAll('button').forEach(button => {
            if (!button.hasAttribute('tabindex')) {
                button.setAttribute('tabindex', '0');
            }
            // Add aria-label to icon-only buttons
            if (!button.textContent.trim() && !button.hasAttribute('aria-label')) {
                const icon = button.querySelector('[class*="icon"], svg');
                if (icon) {
                    const label = icon.getAttribute('aria-label') || 'Button';
                    button.setAttribute('aria-label', label);
                }
            }
        });

        // Ensure all links are focusable
        document.querySelectorAll('a').forEach(link => {
            if (!link.hasAttribute('tabindex')) {
                link.setAttribute('tabindex', '0');
            }
        });
    }

    /**
     * Add skip links
     */
    function addSkipLinks() {
        const mainContent = document.querySelector('#main-content, main, .uat-card-grid');
        const nav = document.querySelector('nav');

        if (mainContent && !document.querySelector('.skip-link[href*="main"]')) {
            const skipLink = document.createElement('a');
            skipLink.href = '#main-content';
            skipLink.className = 'skip-link';
            skipLink.textContent = 'Skip to main content';
            document.body.insertBefore(skipLink, document.body.firstChild);
        }

        if (nav && !document.querySelector('.skip-link[href*="nav"]')) {
            const skipNav = document.createElement('a');
            skipNav.href = '#nav';
            skipNav.className = 'skip-link';
            skipNav.style.top = '-80px';
            skipNav.textContent = 'Skip to navigation';
            document.body.insertBefore(skipNav, document.body.firstChild);
        }
    }

    /**
     * Register keyboard shortcuts
     */
    function registerShortcuts() {
        defaultShortcuts.forEach(shortcut => {
            state.shortcuts.set(shortcut.key, shortcut);
        });
    }

    /**
     * Initialize keyboard navigation
     */
    function init() {
        console.log('Initializing keyboard navigation...');

        // Register event listeners
        document.addEventListener('keydown', handleKeyDown);
        document.addEventListener('focus', handleFocus, true);
        document.addEventListener('blur', handleBlur, true);

        // Initialize focusable elements
        initializeFocusableElements();

        // Add skip links
        addSkipLinks();

        // Register shortcuts
        registerShortcuts();

        // Add screen-reader-only class styles
        if (!document.getElementById('sr-only-styles')) {
            const style = document.createElement('style');
            style.id = 'sr-only-styles';
            style.textContent = `
                .sr-only {
                    position: absolute;
                    width: 1px;
                    height: 1px;
                    padding: 0;
                    margin: -1px;
                    overflow: hidden;
                    clip: rect(0, 0, 0, 0);
                    white-space: nowrap;
                    border: 0;
                }
            `;
            document.head.appendChild(style);
        }

        console.log('✓ Keyboard navigation initialized');
        console.log(`  - Registered ${state.shortcuts.size} keyboard shortcuts`);
        console.log('  - Type ? for shortcuts help');
    }

    // ========================================
    // PUBLIC API
    // ========================================

    window.KeyboardNavigation = {
        init,

        navigateTo: navigateToElement,

        closeActiveModal,

        showHelp: showKeyboardHelp,

        setFocusTrap(selectors) {
            state.focusTrapSelectors = selectors;
        },

        clearFocusTrap() {
            state.focusTrapSelectors = [];
        },

        registerShortcut(key, description, action, category = 'custom') {
            state.shortcuts.set(key, { key, description, action, category });
        },

        unregisterShortcut(key) {
            state.shortcuts.delete(key);
        },

        getShortcuts() {
            return Array.from(state.shortcuts.values());
        },

        announce: announceToScreenReader
    };

    // ========================================
    // AUTO-INITIALIZE
    // ========================================

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();

/**
 * Usage Examples:
 *
 * // Navigate programmatically
 * KeyboardNavigation.navigateTo('.uat-card-grid');
 *
 * // Register custom shortcut
 * KeyboardNavigation.registerShortcut('Alt+s', 'Save changes', () => {
 *     document.querySelector('[data-action="save"]').click();
 * }, 'actions');
 *
 * // Announce to screen readers
 * KeyboardNavigation.announce('Changes saved successfully');
 */
