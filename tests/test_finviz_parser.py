import os
import re
import json

def parse_finviz_markdown(markdown_content: str) -> dict:
    """
    Parses the cleaned Finviz markdown into a structured JSON-like dictionary.
    """
    data = {
        "ticker": "",
        "company_name": "",
        "website": "",
        "fundamentals": {},
        "analyst_ratings": [],
        "recent_headlines": [],
        "institutional_ownership": []
    }
    
    lines = markdown_content.splitlines()
    current_section = "header"
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # Ticker Identification
        if line.startswith("# "):
            data["ticker"] = line.replace("# ", "").strip()
            continue
            
        # Company Name & Website
        if line.startswith("## ") and not line.startswith("## Analyst Ratings") and not line.startswith("## Recent Headlines"):
            m = re.search(r'\[\s*(.*?)\s*\]\((.*?)\)', line)
            if m:
                data["company_name"] = m.group(1).strip()
                data["website"] = m.group(2).strip()
            continue
            
        # Section Transitions
        if line == "## Analyst Ratings":
            current_section = "analyst_ratings"
            continue
        elif line == "## Recent Headlines":
            current_section = "recent_headlines"
            pass # Stay in section, wait for next lines
            
        elif line == "#### Institutional Ownership":
            current_section = "institutional_ownership"
            continue
            
        elif line.startswith("Index|") or "Market Cap|" in line:
            current_section = "fundamentals"
            
        # Parse Fundamentals Table
        if current_section == "fundamentals":
            if line.startswith("---"):
                continue
            if line == "## Analyst Ratings":
                current_section = "analyst_ratings"
                continue
            # Handle Peer List
            if line.startswith("Peers:"):
                # "Peers: LI XPEV NIO RIVN LCID TM HMC GM STLA F"
                peers_raw = line.replace("Peers:", "").strip()
                data["fundamentals"]["Peers"] = [p.strip() for p in peers_raw.split() if p.strip()]
                continue
                
            # Parse Key-Value grids
            if "|" in line:
                parts = [p.strip() for p in line.split("|")]
                for i in range(0, len(parts)-1, 2):
                    key = parts[i]
                    val = parts[i+1]
                    # Clean up bold markdown (**Value**) and link formatting
                    val = val.replace("**", "").replace("[", "").replace("]", "").strip()
                    val = re.sub(r'\(quote\.ashx[^\)]+\)', '', val).strip() # Remove raw URL paths from cells
                    if key and val:
                        data["fundamentals"][key] = val
                        
        # Parse Analyst Ratings
        elif current_section == "analyst_ratings":
            if line.startswith("---") or line.startswith("| Date"):
                continue
            if line == "## Recent Headlines":
                current_section = "recent_headlines"
                continue
            parts = [p.strip() for p in line.split("|")]
            # Handle potential leading pipe empty element
            if parts and parts[0] == "":
                parts = parts[1:]
            if len(parts) >= 5:
                data["analyst_ratings"].append({
                    "date": parts[0],
                    "action": parts[1],
                    "analyst": parts[2],
                    "rating_change": parts[3].replace(" → ", " to ").replace("→", "to"),
                    "price_target_change": parts[4].replace(" → ", " to ").replace("→", "to")
                })
                
        # Parse Headlines
        elif current_section == "recent_headlines":
            if line.startswith("---"):
                continue
            if line == "#### Institutional Ownership":
                current_section = "institutional_ownership"
                continue
                
            # Extract links and sources
            # Example: 09:51PM | [Tesla cuts price...](url) (Reuters)
            m = re.search(r'\[(.*?)\]\((.*?)\)\s*\((.*?)\)', line)
            if m:
                time_match = re.search(r'(\d{2}:\d{2}[AMP]+)', line)
                date_match = re.search(r'([A-Z][a-z]{2}-\d{2}-\d{2})', line)
                data["recent_headlines"].append({
                    "publish_time": time_match.group(1) if time_match else "",
                    "publish_date": date_match.group(1) if date_match else "Recent",
                    "title": m.group(1).strip(),
                    "url": m.group(2).strip(),
                    "source": m.group(3).strip()
                })
                
        # Parse Institutional Ownership
        elif current_section == "institutional_ownership":
            if line.startswith("---") or "ManagersFunds" in line:
                continue
            parts = [p.strip() for p in line.split("|")]
            if parts and parts[0] == "":
                parts = parts[1:]
            if len(parts) >= 2 and parts[0] != "":
               data["institutional_ownership"].append({
                   "entity": parts[0],
                   "ownership": parts[1]
               })

    return data

def main():
    input_file = "finviz_test_output_tsla_pruned.md"
    output_file = "finviz_test_output_tsla_parsed.json"
    
    if not os.path.exists(input_file):
        print(f"Error: {input_file} not found. Run pruning script first.")
        return
        
    with open(input_file, "r", encoding="utf-8") as f:
        markdown_content = f.read()
        
    print("Parsing structure...")
    parsed_data = parse_finviz_markdown(markdown_content)
    
    # Save structured JSON
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(parsed_data, f, indent=4)
        
    print(f"Successfully serialized data for {parsed_data.get('ticker')}")
    print(f"Fundamentals tracked: {len(parsed_data['fundamentals'])}")
    print(f"Analyst Ratings: {len(parsed_data['analyst_ratings'])}")
    print(f"Recent Headlines: {len(parsed_data['recent_headlines'])}")
    print(f"Institutional Ownership Entities: {len(parsed_data['institutional_ownership'])}")
    print(f"\nSaved structured output to: {output_file}")

if __name__ == "__main__":
    main()
