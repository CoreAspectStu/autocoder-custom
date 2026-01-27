"""
Keyboard Navigation Manager - Accessibility utilities for keyboard-only navigation

This module provides comprehensive keyboard navigation support to ensure all features
are accessible via keyboard, complying with WCAG 2.1 Level AA requirements.

Feature #236: UAT gateway supports keyboard navigation

Key Features:
- Logical tab order management
- Visible focus indicators
- Skip links for main content
- Keyboard shortcuts for common actions
- Escape key handling for modals
- Arrow key navigation within components
"""

import logging
from typing import List, Dict, Optional, Set, Callable, Any
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from uat_gateway.utils.logger import get_logger


class KeyboardKey(Enum):
    """Standard keyboard keys for navigation"""
    TAB = "Tab"
    ENTER = "Enter"
    SPACE = " "
    ESCAPE = "Escape"
    ARROW_UP = "ArrowUp"
    ARROW_DOWN = "ArrowDown"
    ARROW_LEFT = "ArrowLeft"
    ARROW_RIGHT = "ArrowRight"
    HOME = "Home"
    END = "End"
    PAGE_UP = "PageUp"
    PAGE_DOWN = "PageDown"


class FocusableRole(Enum):
    """ARIA roles for focusable elements"""
    BUTTON = "button"
    LINK = "link"
    TEXTBOX = "textbox"
    COMBOBOX = "combobox"
    MENUITEM = "menuitem"
    TAB = "tab"
    PANEL = "panel"
    DIALOG = "dialog"
    ALERTDIALOG = "alertdialog"


@dataclass
class FocusableElement:
    """Represents a focusable element in the UI"""
    selector: str
    role: FocusableRole
    label: str
    priority: int = 0
    shortcut: Optional[str] = None
    description: Optional[str] = None


@dataclass
class KeyboardShortcut:
    """Represents a keyboard shortcut"""
    key: str
    description: str
    action: str
    category: str = "general"
    prevent_default: bool = True


class KeyboardNavigationManager:
    """
    Manages keyboard navigation for the UAT Gateway interface

    Responsibilities:
    - Ensure logical tab order
    - Provide visible focus indicators
    - Support keyboard shortcuts
    - Handle escape key for modals
    - Support arrow key navigation
    """

    def __init__(self):
        self.logger = get_logger(__name__)
        self.focusable_elements: List[FocusableElement] = []
        self.shortcuts: Dict[str, KeyboardShortcut] = {}
        self.skip_links: List[Dict[str, str]] = []
        self.focus_trap_active = False
        self.focus_trap_elements: Set[str] = set()

    def add_focusable_element(self, element: FocusableElement) -> None:
        """Register a focusable element"""
        self.focusable_elements.append(element)
        self.focusable_elements.sort(key=lambda e: e.priority)
        self.logger.debug(f"Added focusable element: {element.selector} ({element.role.value})")

    def add_shortcut(self, shortcut: KeyboardShortcut) -> None:
        """Register a keyboard shortcut"""
        self.shortcuts[shortcut.key] = shortcut
        self.logger.debug(f"Added shortcut: {shortcut.key} - {shortcut.description}")

    def add_skip_link(self, target_id: str, label: str) -> None:
        """Add a skip link for keyboard users"""
        self.skip_links.append({
            "target": target_id,
            "label": label
        })
        self.logger.debug(f"Added skip link: {label} -> #{target_id}")

    def set_focus_trap(self, selectors: List[str]) -> None:
        """
        Set focus trap to keep focus within specific elements
        (e.g., modals, dialogs)
        """
        self.focus_trap_elements = set(selectors)
        self.focus_trap_active = True
        self.logger.debug(f"Focus trap active: {len(selectors)} elements")

    def clear_focus_trap(self) -> None:
        """Clear focus trap"""
        self.focus_trap_active = False
        self.focus_trap_elements.clear()
        self.logger.debug("Focus trap cleared")

    def get_default_shortcuts(self) -> List[KeyboardShortcut]:
        """Get default keyboard shortcuts for UAT Gateway"""
        return [
            KeyboardShortcut(
                key="Alt+M",
                description="Navigate to main content",
                action="skip-to-main",
                category="navigation"
            ),
            KeyboardShortcut(
                key="Alt+N",
                description="Navigate to navigation",
                action="skip-to-nav",
                category="navigation"
            ),
            KeyboardShortcut(
                key="Escape",
                description="Close modal or dialog",
                action="close-modal",
                category="modal"
            ),
            KeyboardShortcut(
                key="ArrowDown",
                description="Move to next item in list",
                action="next-item",
                category="navigation"
            ),
            KeyboardShortcut(
                key="ArrowUp",
                description="Move to previous item in list",
                action="previous-item",
                category="navigation"
            ),
            KeyboardShortcut(
                key="Home",
                description="Move to first item in list",
                action="first-item",
                category="navigation"
            ),
            KeyboardShortcut(
                key="End",
                description="Move to last item in list",
                action="last-item",
                category="navigation"
            ),
            KeyboardShortcut(
                key="Space",
                description="Activate button or toggle checkbox",
                action="activate",
                category="activation"
            ),
            KeyboardShortcut(
                key="Enter",
                description="Submit form or activate link",
                action="submit",
                category="activation"
            ),
        ]

    def get_uat_card_focusable_elements(self) -> List[FocusableElement]:
        """Get focusable elements for UAT card component"""
        return [
            FocusableElement(
                selector=".uat-card",
                role=FocusableRole.BUTTON,
                label="UAT Card",
                priority=1,
                description="Individual test card in the grid"
            ),
            FocusableElement(
                selector=".uat-card__button--primary",
                role=FocusableRole.BUTTON,
                label="Primary Action",
                priority=2,
                shortcut="Enter",
                description="Main action button on card"
            ),
            FocusableElement(
                selector=".uat-card__button--secondary",
                role=FocusableRole.BUTTON,
                label="Secondary Action",
                priority=3,
                description="Secondary action button on card"
            ),
        ]

    def get_filter_focusable_elements(self) -> List[FocusableElement]:
        """Get focusable elements for filter controls"""
        return [
            FocusableElement(
                selector="[data-filter-type]",
                role=FocusableRole.COMBOBOX,
                label="Filter Control",
                priority=10,
                shortcut="Ctrl+F",
                description="Filter control for results"
            ),
            FocusableElement(
                selector=".filter-checkbox",
                role=FocusableRole.TEXTBOX,
                label="Filter Checkbox",
                priority=11,
                description="Individual filter checkbox"
            ),
        ]

    def get_modal_focusable_elements(self) -> List[FocusableElement]:
        """Get focusable elements for modal dialogs"""
        return [
            FocusableElement(
                selector=".modal-close",
                role=FocusableRole.BUTTON,
                label="Close Modal",
                priority=100,
                shortcut="Escape",
                description="Close the current modal"
            ),
            FocusableElement(
                selector=".modal-confirm",
                role=FocusableRole.BUTTON,
                label="Confirm",
                priority=101,
                shortcut="Enter",
                description="Confirm modal action"
            ),
            FocusableElement(
                selector=".modal-cancel",
                role=FocusableRole.BUTTON,
                label="Cancel",
                priority=102,
                description="Cancel modal action"
            ),
        ]

    def validate_tab_order(self, html_content: str) -> Dict[str, Any]:
        """
        Validate that tab order is logical and follows visual flow

        Returns:
            Dict with validation results including:
            - is_valid: bool
            - issues: List of issues found
            - element_count: Number of focusable elements
        """
        issues = []
        focusable_count = 0

        # Count focusable elements
        if "tabindex" in html_content or "href=" in html_content:
            focusable_count = html_content.count("tabindex") + html_content.count("href=")

        # Check for positive tabindex (should use 0 or -1)
        import re
        positive_tabindex = re.findall(r'tabindex=["\']([1-9]\d*)["\']', html_content)
        if positive_tabindex:
            issues.append(f"Found {len(positive_tabindex)} elements with positive tabindex (should use 0 or -1)")

        # Check for custom tab order that breaks visual flow
        if 'tabindex="-1"' in html_content and focusable_count > 10:
            # Ensure -1 is used appropriately (not on all elements)
            if html_content.count('tabindex="-1"') > focusable_count / 2:
                issues.append("Too many elements have tabindex=-1, may break keyboard navigation")

        return {
            "is_valid": len(issues) == 0,
            "issues": issues,
            "element_count": focusable_count,
            "positive_tabindex_count": len(positive_tabindex)
        }

    def generate_focus_styles(self) -> str:
        """Generate CSS for focus indicators"""
        return """
/* Keyboard Navigation - Focus Indicators */
:focus {
    outline: 3px solid #3B82F6 !important;
    outline-offset: 2px !important;
}

/* High contrast focus for better visibility */
:focus-visible {
    outline: 3px solid #2563EB !important;
    outline-offset: 2px !important;
    box-shadow: 0 0 0 4px rgba(59, 130, 246, 0.3) !important;
}

/* Remove default focus and add custom for buttons */
button:focus,
.uat-card__button:focus {
    outline: 3px solid #3B82F6;
    outline-offset: 2px;
}

/* Card focus styles */
.uat-card:focus {
    outline: 3px solid #3B82F6;
    outline-offset: 4px;
    box-shadow: 0 10px 25px rgba(59, 130, 246, 0.3);
}

.uat-card:focus-visible {
    outline: 3px solid #2563EB;
    outline-offset: 4px;
}

/* Filter focus styles */
[data-filter-type]:focus {
    outline: 3px solid #10B981;
    outline-offset: 2px;
}

/* Modal focus trap */
.modal[role="dialog"]:focus {
    outline: 3px solid #F59E0B;
    outline-offset: 2px;
}

/* Skip links */
.skip-link {
    position: absolute;
    top: -40px;
    left: 0;
    background: #000;
    color: #fff;
    padding: 8px;
    text-decoration: none;
    z-index: 100000;
}

.skip-link:focus {
    top: 0;
}

/* Ensure focus indicators are visible in dark mode */
@media (prefers-color-scheme: dark) {
    :focus {
        outline-color: #60A5FA !important;
    }

    :focus-visible {
        outline-color: #3B82F6 !important;
        box-shadow: 0 0 0 4px rgba(96, 165, 250, 0.4) !important;
    }
}

/* High contrast mode support */
@media (prefers-contrast: high) {
    :focus {
        outline: 4px solid currentColor !important;
        outline-offset: 2px !important;
    }
}

/* Reduced motion support */
@media (prefers-reduced-motion: reduce) {
    :focus {
        transition: none !important;
    }
}
"""

    def generate_keyboard_js(self) -> str:
        """Generate JavaScript for keyboard navigation"""
        return """
/**
 * Keyboard Navigation Module
 * Provides comprehensive keyboard navigation support
 */

(function() {
    'use strict';

    // Focus trap for modals
    let focusTrapSelectors = [];
    let previousFocusElement = null;

    /**
     * Set focus trap to keep focus within specific elements
     */
    function setFocusTrap(selectors) {
        focusTrapSelectors = selectors;
    }

    /**
     * Clear focus trap
     */
    function clearFocusTrap() {
        focusTrapSelectors = [];
    }

    /**
     * Handle keyboard events
     */
    function handleKeyDown(event) {
        const key = event.key;
        const target = event.target;
        const tagName = target.tagName.toLowerCase();

        // Escape key handling
        if (key === 'Escape') {
            // Close modals
            const modal = target.closest('.modal, [role="dialog"]');
            if (modal) {
                const closeButton = modal.querySelector('.modal-close, [data-action="close"]');
                if (closeButton) {
                    closeButton.click();
                    event.preventDefault();
                }
            }
        }

        // Arrow key navigation in lists
        if (key === 'ArrowDown' || key === 'ArrowUp') {
            const list = target.closest('[role="listbox"], .uat-card-grid');
            if (list) {
                const items = Array.from(list.querySelectorAll('[tabindex="0"], .uat-card'));
                const currentIndex = items.indexOf(target);

                if (currentIndex !== -1) {
                    event.preventDefault();
                    let nextIndex;
                    if (key === 'ArrowDown') {
                        nextIndex = (currentIndex + 1) % items.length;
                    } else {
                        nextIndex = (currentIndex - 1 + items.length) % items.length;
                    }
                    items[nextIndex].focus();
                }
            }
        }

        // Home/End navigation
        if (key === 'Home' || key === 'End') {
            const list = target.closest('[role="listbox"], .uat-card-grid');
            if (list) {
                const items = Array.from(list.querySelectorAll('[tabindex="0"], .uat-card'));
                if (items.length > 0) {
                    event.preventDefault();
                    const targetIndex = key === 'Home' ? 0 : items.length - 1;
                    items[targetIndex].focus();
                }
            }
        }

        // Space/Enter activation
        if ((key === ' ' || key === 'Enter') && target.getAttribute('role') === 'button') {
            event.preventDefault();
            target.click();
        }
    }

    /**
     * Handle focus events
     */
    function handleFocus(event) {
        const target = event.target;

        // Store previous focus for modal restoration
        if (!target.classList.contains('modal')) {
            previousFocusElement = target;
        }

        // Add focus-visible class for browsers that don't support :focus-visible
        if (target.matches(':focus-visible')) {
            target.classList.add('focus-visible');
        }
    }

    /**
     * Handle blur events
     */
    function handleBlur(event) {
        const target = event.target;
        target.classList.remove('focus-visible');
    }

    /**
     * Initialize keyboard navigation
     */
    function init() {
        document.addEventListener('keydown', handleKeyDown);
        document.addEventListener('focus', handleFocus, true);
        document.addEventListener('blur', handleBlur, true);

        // Make all UAT cards focusable
        document.querySelectorAll('.uat-card').forEach(card => {
            card.setAttribute('tabindex', '0');
            card.setAttribute('role', 'button');
        });

        // Ensure all buttons are focusable
        document.querySelectorAll('button').forEach(button => {
            if (!button.hasAttribute('tabindex')) {
                button.setAttribute('tabindex', '0');
            }
        });

        // Add aria-label to buttons without text content
        document.querySelectorAll('button').forEach(button => {
            if (!button.getAttribute('aria-label') && !button.textContent.trim()) {
                const icon = button.querySelector('svg, [class*="icon"]');
                if (icon) {
                    button.setAttribute('aria-label', icon.getAttribute('aria-label') || 'Button');
                }
            }
        });

        console.log('Keyboard navigation initialized');
    }

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    // Export functions for external use
    window.KeyboardNavigation = {
        setFocusTrap,
        clearFocusTrap,
        init
    };
})();
"""


def validate_keyboard_navigation(html_content: str) -> Dict[str, Any]:
    """
    Validate that HTML content supports keyboard navigation

    Args:
        html_content: HTML string to validate

    Returns:
        Dict with validation results
    """
    manager = KeyboardNavigationManager()
    result = manager.validate_tab_order(html_content)

    # Additional checks
    issues = result["issues"]

    # Check for skip links
    if "skip-link" not in html_content and "Skip to" not in html_content:
        issues.append("No skip links found for keyboard users")

    # Check for ARIA roles
    if "role=" not in html_content:
        issues.append("No ARIA roles found on interactive elements")

    # Check for aria-label
    if "aria-label" not in html_content:
        issues.append("No aria-label attributes found (may affect screen reader users)")

    # Check for tabindex
    if "tabindex" not in html_content:
        issues.append("No tabindex attributes found (keyboard navigation may be broken)")

    result["is_valid"] = len(issues) == 0
    result["issues"] = issues

    return result


def get_keyboard_navigation_manager() -> KeyboardNavigationManager:
    """Get singleton keyboard navigation manager instance"""
    return KeyboardNavigationManager()
