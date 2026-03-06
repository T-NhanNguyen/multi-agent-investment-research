# ABOUTME: Helper functions for URL interpolation, directory validation, and text cleaning
# ABOUTME: Provides centralized utilities for sanitized URL generation and DOM-traversal text extraction

import os
import re
from datetime import datetime
from bs4 import BeautifulSoup

def interpolate_url(template, **kwargs):
    """
    Interpolates a URL template with named keyword arguments.
    Example: GITHUB_ISSUE = "https://github.com/{owner}/{repo}/issues/{id}"
    """
    try:
        return template.format(**kwargs)
    except KeyError as e:
        raise ValueError(f"Missing required URL parameter: {e}")

def sanitize_content(html):
    """
    Removes boilerplate HTML (scripts, styles, navs) using BeautifulSoup.
    Returns cleaned text content.
    """
    if not html:
        return ""
    
    soup = BeautifulSoup(html, "html.parser")
    
    # Remove script and style elements
    for script_or_style in soup(["script", "style", "nav", "footer", "header", "noscript"]):
        script_or_style.decompose()
    
    # Get text
    text = soup.get_text(separator='\n')
    
    # Break into lines and remove leading/trailing whitespace
    lines = (line.strip() for line in text.splitlines())
    
    # Break multi-headlines into a line each
    chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
    
    # Drop blank lines
    text = '\n'.join(chunk for chunk in chunks if chunk)
    
    return text

def ensure_directory(path):
    """
    Ensures a directory exists, creating it if necessary.
    """
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)

def generate_filename(source_name):
    """
    Generates a consistent filename based on source name and timestamp.
    Example: source_name_20231024_153000.txt
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{source_name}_{timestamp}.txt"
