# ABOUTME: Unit tests for URL interpolation and content sanitization
# ABOUTME: Verifies helpers for URL templates and HTML cleaning without external dependencies

import unittest
import sys
import os

# Add the project root to sys.path
root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if root_dir not in sys.path:
    sys.path.append(root_dir)

from browser_automation.tools import helpers

class TestPlaywrightHelpers(unittest.TestCase):
    """
    Test suite for the Playwright tool helper functions.
    """
    
    def test_interpolate_url(self):
        """
        Verify that URLs are correctly interpolated with keyword arguments.
        """
        template = "https://github.com/{owner}/{repo}/issues/{id}"
        result = helpers.interpolate_url(template, owner="psf", repo="requests", id="123")
        self.assertEqual(result, "https://github.com/psf/requests/issues/123")
        
        # Test missing key throws ValueError
        with self.assertRaises(ValueError):
            helpers.interpolate_url(template, owner="psf")

    def test_sanitize_content(self):
        """
        Verify that HTML boilerplate is removed but main text is preserved.
        """
        html = """
        <html>
            <head><title>Test Page</title></head>
            <body>
                <header><nav>Home | Login</nav></header>
                <main>
                    <h1>Page Headline</h1>
                    <p>This is the core content that should persist.</p>
                    <script>alert('Blocked');</script>
                    <style>.hidden { display: none; }</style>
                </main>
                <footer>&copy; 2023</footer>
            </body>
        </html>
        """
        clean_text = helpers.sanitize_content(html)
        
        # Check text is cleaner
        self.assertIn("Page Headline", clean_text)
        self.assertIn("This is the core content that should persist.", clean_text)
        
        # Check navigation and scripts are gone
        self.assertNotIn("Home | Login", clean_text)
        self.assertNotIn("alert('Blocked')", clean_text)
        self.assertNotIn("&copy;", clean_text)

if __name__ == "__main__":
    unittest.main()
