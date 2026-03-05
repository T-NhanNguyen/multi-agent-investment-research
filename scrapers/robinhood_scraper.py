import asyncio
import sys
import json
import os
import re
from typing import Optional, Dict, Any, List
from scrapers.base_scraper import Crawl4AiBaseScraper

class RobinhoodScraper(Crawl4AiBaseScraper):
    """
    Scraper for Robinhood stock profiles.
    """

    def __init__(self, baseUrl: Optional[str] = None):
        super().__init__(baseUrl)
        self._current_ticker = ""

    async def scrapeTicker(self, ticker: str):
        self._current_ticker = ticker.upper().strip()
        url = f"https://robinhood.com/us/en/stocks/{self._current_ticker}/"
        
        # Placeholders for future expanded tab interactions
        js_code = [] 
        wait_for = ""
        
        res = await self.scrape_url(url, js_code=js_code, wait_for=wait_for)
        res["ticker"] = self._current_ticker
        return res

    def _pruneContent(self, content: str) -> str:
        """Surgically isolates relevant stock data and cleans up obvious navigation/footer noise."""
        if not content: return ""
        
        # 1. Terminal Noise (Disclaimer/Footer)
        end_markers = ["All investments involve risks", "Robinhood Financial LLC", "Check the background"]
        for marker in end_markers:
            if marker in content:
                content = content[:content.find(marker)]
                break

        # 2. Header Isolation (Start from 'About' or 'Key Statistics')
        start_markers = [f"## About {self._current_ticker}", f"## {self._current_ticker} Key Statistics", "## About ", "## Key Statistics"]
        for marker in start_markers:
            if marker in content:
                content = content[content.find(marker):]
                break

        return content.strip()

    def _parseToDict(self, content: str) -> Dict[str, Any]:
        """Parses Robinhood markdown into a structured dictionary for the analyst agent."""
        data = {
            "ticker": self._current_ticker,
            "key_statistics": {},
            "stock_snapshot": "",
            "analyst_ratings": {"buy": "", "hold": "", "sell": ""},
            "news": [],
            "correlated_tickers": {
                "people_also_own": [],
                "similar_marketcap": []
            },
            "raw_markdown": content
        }

        lines = content.splitlines()
        current_section = None
        
        for i, line in enumerate(lines):
            line = line.strip()
            if not line: continue

            # Section identification
            if "Key Statistics" in line: current_section = "key_stats"; continue
            if "Stock Snapshot" in line: current_section = "snapshot"; continue
            if "Analyst ratings" in line: current_section = "ratings"; continue
            if "News" in line: current_section = "news"; continue
            if "People also own" in line: current_section = "also_own"; continue
            if "Similar Marketcap" in line: current_section = "similar_cap"; continue

            if current_section == "key_stats":
                # Matches patterns like "Market cap3.91T" or "High today$269.43"
                match = re.search(r'^(.*?)([\$\d\.%BTM]+)$', line)
                if match:
                    key = match.group(1).strip().rstrip("$").strip()
                    val = match.group(2).strip()
                    if key and val and key not in data["key_statistics"]:
                        data["key_statistics"][key] = val
                continue

            elif current_section == "snapshot":
                if line == "See More": continue
                if line.startswith("##") and "Snapshot" not in line:
                    current_section = None
                else:
                    data["stock_snapshot"] += line + "\n"

            elif current_section == "ratings":
                # Helper to find next data line
                def get_next_val(idx):
                    for j in range(idx + 1, len(lines)):
                        l = lines[j].strip()
                        if l: return l
                    return ""
                
                if line == "Buy": data["analyst_ratings"]["buy"] = get_next_val(i)
                elif line == "Hold": data["analyst_ratings"]["hold"] = get_next_val(i)
                elif line == "Sell": data["analyst_ratings"]["sell"] = get_next_val(i)
                
            elif current_section == "news":
                # Matches markdown links: [Source TimeTitle![...](...)](link)
                links = re.findall(r'\[([^\]]+)\]\(([^\)]+)\)', line)
                for text, link in links:
                    if "![" in text: text = text.split("![")[0].strip()
                    news_match = re.search(r'^(\w+(?:\s\w+)?)\s(\d+[hd])(.*)$', text)
                    if news_match:
                        data["news"].append({
                            "source": news_match.group(1).strip(),
                            "time": news_match.group(2).strip(),
                            "title": news_match.group(3).strip(),
                            "url": link
                        })
                    else:
                        data["news"].append({"title": text, "url": link})

            elif current_section == "also_own":
                if line.startswith("##") and "People also own" not in line: 
                    current_section = None; continue
                matches = re.findall(r'\[.*?\]\(/us/en/stocks/([A-Z]+)\)', line)
                for ticker in matches:
                    if ticker not in data["correlated_tickers"]["people_also_own"]:
                        data["correlated_tickers"]["people_also_own"].append(ticker)
                        
            elif current_section == "similar_cap":
                if line.startswith("##") and "Similar Marketcap" not in line:
                    current_section = None; continue
                matches = re.findall(r'\[.*?\]\(/us/en/stocks/([A-Z\.]+)\)', line)
                for ticker in matches:
                    if ticker not in data["correlated_tickers"]["similar_marketcap"]:
                        data["correlated_tickers"]["similar_marketcap"].append(ticker)

        data["stock_snapshot"] = data["stock_snapshot"].strip()
        return data

if __name__ == "__main__":
    async def main():
        if len(sys.argv) < 2:
            print("Usage: python -m scrapers.robinhood_scraper <TICKER>")
            return
            
        ticker = sys.argv[1]
        scraper = RobinhoodScraper()
        print(f"--- Fetching Robinhood Data for {ticker} ---")
        result = await scraper.scrapeTicker(ticker)
        
        if result.get("success"):
            print(f"SUCCESS: Scraped {ticker}")
            data = result["data"]
            
            # Save raw markdown and structured output
            raw_filename = os.path.join(os.path.dirname(__file__), f"robinhood_{ticker}.txt")
            with open(raw_filename, "w", encoding="utf-8") as f:
                f.write(data.get("raw_markdown", ""))
            
            out_filename = os.path.join(os.path.dirname(__file__), f"robinhood_{ticker}_output.json")
            with open(out_filename, "w", encoding="utf-8") as f:
                f.write(json.dumps(data, indent=2))
                
            print(f"Files saved: {raw_filename}, {out_filename}")
            
            print("\n--- Parsed Data (Preview) ---")
            # Print specific fields to verify extraction
            print(f"Key Stats: {list(data.get('key_statistics', {}).keys())}")
            print(f"Analyst Ratings: {data.get('analyst_ratings')}")
            print(f"News Items: {len(data.get('news', []))}")
            print(f"Correlated: {data.get('correlated_tickers')}")
            
            if "--full" in sys.argv:
                print(json.dumps(data, indent=2))
        else:
            print(f"FAILED: {result.get('error')}")

    asyncio.run(main())
