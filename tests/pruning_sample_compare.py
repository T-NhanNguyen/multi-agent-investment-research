# ABOUTME: Unit tests for the handoff pruning functionality
# ABOUTME: Validates that agent outputs are correctly pruned for downstream handoffs

import sys
from pathlib import Path

# Fix path to include project root
project_root = str(Path(__file__).parent.parent)
if project_root not in sys.path:
    sys.path.append(project_root)

from internal_configs import prune_for_handoff


def test_short_output_unchanged():
    """Short outputs should pass through unchanged."""
    short_text = "This is a short analysis."
    result = prune_for_handoff(short_text, 'qualitative')
    assert result == short_text


def test_qualitative_section_extraction():
    """Qualitative pruning should extract thesis, risks, catalysts, moat."""
    long_output = """
## Investment Thesis
Tesla is transitioning from a car company to an AI and energy company.
The FSD technology represents a significant moat that competitors cannot easily replicate.

## Key Risks
1. Execution risk on FSD timeline
2. Competition from BYD in China market
3. Margin compression in core auto business

## Catalysts
- FSD v13 release expected Q1 2026
- Energy storage growth exceeding 100% YoY
- Robotaxi pilot launch

## Competitive Moat
Vertical integration, data flywheel from 5M+ vehicles, manufacturing expertise.

## Other Details
Lots of additional context that downstream agents don't need...
""" * 10  # Make it long

    result = prune_for_handoff(long_output, 'qualitative', max_chars=2000)

    # Should contain key sections
    assert '**Core Thesis**' in result or '**Key Risks**' in result
    assert len(result) < len(long_output)
    assert '[Pruned for context efficiency]' in result


def test_quantitative_section_extraction():
    """Quantitative pruning should extract valuation, metrics, technical signals."""
    long_output = """
## Valuation
Fair value estimate: $250-280 based on DCF with 12% discount rate.
Current price implies 20x 2026 earnings.

## Key Financial Metrics
- Revenue growth: 28% YoY
- Gross margin: 18.5%
- Free cash flow: $3.2B TTM

## Technical Signal
Bullish momentum, price above 50 and 200 DMA.
RSI at 58, not overbought.

## Price Target
12-month target: $275
Upside potential: 15%

## Detailed Tables
Lots of data tables and historical comparisons...
""" * 10

    result = prune_for_handoff(long_output, 'quantitative', max_chars=2000)

    assert '**Valuation**' in result or '**Key Metrics**' in result
    assert len(result) < len(long_output)


def test_synthesis_section_extraction():
    """Synthesis pruning should extract recommendation, confidence, action."""
    long_output = """
## Recommendation
BUY with moderate position sizing. The risk-reward is favorable.

## Confidence Level
High confidence (75%) on thesis, medium confidence on timing.

## Action Items
1. Initiate position at current levels
2. Add on pullbacks to $220
3. Review thesis quarterly

## Detailed Rationale
Extended discussion of all the factors...
""" * 10

    result = prune_for_handoff(long_output, 'synthesis', max_chars=2000)

    assert '**Recommendation**' in result or '**Confidence**' in result
    assert len(result) < len(long_output)


def test_fallback_for_unstructured_output():
    """Unstructured outputs should use fallback truncation."""
    unstructured = "A" * 5000  # No recognizable sections

    result = prune_for_handoff(unstructured, 'qualitative', max_chars=2000)

    assert len(result) <= 2100  # Some buffer for the suffix
    assert '[Pruned for context efficiency]' in result


def test_empty_input():
    """Empty inputs should return empty."""
    assert prune_for_handoff("", 'qualitative') == ""
    assert prune_for_handoff(None, 'qualitative') is None


def test_unknown_agent_type_uses_default():
    """Unknown agent types should fall back to qualitative patterns."""
    output = """
## Investment Thesis
This is the thesis content.
"""
    result = prune_for_handoff(output, 'unknown_type', max_chars=2000)
    # Should still work, using qualitative as default
    assert result is not None


if __name__ == "__main__":
    test_short_output_unchanged()
    test_qualitative_section_extraction()
    test_quantitative_section_extraction()
    test_synthesis_section_extraction()
    test_fallback_for_unstructured_output()
    test_empty_input()
    test_unknown_agent_type_uses_default()
    print("All pruning tests passed!")
