# ABOUTME: Main runner for task orchestration and extraction
# ABOUTME: Integrates URL templating, browser controller, and text sanitization for research tasks

import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

# Add the parent directory to sys.path to import local config
# Add the project root to sys.path
root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if root_dir not in sys.path:
    sys.path.append(root_dir)

from browser_automation.firefox import config as ff_config
from browser_automation.tools import helpers
from browser_automation.core.controller import get_page_content

async def run_scrape(template_key, **kwargs):
    """
    Orchestrates the scraping of a URL template using persistent Firefox.
    Stores the results in a predictable text format.
    """
    # 1. Substitute URL
    template = ff_config.get_template(template_key)
    url = helpers.interpolate_url(template, **kwargs)
    print(f"Starting scrape for: {url}")
    
    # 2. Extract HTML from Browser
    try:
        html = await get_page_content(url, headless=ff_config.HEADLESS_DEFAULT)
        # 3. Clean and Sanitize Content
        clean_text = helpers.sanitize_content(html)
        
        # 4. Data Integrity Check
        if not clean_text or len(clean_text) < 100:
            print(f"Warning: Extracted content for {url} appears empty or potentially blocked.")
            # Trigger "needs re-authentication" alert if needed
            return None
            
        # 5. File System Handoff
        helpers.ensure_directory(ff_config.SCRAPED_DATA_PATH)
        filename = helpers.generate_filename(template_key.lower())
        output_path = ff_config.SCRAPED_DATA_PATH / filename
        
        # Metadata Header
        timestamp = datetime.now().isoformat()
        profile_used = ff_config.FIREFOX_PROFILE_PATH
        header = f"SOURCE: {url}\nTIMESTAMP: {timestamp}\nPROFILE: {profile_used}\n"
        header += "="*30 + "\n\n"
        
        # Save to file
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(header + clean_text)
            
        print(f"Successfully saved results to: {output_path}")
        return output_path
        
    except Exception as e:
        print(f"Error during scrape for {url}: {e}")
        return None

if __name__ == "__main__":
    # Test call
    # python playwright/core/runner.py FINVIZ_TICKER ticker=AAPL
    if len(sys.argv) < 2:
        print("Usage: python playwright/core/runner.py [TEMPLATE_KEY] [KWARGS...]")
        sys.exit(1)
        
    template_key = sys.argv[1]
    kwargs = dict(arg.split('=') for arg in sys.argv[2:])
    
    asyncio.run(run_scrape(template_key, **kwargs))
