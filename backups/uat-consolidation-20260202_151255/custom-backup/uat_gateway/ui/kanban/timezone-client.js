/**
 * Timezone Client Module for UAT Gateway
 *
 * Handles timezone conversion and display on the frontend
 * Feature #292: Cross-timezone timestamp accuracy
 */

class TimezoneClient {
    constructor(apiBaseUrl = '/api') {
        this.apiBaseUrl = apiBaseUrl;
        this.currentTimezone = null;
        this.cache = new Map();
    }

    /**
     * Get the user's current timezone preference
     */
    async getCurrentTimezone() {
        if (this.currentTimezone) {
            return this.currentTimezone;
        }

        try {
            const response = await fetch(`${this.apiBaseUrl}/timezones/current`);
            if (!response.ok) {
                throw new Error('Failed to fetch timezone');
            }
            const data = await response.json();
            this.currentTimezone = data.timezone;
            return this.currentTimezone;
        } catch (error) {
            console.error('Error fetching timezone:', error);
            return 'UTC'; // Fallback to UTC
        }
    }

    /**
     * Set the user's timezone preference
     */
    async setTimezone(timezoneName) {
        try {
            const response = await fetch(`${this.apiBaseUrl}/timezones/current`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ timezone_name: timezoneName })
            });

            if (!response.ok) {
                throw new Error('Failed to set timezone');
            }

            const data = await response.json();
            this.currentTimezone = data.timezone;
            return data;
        } catch (error) {
            console.error('Error setting timezone:', error);
            throw error;
        }
    }

    /**
     * List all available timezones
     */
    async listTimezones() {
        if (this.cache.has('all_timezones')) {
            return this.cache.get('all_timezones');
        }

        try {
            const response = await fetch(`${this.apiBaseUrl}/timezones`);
            if (!response.ok) {
                throw new Error('Failed to fetch timezones');
            }
            const data = await response.json();
            this.cache.set('all_timezones', data.timezones);
            return data.timezones;
        } catch (error) {
            console.error('Error fetching timezones:', error);
            return [];
        }
    }

    /**
     * Convert a UTC timestamp to the user's timezone
     */
    async convertTimestamp(timestamp, targetTimezone = null) {
        try {
            const response = await fetch(`${this.apiBaseUrl}/timezones/convert`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    timestamp: timestamp,
                    target_timezone: targetTimezone
                })
            });

            if (!response.ok) {
                throw new Error('Failed to convert timestamp');
            }

            const data = await response.json();
            return data.converted;
        } catch (error) {
            console.error('Error converting timestamp:', error);
            return {
                full: timestamp,
                short: timestamp,
                time: timestamp,
                date: timestamp,
                relative: timestamp,
                iso: timestamp
            };
        }
    }

    /**
     * Format a timestamp for display (client-side fallback)
     * Uses JavaScript Intl API when available
     */
    formatTimestampClientSide(isoString, format = 'short') {
        const date = new Date(isoString);
        const timezone = this.currentTimezone || Intl.DateTimeFormat().resolvedOptions().timeZone;

        const options = {
            timeZone: timezone,
            hour12: true
        };

        switch (format) {
            case 'full':
                options.year = 'numeric';
                options.month = 'numeric';
                options.day = 'numeric';
                options.hour = 'numeric';
                options.minute = 'numeric';
                options.second = 'numeric';
                options.timeZoneName = 'short';
                break;
            case 'short':
                options.month = 'short';
                options.day = 'numeric';
                options.hour = 'numeric';
                options.minute = 'numeric';
                options.timeZoneName = 'short';
                break;
            case 'time':
                options.hour = 'numeric';
                options.minute = 'numeric';
                options.timeZoneName = 'short';
                break;
            case 'date':
                options.year = 'numeric';
                options.month = 'short';
                options.day = 'numeric';
                break;
            case 'relative':
                return this.formatRelativeTime(date);
            default:
                options.year = 'numeric';
                options.month = 'short';
                options.day = 'numeric';
                options.hour = 'numeric';
                options.minute = 'numeric';
        }

        return new Intl.DateTimeFormat('en-US', options).format(date);
    }

    /**
     * Format a relative time (e.g., "2 hours ago")
     */
    formatRelativeTime(date) {
        const now = new Date();
        const diffMs = now - date;
        const diffSecs = Math.floor(diffMs / 1000);
        const diffMins = Math.floor(diffSecs / 60);
        const diffHours = Math.floor(diffMins / 60);
        const diffDays = Math.floor(diffHours / 24);

        if (diffSecs < 60) {
            return 'just now';
        } else if (diffMins < 60) {
            return `${diffMins} minute${diffMins > 1 ? 's' : ''} ago`;
        } else if (diffHours < 24) {
            return `${diffHours} hour${diffHours > 1 ? 's' : ''} ago`;
        } else if (diffDays < 7) {
            return `${diffDays} day${diffDays > 1 ? 's' : ''} ago`;
        } else if (diffDays < 30) {
            const weeks = Math.floor(diffDays / 7);
            return `${weeks} week${weeks > 1 ? 's' : ''} ago`;
        } else if (diffDays < 365) {
            const months = Math.floor(diffDays / 30);
            return `${months} month${months > 1 ? 's' : ''} ago`;
        } else {
            const years = Math.floor(diffDays / 365);
            return `${years} year${years > 1 ? 's' : ''} ago`;
        }
    }

    /**
     * Auto-detect user's browser timezone
     */
    detectBrowserTimezone() {
        try {
            return Intl.DateTimeFormat().resolvedOptions().timeZone;
        } catch (e) {
            console.error('Could not detect timezone:', e);
            return 'UTC';
        }
    }

    /**
     * Update all timestamp elements on the page
     */
    async updateTimestampsOnPage() {
        const timezone = await this.getCurrentTimezone();
        const timestamps = document.querySelectorAll('time[data-datetime]');

        for (const timeEl of timestamps) {
            const isoString = timeEl.getAttribute('datetime');
            if (!isoString) continue;

            const displayFormat = timeEl.getAttribute('data-format') || 'short';
            const formatted = await this.convertTimestamp(isoString, timezone);
            const text = formatted[displayFormat] || formatted.short;
            timeEl.textContent = text;
        }
    }
}

// Create global instance
const timezoneClient = new TimezoneClient();

// Auto-initialize: detect and set browser timezone on first visit
async function initTimezone() {
    try {
        const browserTimezone = timezoneClient.detectBrowserTimezone();
        const currentTimezone = await timezoneClient.getCurrentTimezone();

        // Only set if not already set (i.e., still default UTC)
        if (currentTimezone === 'UTC' && browserTimezone !== 'UTC') {
            console.log(`Auto-setting timezone to: ${browserTimezone}`);
            await timezoneClient.setTimezone(browserTimezone);
        }

        // Update timestamps on page
        await timezoneClient.updateTimestampsOnPage();
    } catch (error) {
        console.error('Error initializing timezone:', error);
    }
}

// Initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initTimezone);
} else {
    initTimezone();
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { TimezoneClient, timezoneClient };
}
