# ABOUTME: Manual authentication utility for persistent Firefox sessions
# ABOUTME: Launches a visible window for logging into various stock market tools and data sources

import asyncio
from playwright.async_api import async_playwright
import os
import sys

# Add the parent directory to sys.path to import local config
# Add the project root to sys.path
root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if root_dir not in sys.path:
    sys.path.append(root_dir)

from browser_automation.firefox import config as ff_config

async def run_login_tool():
    """
    Launches a visible Firefox instance for manual logins and 2FA authentication.
    """
    print(f"Opening Firefox profile at: {ff_config.FIREFOX_PROFILE_PATH}")
    print("--- LOGIN UTILITY ---")
    print("Please perform all necessary logins (e.g., Seeking Alpha, Finviz, GitHub).")
    print("Once complete, simply close the browser window to anchor the session state.")
    
    async with async_playwright() as p:
        # Launch visible Firefox window using persistent context
        context = await p.firefox.launch_persistent_context(
            user_data_dir=str(ff_config.FIREFOX_PROFILE_PATH),
            headless=False, # Must be visible for 2FA/logins
            # Block images to save bandwidth, even in login mode
            # permissions.default.image: 2 = Block all images
        )
        
        # Use the default page that persistent_context opens automatically
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto("https://www.google.com") # Starting point
        
        # We'll just wait for the user to manually close the browser.
        # However, Playwright's launch_persistent_context closes the process once the terminal exits.
        # We can wait for the context to disconnect.
        print("Waiting for you to close the browser...")
        
        # Wait for the browser to be closed by the user
        while True:
            # Check if any page is still open
            if not context.pages:
                break
            await asyncio.sleep(1)
            
        print("Session state anchored. Closing...")
        await context.close()

if __name__ == "__main__":
    asyncio.run(run_login_tool())
