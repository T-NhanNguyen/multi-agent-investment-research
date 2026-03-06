# ABOUTME: Global configuration for Firefox profile and URL templates
# ABOUTME: Centralizes environment variables, browser paths, and URL substitution logic

import os
from pathlib import Path

# Paths
ROOT_DIR = Path(__file__).parents[2].absolute()
FIREFOX_PROFILE_PATH = ROOT_DIR / "scrapers" / "browser_profile" / "firefox"
SCRAPED_DATA_PATH = ROOT_DIR / "scraped_data"

# Browser Settings
HEADLESS_DEFAULT = True # Override for debugging
DISABLE_IMAGES = True

# URL Templates
# Example: GITHUB_ISSUE = "https://github.com/{owner}/{repo}/issues/{id}"
URL_TEMPLATES = {
    "FINVIZ_TICKER": "https://finviz.com/quote.ashx?t={ticker}",
    "SEEKING_ALPHA_TICKER": "https://seekingalpha.com/symbol/{ticker}",
    "ROBINHOOD_TICKER": "https://robinhood.com/stocks/{ticker}",
    "MACRO_CALENDAR": "https://tradingeconomics.com/calendar?importance=high",
    "GITHUB_ISSUE": "https://github.com/{owner}/{repo}/issues/{id}"
}

def get_template(key):
    """
    Returns the URL template for a given key.
    """
    if key not in URL_TEMPLATES:
        raise ValueError(f"URL key '{key}' not found in URL_TEMPLATES configuration.")
    return URL_TEMPLATES[key]
