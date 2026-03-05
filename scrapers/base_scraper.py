# ABOUTME: Generalized base scraper using Crawl4AI Docker service for high-fidelity extraction.

import asyncio
import logging
import httpx
from typing import Dict, Any, Optional
import internal_configs as cfg

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class Crawl4AiBaseScraper:
    """
    Generalized base scraper for extracting high-signal data using Crawl4AI.
    Handles the asynchronous polling and connection logic.
    """

    def __init__(self, baseUrl: Optional[str] = None):
        self.baseUrl = (baseUrl or cfg.config.CRAWL4AI_BASE_URL).rstrip('/')
        self.apiToken = cfg.config.CRAWL4AI_API_TOKEN
        logger.info(f"{self.__class__.__name__} initialized with Crawl4AI at: {self.baseUrl}")

    async def scrape_url(
        self, 
        url: str, 
        js_code: Optional[list] = None, 
        wait_for: Optional[str] = None,
        magic: bool = True
    ) -> Dict[str, Any]:
        """
        Submits a URL to Crawl4AI, polls until completion, and returns the parsed result.
        Subclasses should use this to retrieve the generic scraped dictionary structure.
        """
        logger.info(f"{self.__class__.__name__}: Initiating scrape for -> {url}")
        
        payload = {
            "urls": [url],
            "browser_config": {
                "headless": True,
                "text_mode": False
            },
            "crawler_config": {
                "js_code": js_code or [],
                "wait_for": wait_for or "",
                "magic": magic,
                "simulate_user": True,
                "override_navigator": True
            }
        }
        
        headers = {}
        if self.apiToken:
            headers["Authorization"] = f"Bearer {self.apiToken}"
            
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                submitResp = await client.post(f"{self.baseUrl}/crawl", json=payload, headers=headers)
                submitResp.raise_for_status()
                submitResult = submitResp.json()
                
                taskId = submitResult.get("task_id")
                if not taskId:
                    return self._extractFromResult(url, submitResult)
                
                logger.info(f"{self.__class__.__name__}: Task queued {taskId}, polling for result...")
                MAX_POLL_ATTEMPTS = 30
                POLL_INTERVAL_SECONDS = 3
                
                for attempt in range(MAX_POLL_ATTEMPTS):
                    await asyncio.sleep(POLL_INTERVAL_SECONDS)
                    taskResp = await client.get(f"{self.baseUrl}/task/{taskId}", headers=headers)
                    taskResp.raise_for_status()
                    taskResult = taskResp.json()
                    
                    status = taskResult.get("status")
                    if status == "completed":
                        return self._extractFromResult(url, taskResult)
                    elif status == "failed":
                        error = taskResult.get("error", "Unknown task failure")
                        return {"success": False, "error": error}
                
                return {"success": False, "error": "Timed out waiting for crawl task"}
                    
        except Exception as exc:
            logger.error(f"{self.__class__.__name__}: error for {url}: {exc}")
            return {"success": False, "error": str(exc)}

    def _extractFromResult(self, url: str, result: Dict) -> Dict[str, Any]:
        """Extracts markdown, prunes it, and parses it into a unified dictionary."""
        resultData = result.get("result") or result
        scrapeResults = resultData.get("results", []) or ([resultData] if resultData.get("markdown") else [])
        
        if not scrapeResults:
            logger.warning(f"No scrape results found. resultData snippet: {str(resultData)[:500]}")
            return {"success": False, "error": "No results in response"}
        
        res = scrapeResults[0]
        markdownData = res.get('markdown', '')
        
        if isinstance(markdownData, dict):
            raw_content = markdownData.get('fit_markdown') or markdownData.get('raw_markdown') or ""
        else:
            raw_content = str(markdownData)
        
        pruned_md = self._pruneContent(raw_content)
        structured_data = self._parseToDict(pruned_md)
        
        return {
            "success": True,
            "url": url,
            "data": structured_data,
            "metadata": res.get('metadata', {})
        }

    def _pruneContent(self, content: str) -> str:
        """Surgically removes noise from markdown content. Override in subclass."""
        return content

    def _parseToDict(self, content: str) -> Dict[str, Any]:
        """Parses the cleaned markdown into a structured data dictionary. Override in subclass."""
        return {"raw_markdown": content}

    async def scrapeTicker(self, ticker: str) -> Dict[str, Any]:
        """
        Wrapper to handle ticker-specific scrapes.
        Must be implemented by subclasses.
        """
        raise NotImplementedError("Subclasses must implement scrapeTicker")
