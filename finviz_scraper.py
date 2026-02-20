# ABOUTME: Specialized scraper for Finviz market and stock data.
# ABOUTME: Leverages Crawl4AI Docker service for high-fidelity extraction.

import asyncio
import logging
import httpx
from typing import Dict, List, Any, Optional
import internal_configs as cfg

# Configure logging
logger = logging.getLogger(__name__)

class FinvizScraper:
    """
    Specialized scraper for extracting high-signal financial data from Finviz.
    Uses crawl4ai service to handle complex renderings and extract clean markdown.
    """

    def __init__(self, baseUrl: Optional[str] = None):
        self.baseUrl = (baseUrl or cfg.config.CRAWL4AI_BASE_URL).rstrip('/')
        self.apiToken = cfg.config.CRAWL4AI_API_TOKEN
        logger.info(f"FinvizScraper initialized with Crawl4AI at: {self.baseUrl}")

    async def scrapeTicker(self, ticker: str) -> Dict[str, Any]:
        """
        Scrapes a specific ticker's profile on Finviz.
        Crawl4AI v0.8 uses an async task queue — submits to /crawl then polls /task/{id}.
        Returns a dictionary containing the extracted content or error info.
        """
        ticker = ticker.upper().strip()
        url = f"https://finviz.com/quote.ashx?t={ticker}&ty=c&ta=1&p=d"
        
        logger.info(f"FinvizScraper: Initiating scrape for {ticker} -> {url}")
        
        payload = {
            "urls": [url],
            "browser_config": {"headless": True},
            "crawler_config": {}
        }
        
        headers = {}
        if self.apiToken:
            headers["Authorization"] = f"Bearer {self.apiToken}"
            
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                # Step 1: Submit crawl job
                submitResp = await client.post(f"{self.baseUrl}/crawl", json=payload, headers=headers)
                submitResp.raise_for_status()
                submitResult = submitResp.json()
                logger.debug(f"FinvizScraper submit response for {ticker}: {submitResult}")
                
                taskId = submitResult.get("task_id")
                if not taskId:
                    # Legacy sync response — handle directly
                    return self._extractFromResult(ticker, url, submitResult)
                
                # Step 2: Poll /task/{task_id} until complete
                logger.info(f"FinvizScraper: Task queued {taskId}, polling for result...")
                MAX_POLL_ATTEMPTS = 30
                POLL_INTERVAL_SECONDS = 3
                
                for attempt in range(MAX_POLL_ATTEMPTS):
                    await asyncio.sleep(POLL_INTERVAL_SECONDS)
                    taskResp = await client.get(f"{self.baseUrl}/task/{taskId}", headers=headers)
                    taskResp.raise_for_status()
                    taskResult = taskResp.json()
                    
                    status = taskResult.get("status")
                    logger.debug(f"FinvizScraper: Poll {attempt + 1}/{MAX_POLL_ATTEMPTS} status={status}")
                    
                    if status == "completed":
                        return self._extractFromResult(ticker, url, taskResult)
                    elif status == "failed":
                        error = taskResult.get("error", "Unknown task failure")
                        logger.error(f"FinvizScraper: Task failed for {ticker}: {error}")
                        return {"ticker": ticker, "success": False, "error": error}
                    # status == "pending" or "processing" -> keep polling
                
                return {"ticker": ticker, "success": False, "error": "Timed out waiting for crawl task"}
                    
        except Exception as exc:
            logger.error(f"FinvizScraper: HTTP/Extraction error for {ticker}: {exc}")
            return {"ticker": ticker, "success": False, "error": str(exc)}

    def _extractFromResult(self, ticker: str, url: str, result: Dict) -> Dict[str, Any]:
        """Parse a completed task result (either legacy sync or v0.8 task format)."""
        # v0.8 task result wraps data under 'result'
        resultData = result.get("result") or result
        
        scrapeResults = resultData.get("results", [])
        if not scrapeResults:
            # Some versions return single result at top level
            scrapeResults = [resultData] if resultData.get("markdown") else []
        
        if not scrapeResults:
            logger.error(f"FinvizScraper: No results in task response for {ticker}")
            return {"ticker": ticker, "success": False, "error": "No results in response"}
        
        res = scrapeResults[0]
        markdownData = res.get('markdown', '')
        
        # Prefer fit_markdown (noise-filtered), fall back to raw_markdown
        content = ""
        if isinstance(markdownData, dict):
            content = markdownData.get('fit_markdown') or markdownData.get('raw_markdown') or ""
        elif isinstance(markdownData, str):
            content = markdownData
        
        logger.info(f"FinvizScraper: Successfully scraped {ticker} ({len(content)} chars)")
        
        return {
            "ticker": ticker,
            "success": True,
            "url": url,
            "content": content,
            "metadata": res.get('metadata', {})
        }


if __name__ == "__main__":
    # Quick self-test script
    async def test():
        logging.basicConfig(level=logging.INFO)
        scraper = FinvizScraper() # Uses CRAWL4AI_BASE_URL from config
        data = await scraper.scrapeTicker("TSLA")
        if data["success"]:
            print(f"Scraped {data['ticker']} successfully.")
            print(data["content"][:500])
        else:
            print(f"Failed to scrape {data['ticker']}: {data['error']}")

    asyncio.run(test())
