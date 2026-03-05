# ABOUTME: Specialized scraper for Finviz market and stock data.
# ABOUTME: Leverages Crawl4AI Docker service for high-fidelity extraction.

import asyncio
import logging
import re
import json
import sys
from typing import Dict, List, Any, Optional
from scrapers.base_scraper import Crawl4AiBaseScraper

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class FinvizScraper(Crawl4AiBaseScraper):
    """
    Specialized scraper for extracting high-signal financial data from Finviz.
    Uses crawl4ai service to handle complex renderings and extract clean markdown.
    """

    async def scrapeTicker(self, ticker: str) -> Dict[str, Any]:
        """
        Scrapes a specific ticker's profile on Finviz.
        Returns a structured dictionary with fundamentals, news, and ratings.
        """
        ticker = ticker.upper().strip()
        url = f"https://finviz.com/quote.ashx?t={ticker}&ty=c&ta=1&p=d"
        
        res = await self.scrape_url(url)
        res["ticker"] = ticker
        return res

    def _pruneContent(self, content: str) -> str:
        """Surgically removes noise from Finviz markdown content - following test_finviz_pruner.py + fixes."""
        lines = content.splitlines()
        pruned = []
        
        NAV_MENU_PATTERN = r"\| \[Home\]\(/\)\| \[News\]\(/news\.ashx\)\| \[Screener\]\(/screener\.ashx\)"
        LINK_STRIP_RE = re.compile(r"\[([^\]]+)\]\([^\)]+\)")
        
        skip_mode = False
        header_data_collected = False
        
        for line in lines:
            stripped = line.strip()
            if not stripped: continue
            
            # 1. Terminal Noise (Footer) - BREAK HERE
            if any(m in line for m in ["[Affiliate](/affiliate.ashx)", "Quotes delayed 15 minutes", "[Follow us on X]"]):
                break
                
            # 2. Block Suppression (Marketing/Ads)
            if "Upgrade your FINVIZ experience" in line:
                skip_mode = True
                continue
            if skip_mode:
                if any(marker in line for marker in ["Total Revenue", "Cost of Goods", "Period End Date", "| Date | Action |", "| Insider Trading |", "#### Institutional Ownership"]):
                    skip_mode = False
                else: continue

            # 3. Aggressive Header/Ad Removal
            if not header_data_collected:
                if line.startswith("# ") or line.startswith("## "):
                    pruned.append(line)
                    continue
                if "Index|" in line or "Market Cap|" in line:
                    header_data_collected = True
                else: continue

            # 4. Section Header Injection
            if "| Date | Action | Analyst |" in line:
                pruned.append("## Analyst Ratings")
            if "| Insider Trading | Relationship |" in line:
                pruned.append("## Insider Trading")
            
            # News detection - improved to catch "Today" or specific dates without being overly restrictive
            if "|  |  " in line and ("(" in line and ")" in line) and any(m in line for m in ["Today", "AM", "PM", "Jan-", "Feb-", "Mar-"]):
                if not any(p.strip() == "## Recent Headlines" for p in pruned[-10:]):
                    pruned.append("## Recent Headlines")

            if "[ Show Previous Ratings ]" in line: continue
            if any(marker in line for marker in ["![](/gfx/nic2x2.gif)", "|  |  [](/)", "gfx/nic2x2.gif"]): continue
            if re.search(NAV_MENU_PATTERN, line): continue
            if stripped == "---" and (not pruned or pruned[-1].strip() == "---"): continue

            # 5. Hyperlink Cleaning
            if any(m in line for m in ["Peers:", "Held by:", "Institutional Ownership", "insidertrading/managers"]):
                 line = LINK_STRIP_RE.sub(r"\1", line)
                 if "Peers:" in line: line = line.split("Scroll to")[0].strip()
            
            # Don't break at Income Statement if we want Insider Trading which usually comes after in the markdown
            if "| [Income Statement](#)" in line or "DataYoY Growth YoY Growth" in line:
                continue 

            pruned.append(line)
        
        while pruned and (pruned[-1].strip() == "" or pruned[-1].strip() == "---"):
            pruned.pop()
        return "\n".join(pruned).strip()

    def _parseToDict(self, content: str) -> Dict[str, Any]:
        """Parses the cleaned Finviz markdown into a structured data dictionary - following test_finviz_parser.py."""
        data = {
            "ticker": "",
            "company_name": "",
            "website": "",
            "fundamentals": {},
            "analyst_ratings": [],
            "recent_headlines": [],
            "insider_trading": [],
            "institutional_ownership": []
        }
        
        lines = content.splitlines()
        current_section = "header"
        last_headline_date = "Recent"
        
        for line in lines:
            line = line.strip()
            if not line: continue
            
            if line.startswith("# "):
                data["ticker"] = line.replace("# ", "").strip()
                continue
            
            if line.startswith("## ") and not any(s in line for s in ["Analyst Ratings", "Recent Headlines", "Insider Trading"]):
                m = re.search(r'\[\s*(.*?)\s*\]\((.*?)\)', line)
                if m:
                    data["company_name"] = m.group(1).strip()
                    data["website"] = m.group(2).strip()
                continue

            # Section Transitions
            if line == "## Analyst Ratings": current_section = "analyst_ratings"; continue
            if line == "## Recent Headlines": current_section = "recent_headlines"; continue
            if line == "## Insider Trading": current_section = "insider_trading"; continue
            if line == "#### Institutional Ownership": current_section = "institutional_ownership"; continue
            if line.startswith("Index|") or "Market Cap|" in line: current_section = "fundamentals"

            if current_section == "fundamentals":
                if line.startswith("---") or line.startswith("## "): continue
                if line.startswith("Peers:"):
                    peers_raw = line.replace("Peers:", "").strip()
                    data["fundamentals"]["Peers"] = [p.strip() for p in peers_raw.split() if p.strip()]
                    continue
                if "|" in line:
                    parts = [p.strip() for p in line.split("|")]
                    for i in range(0, len(parts)-1, 2):
                        key = parts[i]
                        val = parts[i+1].replace("**", "").replace("[", "").replace("]", "").strip()
                        val = re.sub(r'\(quote\.ashx[^\)]+\)', '', val).strip()
                        if key and val: data["fundamentals"][key] = val
                        
            elif current_section == "analyst_ratings":
                if line.startswith("---") or line.startswith("| Date") or line.startswith("## "): continue
                parts = [p.strip() for p in (line[1:] if line.startswith("|") else line).split("|")]
                if len(parts) >= 5:
                    data["analyst_ratings"].append({
                        "date": parts[0], "action": parts[1], "analyst": parts[2],
                        "rating_change": parts[3].replace("→", "to"),
                        "price_target_change": parts[4].replace(" → ", " to ").replace("→", "to")
                    })
                    
            elif current_section == "recent_headlines":
                if line.startswith("---") or line.startswith("## ") or line.startswith("#### "): continue
                m = re.search(r'\[(.*?)\]\((.*?)\)\s*\((.*?)\)', line)
                if m:
                    # Look for date patterns (e.g., Feb-23-26 or Feb-23)
                    date_m = re.search(r'([A-Z][a-z]{2}-\d{1,2}-\d{2}|[A-Z][a-z]{2}-\d{1,2})', line)
                    # Look for time patterns (e.g., 03:31PM, Today, Recent)
                    time_m = re.search(r'(\d{1,2}:\d{2}[AMPamp]+|Today|Recent)', line)
                    
                    if date_m:
                        last_headline_date = date_m.group(1)
                    elif time_m and time_m.group(1).lower() == "today":
                        last_headline_date = "Today"
                        
                    data["recent_headlines"].append({
                        "publish_time": time_m.group(1) if time_m else "",
                        "publish_date": last_headline_date,
                        "title": m.group(1).strip(), "url": m.group(2).strip(), "source": m.group(3).strip()
                    })

            elif current_section == "insider_trading":
                if line.startswith("---") or "| Insider Trading" in line or line.startswith("## ") or line.startswith("#### "): continue
                parts = [p.strip() for p in line.split("|")]
                if parts and parts[0] == "": parts = parts[1:]
                if len(parts) >= 7:
                    owner_m = re.search(r'\[(.*?)\]', parts[0])
                    data["insider_trading"].append({
                        "owner": owner_m.group(1) if owner_m else parts[0],
                        "relationship": parts[1], "date": parts[2], "transaction": parts[3],
                        "cost": parts[4], "shares": parts[5], "value": parts[6]
                    })
                    
            elif current_section == "institutional_ownership":
                if line.startswith("---") or "ManagersFunds" in line: continue
                parts = [p.strip() for p in line.split("|")]
                if parts and parts[0] == "": parts = parts[1:]
                if len(parts) >= 2 and parts[0] != "":
                   data["institutional_ownership"].append({"entity": parts[0], "ownership": parts[1]})

        return data

if __name__ == "__main__":
    async def main():
        if len(sys.argv) < 2:
            print("Usage: python -m scrapers.finviz_scraper <TICKER> [--full]")
            return
            
        ticker = sys.argv[1]
        show_full = "--full" in sys.argv
        
        scraper = FinvizScraper()
        print(f"--- Fetching Data for {ticker} ---")
        result = await scraper.scrapeTicker(ticker)
        
        if result["success"]:
            data = result["data"]
            print(f"SUCCESS: Scraped {ticker}")
            print(f"Fundamentals: {len(data.get('fundamentals', {}))} keys found")
            print(f"Analyst Ratings: {len(data.get('analyst_ratings', []))} records")
            print(f"Headlines: {len(data.get('recent_headlines', []))} records")
            print(f"Insider Trades: {len(data.get('insider_trading', []))} records")
            
            print("\n--- Sample Headlines (Verifying Date extraction) ---")
            for h in data.get('recent_headlines', [])[:10]:
                print(f"[{h.get('publish_date')} {h.get('publish_time')}] {h.get('title')[:80]}...")
            
            if show_full:
                print("\n--- Full Data JSON ---")
                print(json.dumps(data, indent=2))
        else:
            print(f"FAILED: {result.get('error')}")

    asyncio.run(main())
