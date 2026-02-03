/**
 * Form Data Persistence Utility
 * Feature #313: Form data survives refresh
 *
 * Automatically saves form state to localStorage and restores it on page load.
 * Supports text inputs, textareas, selects, checkboxes, radio buttons, and file inputs.
 *
 * Usage:
 *   1. Add data-persist="true" to form elements you want to persist
 *   2. Add data-form-id="unique-id" to identify the form
 *   3. Include this script in your page
 *   4. Call FormPersistence.init() on page load
 */

class FormPersistence {
    constructor() {
        this.storagePrefix = 'form_persistence_';
        this.debounceTimers = {};
        this.debounceDelay = 300; // ms
    }

    /**
     * Initialize form persistence for all forms with data-persist attribute
     */
    init() {
        // Find all forms with data-persist="true"
        const forms = document.querySelectorAll('[data-persist="true"]');

        forms.forEach(form => {
            const formId = form.dataset.formId || form.id || this.generateFormId(form);
            form.dataset.formId = formId;

            // Restore saved state
            this.restoreFormState(formId, form);

            // Add listeners for auto-save
            this.attachSaveListeners(formId, form);
        });

        console.log(`[FormPersistence] Initialized for ${forms.length} form(s)`);
    }

    /**
     * Generate a unique form ID based on form fields
     */
    generateFormId(form) {
        const fields = Array.from(form.elements).map(el => el.name || el.id).filter(Boolean);
        return `form_${fields.join('_').substring(0, 50)}`;
    }

    /**
     * Attach event listeners to auto-save form changes
     */
    attachSaveListeners(formId, form) {
        // Get all persistable elements
        const elements = this.getPersistableElements(form);

        elements.forEach(element => {
            const fieldId = this.getFieldId(element);

            // Save on change (for selects, checkboxes, radios)
            element.addEventListener('change', () => {
                this.saveField(formId, fieldId, element);
            });

            // Save on input with debounce (for text inputs, textareas)
            if (['INPUT', 'TEXTAREA'].includes(element.tagName)) {
                element.addEventListener('input', () => {
                    this.debouncedSave(formId, fieldId, element);
                });
            }
        });

        // Also add beforeunload listener to catch any unsaved changes
        window.addEventListener('beforeunload', () => {
            this.saveFormState(formId, form);
        });
    }

    /**
     * Get all elements that should be persisted
     */
    getPersistableElements(form) {
        const elements = form.querySelectorAll('input, select, textarea');
        return Array.from(elements).filter(el => {
            // Skip elements with data-persist="false"
            if (el.dataset.persist === 'false') return false;

            // Only persist specific input types
            if (el.tagName === 'INPUT') {
                const validTypes = ['text', 'email', 'password', 'search', 'url', 'tel',
                                   'number', 'date', 'time', 'datetime-local', 'checkbox',
                                   'radio', 'file'];
                return validTypes.includes(el.type);
            }

            return true;
        });
    }

    /**
     * Get a unique identifier for a form field
     */
    getFieldId(element) {
        return element.name || element.id || `field_${Math.random().toString(36).substr(2, 9)}`;
    }

    /**
     * Save a single field value to localStorage
     */
    saveField(formId, fieldId, element) {
        const state = this.loadState(formId);
        state[fieldId] = this.getElementValue(element);
        state.lastUpdated = Date.now();
        this.saveState(formId, state);

        console.log(`[FormPersistence] Saved field ${fieldId} for form ${formId}`);
    }

    /**
     * Debounced save to avoid excessive localStorage writes
     */
    debouncedSave(formId, fieldId, element) {
        if (this.debounceTimers[fieldId]) {
            clearTimeout(this.debounceTimers[fieldId]);
        }

        this.debounceTimers[fieldId] = setTimeout(() => {
            this.saveField(formId, fieldId, element);
        }, this.debounceDelay);
    }

    /**
     * Save entire form state
     */
    saveFormState(formId, form) {
        const state = {
            lastUpdated: Date.now(),
            fields: {}
        };

        const elements = this.getPersistableElements(form);
        elements.forEach(element => {
            const fieldId = this.getFieldId(element);
            state.fields[fieldId] = this.getElementValue(element);
        });

        this.saveState(formId, state);
        console.log(`[FormPersistence] Saved form ${formId} with ${Object.keys(state.fields).length} fields`);
    }

    /**
     * Get the value of a form element
     */
    getElementValue(element) {
        if (element.type === 'checkbox' || element.type === 'radio') {
            return { checked: element.checked, value: element.value };
        } else if (element.type === 'file') {
            // For file inputs, we can't persist the actual file,
            // but we can persist the filename for UI restoration
            return { fileName: element.value };
        } else if (element.tagName === 'SELECT') {
            return { value: element.value, text: element.options[element.selectedIndex]?.text };
        } else {
            return element.value;
        }
    }

    /**
     * Set the value of a form element
     */
    setElementValue(element, savedValue) {
        if (savedValue === null || savedValue === undefined) return;

        if (element.type === 'checkbox' || element.type === 'radio') {
            element.checked = savedValue.checked;
        } else if (element.type === 'file') {
            // Can't restore actual file, but can show filename
            element.value = ''; // File inputs can't be set programmatically
        } else if (element.tagName === 'SELECT') {
            element.value = savedValue.value;
        } else {
            element.value = savedValue;
        }

        // Trigger change event for any listeners
        element.dispatchEvent(new Event('change', { bubbles: true }));
    }

    /**
     * Restore form state from localStorage
     */
    restoreFormState(formId, form) {
        const state = this.loadState(formId);
        if (!state || Object.keys(state).length === 0) {
            console.log(`[FormPersistence] No saved state found for form ${formId}`);
            return;
        }

        const elements = this.getPersistableElements(form);
        let restoredCount = 0;

        elements.forEach(element => {
            const fieldId = this.getFieldId(element);
            const savedValue = state[fieldId] || state.fields?.[fieldId];

            if (savedValue !== undefined) {
                this.setElementValue(element, savedValue);
                restoredCount++;
            }
        });

        console.log(`[FormPersistence] Restored ${restoredCount} fields for form ${formId}`);

        // Dispatch custom event to notify that form was restored
        form.dispatchEvent(new CustomEvent('formRestored', {
            detail: { formId, fieldsRestored: restoredCount }
        }));
    }

    /**
     * Clear saved state for a specific form
     */
    clearFormState(formId) {
        const key = this.storagePrefix + formId;
        localStorage.removeItem(key);
        console.log(`[FormPersistence] Cleared state for form ${formId}`);
    }

    /**
     * Clear all saved form states
     */
    clearAllStates() {
        const keys = Object.keys(localStorage);
        keys.forEach(key => {
            if (key.startsWith(this.storagePrefix)) {
                localStorage.removeItem(key);
            }
        });
        console.log('[FormPersistence] Cleared all form states');
    }

    /**
     * Load state from localStorage
     */
    loadState(formId) {
        const key = this.storagePrefix + formId;
        const data = localStorage.getItem(key);
        return data ? JSON.parse(data) : null;
    }

    /**
     * Save state to localStorage
     */
    saveState(formId, state) {
        const key = this.storagePrefix + formId;
        localStorage.setItem(key, JSON.stringify(state));
    }

    /**
     * Check if a form has saved state
     */
    hasState(formId) {
        return this.loadState(formId) !== null;
    }

    /**
     * Get metadata about saved state
     */
    getStateInfo(formId) {
        const state = this.loadState(formId);
        if (!state) return null;

        return {
            formId,
            lastUpdated: state.lastUpdated,
            fieldCount: Object.keys(state.fields || state).length,
            age: Date.now() - state.lastUpdated
        };
    }

    /**
     * List all forms with saved state
     */
    listSavedForms() {
        const keys = Object.keys(localStorage);
        const formIds = keys
            .filter(key => key.startsWith(this.storagePrefix))
            .map(key => key.replace(this.storagePrefix, ''));

        return formIds.map(formId => this.getStateInfo(formId));
    }
}

// Create global instance
const formPersistence = new FormPersistence();

// Auto-initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => formPersistence.init());
} else {
    formPersistence.init();
}

// Export for use in other scripts
if (typeof module !== 'undefined' && module.exports) {
    module.exports = FormPersistence;
}
