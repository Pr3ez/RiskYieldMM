from __future__ import annotations

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = PROJECT_ROOT / "Risk_Yield_Meta_Model_Analyst_0_0_1" / "web"
INDEX_HTML = WEB_ROOT / "index.html"
APP_JS = WEB_ROOT / "app.js"
STYLES_CSS = WEB_ROOT / "styles.css"


def _javascript_function(source: str, name: str) -> str:
    match = re.search(
        rf"(?:async\s+)?function\s+{re.escape(name)}\s*\([^)]*\)\s*{{", source
    )
    if match is None:
        raise AssertionError(f"JavaScript function {name!r} was not found")
    opening_brace = match.end() - 1
    depth = 0
    for position in range(opening_brace, len(source)):
        token = source[position]
        if token == "{":
            depth += 1
        elif token == "}":
            depth -= 1
            if depth == 0:
                return source[match.start() : position + 1]
    raise AssertionError(f"JavaScript function {name!r} is not balanced")


def test_decision_pipeline_has_safe_professional_information_order() -> None:
    html = INDEX_HTML.read_text(encoding="utf-8")
    card_ids = [
        "decision-card-feed",
        "decision-card-readiness",
        "decision-card-agreement",
        "decision-card-context",
        "decision-card-execution",
        "decision-card-replay",
        "decision-card-paper",
    ]

    positions = [html.index(f'id="{card_id}"') for card_id in card_ids]
    required_ids = {
        "decision-workbench",
        "decision-mode-badge",
        *card_ids,
        "decision-feed-state",
        "decision-feed-detail",
        "decision-readiness-state",
        "decision-readiness-detail",
        "decision-agreement-state",
        "decision-agreement-detail",
        "decision-context-state",
        "decision-context-detail",
        "decision-execution-state",
        "decision-execution-detail",
        "decision-replay-state",
        "decision-replay-detail",
        "decision-paper-state",
        "decision-paper-detail",
        "market-context-details",
        "mtf-context-details",
    }
    html_ids = set(re.findall(r'\bid="([^"]+)"', html))
    assert positions == sorted(positions)
    assert required_ids <= html_ids
    assert "diagnostics never guarantee a trade or profit" in html
    assert "real orders are disabled" in html
    assert (
        'id="decision-card-execution" class="decision-card" data-tone="neutral"' in html
    )


def test_decision_pipeline_requires_frozen_policy_and_separates_evidence_vintages() -> (
    None
):
    source = APP_JS.read_text(encoding="utf-8")
    renderer = _javascript_function(source, "renderDecisionSupport")
    feed = _javascript_function(source, "decisionFeedAssessment")
    agreement = _javascript_function(source, "diagnosticDirectionAgreement")
    replay = _javascript_function(source, "decisionReplayAssessment")
    paper = _javascript_function(source, "decisionPaperAssessment")

    assert "policy.policy_frozen === true" in renderer
    assert "const readiness = frozenPolicy && blockers.length === 0" in renderer
    assert '"No trade · blocked"' in renderer
    assert '"No trade · insufficient"' in renderer
    assert 'state: "Routing off"' in renderer
    assert (
        "Research only. Next allowed: replay or forward-paper observation." in renderer
    )
    assert 'state: "Stale feed"' in feed
    assert (
        "detail: `${provider} · ${ageText} · wait for a current finalized bar`" in feed
    )
    assert 'tone: "blocked"' in feed
    assert "blocked: true" in feed
    assert '"Historical: not run"' in replay
    assert '"Historical: rejected"' in replay
    assert '"Paper: observe only"' in paper
    assert "Buy" not in agreement
    assert "Sell" not in agreement
    assert "entry" in agreement


def test_detailed_context_and_settings_use_progressive_disclosure() -> None:
    html = INDEX_HTML.read_text(encoding="utf-8")
    styles = STYLES_CSS.read_text(encoding="utf-8")

    assert '<details id="market-context-details" class="analysis-details">' in html
    assert '<details id="mtf-context-details" class="analysis-details">' in html
    assert "Market context details" in html
    assert "Cross-timeframe details" in html
    assert "Direction & regime diagnostics" in html
    assert "Context & risk diagnostics" in html
    assert ".decision-pipeline" in styles
    assert "grid-auto-flow: column" in styles
    assert "overflow-x: auto" in styles
    assert ".analysis-details > summary" in styles
