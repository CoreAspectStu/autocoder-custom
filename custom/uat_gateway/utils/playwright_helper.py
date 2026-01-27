"""
Playwright Helper - Utility functions for Playwright integration

This module provides helper functions for integrating with Playwright
and third-party tools like axe-core for accessibility testing.
"""

import sys
from pathlib import Path
from typing import List, Optional, Dict, Any

# Add parent directory to path for imports

from uat_gateway.utils.logger import get_logger


def inject_axe(page: Any) -> bool:
    """
    Inject axe-core into a Playwright page

    Args:
        page: Playwright Page object

    Returns:
        True if injection successful, False otherwise
    """
    logger = get_logger(__name__)
    try:
        # Inject axe-core script
        page.evaluate("""
            (function() {
                if (document.querySelector('[data-axe-loaded]')) {
                    return; // Already loaded
                }
                const script = document.createElement('script');
                script.src = 'https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.8.2/axe.min.js';
                script.setAttribute('data-axe-loaded', 'true');
                script.onload = () => {
                    console.log('axe-core loaded');
                };
                document.head.appendChild(script);
            })();
        """)
        logger.info("axe-core injected successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to inject axe-core: {e}")
        return False


def run_axe_scan(
    page: Any,
    include_selectors: Optional[List[str]] = None,
    exclude_selectors: Optional[List[str]] = None,
    wcag_level: str = "AA"
) -> Dict[str, Any]:
    """
    Run accessibility scan using axe-core

    Args:
        page: Playwright Page object
        include_selectors: CSS selectors to include in scan
        exclude_selectors: CSS selectors to exclude from scan
        wcag_level: WCAG compliance level (A, AA, or AAA)

    Returns:
        Axe scan results as dictionary
    """
    logger = get_logger(__name__)

    try:
        # Wait for axe-core to be loaded
        page.wait_for_function("""
            () => {
                return typeof window.axe !== 'undefined';
            }
        """, timeout=10000)

        # Build axe configuration
        axe_config = {
            "runOnly": {
                "type": "tag",
                "values": [f"wcag{wcag_level.lower()}"]
            }
        }

        # Run axe scan
        results = page.evaluate("""
            (config) => {
                return window.axe.run(document, config);
            }
        """, axe_config)

        logger.info(f"axe scan complete: {len(results.get('violations', []))} violations found")
        return results

    except Exception as e:
        logger.error(f"axe scan failed: {e}")
        # Return empty results on failure
        return {
            "violations": [],
            "passes": [],
            "incomplete": [],
            "error": str(e)
        }
