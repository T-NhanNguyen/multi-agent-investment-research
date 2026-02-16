# ABOUTME: Stateless utility for pruning LLM agent outputs before inter-agent handoffs.
# ABOUTME: Strips thinking preambles, workflow markers, and excessive decorative bloat.

import re
import logging

logger = logging.getLogger("OutputPruner")

def pruneAgentOutput(rawOutput: str, maxChars: int = 0, agentType: str = "general") -> str:
    """
    Cleans raw agent output for context efficiency.
    Target: Remove 'thinking' noise while preserving substantive findings/data.
    """
    if not rawOutput:
        return ""

    # 0. Strip <thought> or similar reasoning blocks
    rawOutput = re.sub(r'<thought>.*?</thought>', '', rawOutput, flags=re.DOTALL | re.IGNORECASE)
    rawOutput = re.sub(r'```thought.*?```', '', rawOutput, flags=re.DOTALL | re.IGNORECASE)

    lines = rawOutput.splitlines()
    pruned_lines = []
    
    # Heuristic patterns for thinking preamble and internal noise
    # We avoid complex regex to prevent false positives on substantive headers
    preamble_patterns = [
        "i'll conduct", "i'll start by", "i'll follow", "i'll use",
        "let me analyze", "let me check", "let me start", "let me look",
        "i need to", "i will", "here's my approach", "here is my approach",
        "i'm thinking", "i am thinking", "first, i'll", "first, i will"
    ]
    
    workflow_patterns = [
        "## phase", "## step", "### phase", "### step"
    ]
    
    # Standalone separator: a line that is ONLY dashes (e.g. "---", "-----")
    separator_re = re.compile(r'^-{2,}$')

    for line in lines:
        stripped = line.strip().lower()
        if not stripped:
            pruned_lines.append(line)
            continue
            
        # 1. Strip thinking preamble (case-insensitive start-of-line matches)
        is_preamble = any(stripped.startswith(p) for p in preamble_patterns)
        if is_preamble and len(stripped) < 200: # Avoid stripping long substantive paragraphs
            continue
            
        # 2. Strip workflow metadata (headers that are just markers)
        # We only strip if the line is JUST the marker (e.g. "## Phase 1:")
        is_workflow = any(stripped.startswith(p) for p in workflow_patterns)
        if is_workflow and (":" in stripped or len(stripped) < 15):
            continue

        # 3. Strip standalone separator lines (e.g. "---", "-----")
        if separator_re.match(stripped):
            continue

        pruned_lines.append(line)

    # Convert back to string
    content = "\n".join(pruned_lines)

    # 3. Collapse whitespace and decorative separators
    # Collapse 3+ newlines to 2
    content = re.sub(r'\n{3,}', '\n\n', content)
    
    # Balance separators: Reduce excessive --- runs (e.g. 10 dashes to 3)
    # This preserves structure but reduces character bloat
    content = re.sub(r'-{5,}', '---', content)

    # 4. Optional Truncation (Preserve head and tail)
    if maxChars > 0 and len(content) > maxChars:
        half = maxChars // 2
        content = content[:half] + f"\n\n[... {len(content) - maxChars} chars truncated for context efficiency ...]\n\n" + content[-half:]

    return content.strip()

if __name__ == "__main__":
    # Quick self-test
    sample = """I'll conduct a quick analysis.
## Phase 1: Search
RKLB is a space company.

---
---
---

## Step 1: Finish
It has NASA contracts.


Many more lines..."""
    print(f"Original length: {len(sample)}")
    pruned = pruneAgentOutput(sample)
    print("--- PRUNED ---")
    print(pruned)
    print(f"Pruned length: {len(pruned)}")
