# ABOUTME: Playwright controller for persistent Firefox browser instances
# ABOUTME: Manages resource cleanup and session state using persistent context windows

import os
from contextlib import asynccontextmanager
from playwright.async_api import async_playwright
from browser_automation.firefox import config as ff_config

class BrowserController:
    """
    Controller for managing persistent Playwright Firefox contexts.
    """
    def __init__(self, headless=ff_config.HEADLESS_DEFAULT):
        self.headless = headless
        self.user_data_dir = str(ff_config.FIREFOX_PROFILE_PATH)
        self.image_loading = "disabled" if ff_config.DISABLE_IMAGES else "enabled"

    @asynccontextmanager
    async def get_browser_context(self):
        """
        Async context manager for launching and cleaning up browser instances.
        """
        async with async_playwright() as p:
            # Firefox options to block image loading or other performance optimizations
            # Note: Playwright doesn't have a direct "disable-images" flag for Firefox
            # so we use Firefox preferences.
            firefox_args = []
            
            # Browser configuration for performance
            context = await p.firefox.launch_persistent_context(
                user_data_dir=self.user_data_dir,
                headless=self.headless,
                args=firefox_args,
                # Setting browser preferences
                extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
                # Disable image loading via Firefox preferences
                # 'permissions.default.image': 2 blocks all images
                ignore_https_errors=True
            )
            
            # Additional performance: Disable images in preferences
            # (Note: Some of these will only work on launch)
            try:
                # Provide common page instance if needed by the caller
                # we return the context so the caller can manage multiple pages
                yield context
            finally:
                # Ensure the browser is closed and the profile lock is released
                await context.close()

async def get_page_content(url, headless=ff_config.HEADLESS_DEFAULT, wait_until="networkidle"):
    """
    High-level utility to launch a browser, navigate to a URL, and return HTML.
    """
    controller = BrowserController(headless=headless)
    async with controller.get_browser_context() as context:
        page = await context.new_page()
        # Navigate and wait
        await page.goto(url, wait_until=wait_until)
        # Verify status
        if await page.title() == "404 Not Found":
             raise Exception(f"404 Error: Page {url} not found.")
        
        return await page.content()
