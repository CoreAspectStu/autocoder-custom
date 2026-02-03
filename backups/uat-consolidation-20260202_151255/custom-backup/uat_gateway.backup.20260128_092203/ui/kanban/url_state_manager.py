"""
URL State Manager for Kanban Results Modal

This module provides URL-based state management for sharing filtered views.
Users can copy a URL with their current filters applied and share it with others.

Feature #287: Shareable URLs include all context
"""

from typing import Optional, Dict, Any
from urllib.parse import urlencode, urlparse, parse_qs
from dataclasses import dataclass


@dataclass
class URLState:
    """Represents the complete UI state that can be shared via URL"""
    status: str = "all"  # all, passed, failed
    search: str = ""  # search term
    journey_id: Optional[str] = None  # journey filter
    modal_open: bool = False  # whether results modal is open

    def to_query_params(self) -> Dict[str, str]:
        """
        Convert state to URL query parameters

        Returns:
            Dictionary of query parameters
        """
        params = {}

        if self.status != "all":
            params["status"] = self.status

        if self.search:
            params["search"] = self.search

        if self.journey_id:
            params["journey"] = self.journey_id

        if self.modal_open:
            params["modal"] = "true"

        return params

    def to_url_fragment(self) -> str:
        """
        Convert state to URL fragment (hash)

        Uses fragment instead of query params to avoid page reload on state change

        Returns:
            URL fragment string (without #)
        """
        params = self.to_query_params()
        if not params:
            return ""

        return urlencode(params)

    @classmethod
    def from_url_fragment(cls, fragment: str) -> 'URLState':
        """
        Parse URL fragment to create URLState

        Args:
            fragment: URL fragment (without #)

        Returns:
            URLState object with parsed values
        """
        if not fragment:
            return cls()

        params = parse_qs(fragment)

        # parse_qs returns lists, take first value
        status = params.get("status", ["all"])[0]
        search = params.get("search", [""])[0]
        journey_id = params.get("journey", [None])[0]
        modal_open = params.get("modal", ["false"])[0].lower() == "true"

        return cls(
            status=status,
            search=search,
            journey_id=journey_id,
            modal_open=modal_open
        )

    def is_default(self) -> bool:
        """
        Check if this is the default state (no filters applied)

        Returns:
            True if state matches defaults
        """
        return (
            self.status == "all" and
            not self.search and
            not self.journey_id and
            not self.modal_open
        )


class URLStateManager:
    """
    Manages URL state for shareable filtered views

    Features:
    - Track current filter state (status, search, journey)
    - Update URL when filters change
    - Read URL on page load to restore state
    - Generate shareable URLs
    - Copy URL to clipboard
    """

    def __init__(self, base_url: str = ""):
        """
        Initialize URL state manager

        Args:
            base_url: Base URL of the application (for generating shareable URLs)
        """
        self.base_url = base_url.rstrip("/")
        self._current_state = URLState()

    def update_state(self, status: str = None, search: str = None,
                     journey_id: str = None, modal_open: bool = None) -> URLState:
        """
        Update the current state

        Args:
            status: New status filter (all/passed/failed)
            search: New search term
            journey_id: New journey filter
            modal_open: Whether modal is open

        Returns:
            Updated URLState object
        """
        if status is not None:
            self._current_state.status = status
        if search is not None:
            self._current_state.search = search
        if journey_id is not None:
            self._current_state.journey_id = journey_id
        if modal_open is not None:
            self._current_state.modal_open = modal_open

        return self._current_state

    def get_current_state(self) -> URLState:
        """
        Get the current state

        Returns:
            Current URLState object
        """
        return self._current_state

    def generate_url(self, full_url: bool = True) -> str:
        """
        Generate shareable URL with current state

        Args:
            full_url: Whether to include base URL (vs just fragment)

        Returns:
            Complete URL with fragment containing current state
        """
        fragment = self._current_state.to_url_fragment()

        if not fragment:
            return self.base_url + "/" if full_url else ""

        if full_url:
            return f"{self.base_url}/#{fragment}"
        else:
            return "#" + fragment

    def get_copy_button_html(self, button_text: str = "Share Filtered View",
                            tooltip: str = "Copy URL to clipboard") -> str:
        """
        Generate HTML for copy URL button

        Args:
            button_text: Text to display on button
            tooltip: Tooltip text

        Returns:
            HTML string for copy button
        """
        current_url = self.generate_url()

        return f"""
        <button
            class="url-share-button"
            data-url="{current_url}"
            aria-label="{tooltip}"
            title="{tooltip}"
            onclick="copyShareableURL()"
        >
            <span class="url-share-button__icon">🔗</span>
            <span class="url-share-button__text">{button_text}</span>
        </button>
        """

    def get_share_html(self) -> str:
        """
        Generate complete HTML for share functionality

        Includes:
        - Current state display
        - Copy URL button
        - Success message (hidden by default)

        Returns:
            HTML string for share section
        """
        current_url = self.generate_url()
        state_summary = self._get_state_summary()

        return f"""
        <div class="url-share-section">
            <div class="url-share-section__header">
                <span class="url-share-section__title">Share This View</span>
                <span class="url-share-section__state">{state_summary}</span>
            </div>
            <div class="url-share-section__url">
                <input
                    type="text"
                    class="url-share-section__input"
                    value="{current_url}"
                    readonly
                    aria-label="Shareable URL"
                />
                <button
                    class="url-share-section__copy-button"
                    onclick="copyShareableURL()"
                    aria-label="Copy URL to clipboard"
                >
                    Copy
                </button>
            </div>
            <div class="url-share-section__success" id="url-copy-success" style="display: none;">
                <span class="url-share-section__success-icon">✓</span>
                <span>URL copied to clipboard!</span>
            </div>
        </div>
        """

    def _get_state_summary(self) -> str:
        """
        Get human-readable summary of current state

        Returns:
            String describing current filters
        """
        parts = []

        if self._current_state.status != "all":
            parts.append(f"{self._current_state.status.title()} tests")

        if self._current_state.search:
            parts.append(f'searching "{self._current_state.search}"')

        if self._current_state.journey_id:
            parts.append(f"journey {self._current_state.journey_id}")

        if not parts:
            return "All tests"

        return " | ".join(parts)

    def get_javascript_code(self) -> str:
        """
        Generate JavaScript code for URL state management

        Returns:
            JavaScript code string
        """
        return """
// URL State Management (Feature #287)

// Update URL when filters change
function updateURLState() {
    const state = getCurrentFilterState();
    const params = new URLSearchParams();

    if (state.status !== 'all') {
        params.set('status', state.status);
    }
    if (state.search) {
        params.set('search', state.search);
    }
    if (state.journeyId) {
        params.set('journey', state.journeyId);
    }
    if (state.modalOpen) {
        params.set('modal', 'true');
    }

    const fragment = params.toString();
    const newURL = fragment ? '#' + fragment : ' ';

    // Update URL without reloading page
    history.pushState(state, '', newURL);
}

// Read URL on page load
function restoreURLState() {
    const fragment = window.location.hash.slice(1); // Remove #

    if (!fragment) {
        return; // No state to restore
    }

    const params = new URLSearchParams(fragment);
    const state = {
        status: params.get('status') || 'all',
        search: params.get('search') || '',
        journeyId: params.get('journey') || null,
        modalOpen: params.get('modal') === 'true'
    };

    // Apply restored state
    applyFilterState(state);
}

// Copy shareable URL to clipboard
function copyShareableURL() {
    const url = window.location.href;

    // Use Clipboard API
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(url).then(() => {
            showCopySuccess();
        }).catch(err => {
            // Fallback for older browsers
            fallbackCopyURL(url);
        });
    } else {
        fallbackCopyURL(url);
    }
}

// Fallback copy method for older browsers
function fallbackCopyURL(url) {
    const input = document.querySelector('.url-share-section__input');
    if (input) {
        input.select();
        input.setSelectionRange(0, 99999); // For mobile devices

        try {
            document.execCommand('copy');
            showCopySuccess();
        } catch (err) {
            console.error('Failed to copy URL:', err);
            alert('Failed to copy URL. Please copy manually from the input field.');
        }
    }
}

// Show success message after copying
function showCopySuccess() {
    const successEl = document.getElementById('url-copy-success');
    if (successEl) {
        successEl.style.display = 'flex';
        setTimeout(() => {
            successEl.style.display = 'none';
        }, 3000);
    }
}

// Get current filter state from UI
function getCurrentFilterState() {
    // These will be implemented by the calling code
    return {
        status: window.currentFilter || 'all',
        search: window.currentSearch || '',
        journeyId: window.currentJourney || null,
        modalOpen: window.isModalOpen || false
    };
}

// Apply filter state to UI
function applyFilterState(state) {
    // Update status filter
    if (state.status && state.status !== 'all') {
        applyStatusFilter(state.status);
    }

    // Update search
    if (state.search) {
        const searchInput = document.querySelector('.results-search__input');
        if (searchInput) {
            searchInput.value = state.search;
            applySearch(state.search);
        }
    }

    // Update journey filter
    if (state.journeyId) {
        applyJourneyFilter(state.journeyId);
    }

    // Open modal if requested
    if (state.modalOpen) {
        openResultsModal();
    }
}

// Listen for browser back/forward buttons
window.addEventListener('popstate', (event) => {
    if (event.state) {
        applyFilterState(event.state);
    } else {
        // No state = default view
        clearAllFilters();
    }
});

// Restore state on page load
document.addEventListener('DOMContentLoaded', () => {
    restoreURLState();
});
"""

    def get_css_styles(self) -> str:
        """
        Get CSS styles for URL state management components

        Returns:
            CSS string
        """
        return """
        /* URL Share Section Styles */
        .url-share-section {
            padding: 16px;
            background: #f8fafc;
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            margin-bottom: 16px;
        }

        .url-share-section__header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 12px;
        }

        .url-share-section__title {
            font-size: 14px;
            font-weight: 600;
            color: #1e293b;
        }

        .url-share-section__state {
            font-size: 12px;
            color: #64748b;
            font-style: italic;
        }

        .url-share-section__url {
            display: flex;
            gap: 8px;
        }

        .url-share-section__input {
            flex: 1;
            padding: 8px 12px;
            border: 1px solid #cbd5e1;
            border-radius: 6px;
            font-size: 13px;
            color: #475569;
            background: white;
            font-family: 'Monaco', 'Menlo', 'Courier New', monospace;
        }

        .url-share-section__input:focus {
            outline: none;
            border-color: #3b82f6;
            box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
        }

        .url-share-section__copy-button {
            padding: 8px 16px;
            background: #3b82f6;
            color: white;
            border: none;
            border-radius: 6px;
            font-size: 13px;
            font-weight: 500;
            cursor: pointer;
            transition: background 0.2s;
            white-space: nowrap;
        }

        .url-share-section__copy-button:hover {
            background: #2563eb;
        }

        .url-share-section__copy-button:active {
            background: #1d4ed8;
        }

        .url-share-section__success {
            display: flex;
            align-items: center;
            gap: 8px;
            margin-top: 12px;
            padding: 8px 12px;
            background: #dcfce7;
            border: 1px solid #86efac;
            border-radius: 6px;
            color: #166534;
            font-size: 13px;
        }

        .url-share-section__success-icon {
            font-size: 16px;
            font-weight: bold;
        }

        /* URL Share Button (inline style) */
        .url-share-button {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 8px 12px;
            background: #f1f5f9;
            border: 1px solid #cbd5e1;
            border-radius: 6px;
            color: #475569;
            font-size: 13px;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s;
        }

        .url-share-button:hover {
            background: #e2e8f0;
            border-color: #94a3b8;
        }

        .url-share-button__icon {
            font-size: 14px;
        }

        .url-share-button__text {
            white-space: nowrap;
        }
        """
