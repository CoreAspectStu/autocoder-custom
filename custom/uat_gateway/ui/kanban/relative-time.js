/**
 * Relative Time Display - Feature #291
 *
 * Dynamically updates relative timestamps (e.g., "2 hours ago", "just now")
 * and provides hover tooltips with absolute time.
 */

(function() {
    'use strict';

    /**
     * Format a timestamp as relative time
     * Mirrors the Python logic in time_formatter.py
     */
    function formatRelativeTime(timestamp, now) {
        const delta = now - timestamp;
        const seconds = Math.floor(delta / 1000);

        // Less than a minute
        if (seconds < 60) {
            if (seconds < 10) return 'just now';
            return seconds + ' seconds ago';
        }

        // Less than an hour
        const minutes = Math.floor(seconds / 60);
        if (minutes < 60) {
            if (minutes === 1) return '1 minute ago';
            return minutes + ' minutes ago';
        }

        // Less than a day
        const hours = Math.floor(minutes / 60);
        if (hours < 24) {
            if (hours === 1) return '1 hour ago';
            return hours + ' hours ago';
        }

        // Less than a week
        const days = Math.floor(hours / 24);
        if (days < 7) {
            if (days === 1) {
                // Return "yesterday at HH:MM AM/PM"
                const timeStr = timestamp.toLocaleTimeString('en-US', {
                    hour: 'numeric',
                    minute: '2-digit',
                    hour12: true
                });
                return 'yesterday at ' + timeStr;
            }
            return days + ' days ago';
        }

        // Less than a month
        const weeks = Math.floor(days / 7);
        if (weeks < 4) {
            if (weeks === 1) return '1 week ago';
            return weeks + ' weeks ago';
        }

        // Less than a year
        const months = Math.floor(days / 30);
        if (months < 12) {
            if (months === 1) return '1 month ago';
            return months + ' months ago';
        }

        // More than a year
        const years = Math.floor(days / 365);
        if (years === 1) return '1 year ago';
        return years + ' years ago';
    }

    /**
     * Update all relative time elements on the page
     */
    function updateRelativeTimes() {
        const timeElements = document.querySelectorAll('[data-timestamp]');
        const now = new Date();

        timeElements.forEach(function(element) {
            const timestampStr = element.getAttribute('data-timestamp');
            if (!timestampStr) return;

            const timestamp = new Date(timestampStr);

            // Check if date is valid
            if (isNaN(timestamp.getTime())) return;

            const relativeTime = formatRelativeTime(timestamp, now);
            element.textContent = relativeTime;
        });
    }

    /**
     * Initialize relative time updates
     */
    function init() {
        // Initial update
        updateRelativeTimes();

        // Update every minute (60000 ms)
        setInterval(updateRelativeTimes, 60000);

        console.log('Relative time display initialized (Feature #291)');
    }

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    // Also re-initialize when modal is opened (in case content is dynamically loaded)
    window.addEventListener('modalOpened', updateRelativeTimes);

    // Expose function globally for manual updates if needed
    window.updateRelativeTimes = updateRelativeTimes;

})();
