# Synthesis Writing Style Guide

## Purpose

This guide provides examples and principles for the Final Synthesis Agent to follow when producing the final investment decision document (Mode 3). The goal is to create analysis that is:

- **Punchy and narrative-driven**: Keeps readers engaged
- **Educational**: Accessible to intelligent readers who aren't finance experts
- **Actionable**: Clear entry/exit points and invalidation triggers
- **Falsifiable**: Testable claims, not vague predictions

---

## Core Style Principles

### 1. Short Sentences, Active Voice

❌ **Don't**: "It should be noted that while the company has experienced some challenges, the underlying fundamentals remain relatively strong."

✅ **Do**: "The company hit headwinds. The fundamentals are intact."

### 2. Show, Don't Tell

❌ **Don't**: "Liquidity in the silver market is constrained."

✅ **Do**: "The silver to deliver doesn't exist."

### 3. Explain Mechanisms Inline

❌ **Don't**: "The company benefits from network effects."

✅ **Do**: "Each new seller attracts more buyers, which attracts more sellers. That's the flywheel."

### 4. Use Provocative Hooks

Start sections with unexpected facts or contrarian statements:

- "Sounds like a slap on the wrist. It's not."
- "Everyone's watching earnings. They're looking at the wrong thing."
- "The consensus says growth is slowing. The data says otherwise."

---

## Common Patterns and Templates

### Opening Hook (Executive Summary)

```markdown
## 1. The Executive Summary

[Company] isn't what most people think it is. [One sentence contrarian or clarifying statement].

The trade: [Long/Short] at [price range], targeting [return] within [timeframe]. The edge: [what the market is missing]. The risk: [primary invalidation condition].
```

### The Business Explanation

```markdown
## 2. The Business (Plain English)

Forget the corporate slide deck. Here's what they actually do.

- **The Model**: [How cash enters the building - be specific and concrete]
- **The Competitors**: [Who they're fighting and why it matters]
- **The edge**: [Their competitive advantage in one sentence]

**Jargon Decoder**:

- _[Technical term]_: [Simple definition for newer traders]
```

### Evidence Walkthrough

Use tables for structured data with plain-English explanations:

```markdown
## 3. The Evidence Walkthrough

### Qualitative Evidence (The Narrative)

| Claim                  | Source | What It Means                                          |
| :--------------------- | :----- | :----------------------------------------------------- |
| "Vertical integration" | [QUAL] | They control the full supply chain. Competitors don't. |
| "[Catalyst]"           | [WEB]  | If this happens, stock rerates higher.                 |

### Quantitative Evidence (The Numbers)

| Metric              | Value    | What It Means                                  |
| :------------------ | :------- | :--------------------------------------------- |
| Revenue Growth (3Y) | 45%      | Growing fast. 3X faster than industry average. |
| Free Cash Flow      | $2B      | Generating real cash, not just paper profits.  |
| P/E vs. 5Y Average  | 18 vs 25 | Trading at a discount to its own history.      |

**How to Read This**: The company is growing faster than peers while trading cheaper than normal. Either growth slows, or the stock rerates higher.
```

### The Bear Case

```markdown
## 5. The Bear Case (Why We Could Be Wrong)

We have to look at the other side.

- **The Short Seller's Argument**: [What bears are saying - steel-man their position]
- **Our Rebuttal**: [Why we think they're wrong, or why the risk is priced in]

**Price & Momentum Reality**:

- **Fundamental View**: Based on business quality alone, [BUY/HOLD/SELL].
- **Regime-Aware View**: Accounting for momentum/market rotation, [AGREE / WAIT / FADE THE MOVE].
```

### Action Plan

```markdown
## 7. Action Plan

### Entry

- **Zone**: $XX - $XX
- **Trigger**: Wait for [specific event or price action]

### Position

- **Size**: X% of portfolio (justified by [conviction level + volatility])
- **Scaling**: [All at once / scale in on dips]

### Exit

- **Target**: $XX (+X%)
- **Stop-Loss**: $XX (-X%)
- **Time Limit**: Re-evaluate by [DATE] if thesis hasn't played out

### Thesis Killers (When to Fold)

1. If [specific event], the trade is dead. Exit immediately.
2. If [metric] falls below [threshold], reduce size by half.
```

---

## Sample Article Structure

```markdown
# Investment Decision: $TICKER

## 1. The Executive Summary

[One punchy paragraph: the trade, the edge, the timeframe]

---

## 2. The Business (Plain English)

[What they do, who they compete with, their moat]

**Jargon Decoder**:

- _Term_: Definition

---

## 3. The Evidence Walkthrough

### Qualitative Evidence

[Table with Source tags: [QUAL], [QUANT], [WEB]]

### Quantitative Evidence

[Table with plain-English explanations]

**How to Read This**: [One paragraph synthesis]

---

## 4. Cross-Verification Summary

[Table showing how qualitative claims align with quantitative data]

---

## 5. The Bear Case (Why We Could Be Wrong)

- **The Short Argument**: [Steel-man the opposition]
- **Our Rebuttal**: [Why we disagree or acknowledge the risk]

**Price Reality**:

- Fundamental: [BUY/HOLD/SELL]
- Regime-Aware: [AGREE/WAIT/FADE]

---

## 6. The Thesis

### The Core Bet

[2-3 punchy sentences: direction, timeframe, edge]

### Confidence Level

[HIGH/MEDIUM/LOW] — [why]

---

## 7. Action Plan

[Entry, position sizing, exit, invalidation triggers]

---

## 8. Questions for the Reader

Before acting:

1. Do I understand the business model?
2. What would make me sell immediately?
3. Is there information I wish I had?

---

## 9. Watchlist Items

- [Upcoming catalyst date]
- [Key metric to monitor]
```

---

## Examples and Tone Reference

### Example Hook 1: Provocative Statement

> "Everyone thinks this is a meme stock. They're wrong. This is a supply squeeze with an 18-month runway."

### Example Hook 2: Unexpected Fact

> "The company burns $200M per quarter. That's not the problem. The problem is what they're burning it on."

### Example Hook 3: Contrarian Framing

> "Wall Street says the margins are unsustainable. The data says they're going higher."

---

## Anti-Patterns to Avoid

❌ **Hedge-speak**: "It appears that, potentially, the company may be positioned to possibly benefit from..."
✅ **Direct**: "The company wins if rates stay low."

❌ **Jargon Dump**: "The company's TAM expansion via omnichannel GTM synergies..."
✅ **Explain It**: "They're selling in more places (online + retail). That grows the pie."

❌ **Vague Thesis**: "Long-term value creation potential"
✅ **Falsifiable**: "If revenue grows 30%+ for 2 more years, stock hits $150. If growth drops below 15%, we exit."

---

## Final Checklist Before Publishing

- [ ] Does every claim have a source tag? ([QUAL], [QUANT], [WEB], [SYNTH])
- [ ] Can an intelligent non-expert understand the business model?
- [ ] Is there at least one table with plain-English explanations?
- [ ] Did I present AND rebut the bear case?
- [ ] Are entry/exit levels specific and actionable?
- [ ] Is there a clear invalidation trigger ("sell if X happens")?
- [ ] Did I differentiate fundamental view from momentum/regime view?
- [ ] No jargon without inline definitions?

---

## Remember

The goal isn't to sound smart. The goal is to be useful. Write like you're explaining the trade to a sharp friend over coffee, not like you're publishing in a journal.
