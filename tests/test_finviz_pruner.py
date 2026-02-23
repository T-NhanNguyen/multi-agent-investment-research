import re
import os

def prune_content(content: str) -> str:
    """
    Surgically removes noise from Finviz markdown content.
    """
    lines = content.split('\n')
    pruned = []
    
    # Combined regex for the global nav menu and other noise
    NAV_MENU_PATTERN = r"\| \[Home\]\(/\)\| \[News\]\(/news\.ashx\)\| \[Screener\]\(/screener\.ashx\)"
    
    # Pre-compiled regex for stripping markdown links: [text](url) -> text
    LINK_STRIP_RE = re.compile(r"\[([^\]]+)\]\([^\)]+\)")
    
    skip_mode = False
    header_data_collected = False # Flag to start keeping data after the header
    
    for line in lines:
        stripped = line.strip()
        
        # 1. Terminal Noise (Footer)
        if "[Affiliate](/affiliate.ashx)" in line or "Quotes delayed 15 minutes" in line or "[Follow us on X]" in line:
            break
            
        # 2. Block Suppression (Marketing/Ads)
        if "Upgrade your FINVIZ experience" in line:
            skip_mode = True
            continue
            
        if skip_mode:
            # Drop everything until we hit a real data row or next section
            if any(marker in line for marker in ["Total Revenue", "Cost of Goods", "Period End Date"]):
                skip_mode = False
            else:
                continue

        # 3. Aggressive Header/Ad Removal
        if not header_data_collected:
            if line.startswith("# ") or line.startswith("## "):
                pruned.append(line)
                continue
            if "Index|" in line or "Market Cap|" in line:
                header_data_collected = True
            else:
                continue # Skip everything until table

        # 4. Section Header Injection & Link Residue
        if "| Date | Action | Analyst |" in line:
            pruned.append("## Analyst Ratings")
        
        if "[ Show Previous Ratings ]" in line:
            continue # Skip this line
            
        # Check for start of news section to inject header
        if "|  |  Feb-" in line and " (Benzinga)" in line:
             pruned.append("## Recent Headlines")

        # 5. Global Noise & Ad Filtering
        if any(marker in line for marker in ["![](/gfx/nic2x2.gif)", "|  |  [](/)", "gfx/nic2x2.gif"]):
            continue
            
        if re.search(NAV_MENU_PATTERN, line):
            continue

        if stripped == "---" and (not pruned or pruned[-1].strip() == "---"):
            continue

        # 6. Hyperlink Cleaning & Content Polish
        if any(m in line for m in ["Peers:", "Held by:", "Institutional Ownership", "insidertrading/managers"]):
             line = LINK_STRIP_RE.sub(r"\1", line)
             # Extra polish for Peers line
             if "Peers:" in line:
                 line = line.split("Scroll to")[0].strip()
        
        # Stop before the incomplete finance tables
        if "| [Income Statement](#)" in line or "DataYoY Growth YoY Growth" in line:
            break

        pruned.append(line)

    # Final cleanup: remove trailing empty lines or separators
    while pruned and (pruned[-1].strip() == "" or pruned[-1].strip() == "---"):
        pruned.pop()
        
    return '\n'.join(pruned).strip()

def main():
    input_file = "finviz_test_output_tsla.md"
    output_file = "finviz_test_output_tsla_pruned.md"
    
    if not os.path.exists(input_file):
        print(f"Error: {input_file} not found. Run the scraper self-test first.")
        return
        
    with open(input_file, "r", encoding="utf-8") as f:
        original_content = f.read()
        
    print(f"Original: {len(original_content)} chars, {len(original_content.splitlines())} lines.")
    
    pruned_content = prune_content(original_content)
    
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(pruned_content)
        
    print(f"Pruned:   {len(pruned_content)} chars, {len(pruned_content.splitlines())} lines.")
    
    reduction = (1 - (len(pruned_content) / len(original_content))) * 100
    print(f"Reduction: {reduction:.2f}%")
    print(f"\nResult saved to {output_file}")

if __name__ == "__main__":
    main()
