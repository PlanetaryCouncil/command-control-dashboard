"""The vendor credit pane must not turn silence into a claim about money.

2026-09-02: grok sat at 100% of its weekly limit -- its own TUI said
"Weekly limit left: 0%" -- while the board's credit pane said "has credit".
Nothing had called grok recently enough to log a refusal, and the pane's
fallback branch rendered "no failures observed" as "has money". Marsita:
"Grok is out credits, vendor dashboard is wrong".
"""
from pathlib import Path

SRC = (Path(__file__).resolve().parent.parent
       / "fleet" / "bin" / "oneview.py").read_text()


def test_a_measured_balance_is_read_before_anything_is_inferred():
    body = SRC.split("function creditState(")[1].split("\n}")[0]
    assert body.index('v.flow === "exhausted"') < body.index("v.plan")


def test_no_reading_is_called_unknown_not_rich():
    body = SRC.split("function creditState(")[1].split("\n}")[0]
    tail = body.rsplit("return", 1)[1]
    assert '"hazy"' in tail, "the fallback must not claim credit"


def test_unknown_is_a_word_the_pane_can_print():
    assert 'hazy:"answer unknown"' in SRC.split("CREDIT_WORD")[1].split("}")[0]
    assert "#credit .st.hazy" in SRC


def test_the_unsure_rows_sort_above_the_sure_ones():
    rank = SRC.split("const rank = ")[1].split(";")[0]
    assert rank.index("hazy") < rank.index("rich")



def test_free_is_not_called_credit():
    """ollama runs on this machine and has never had a bill.
    Marsita: "ollama has credit? It's local..."
    """
    body = SRC.split("function creditState(")[1].split("\n}")[0]
    assert '"free"' in body
    assert "costs nothing" not in body


def test_a_dry_vendor_is_amber_not_red():
    """Marsita, 2026-09-02: "Grok running out of credits is routine, don't
    make it red." Credit runs out on a schedule and comes back on one; the
    fleet routes around it unasked. Red is for what a person must act on."""
    assert "#credit .st.dry{color:var(--warning);}" in SRC
    assert "#credit .st.dry{color:var(--critical);}" not in SRC


def test_a_daemon_that_answers_is_not_absent():
    """The NUC's ollama was serving a model list on 11434 while the pane said
    "absent", because a PATH lookup for the binary failed inside the systemd
    unit's environment and the binary check ran first (2026-09-03)."""
    body = SRC.split("function creditState(")[1].split("\n}")[0]
    assert "v.binary === false && v.ok !== true" in body
    assert "if (v.binary === false)      return" not in body


def test_the_words_explain_themselves():
    """A legend was added unasked and cut the same hour: "I didn't ask for
    legend". The fix was the words, not a paragraph about them -- jargon
    ("DRY") and two different silences both called something vague
    ("absent", "unknown") became plain English."""
    words = SRC.split("CREDIT_WORD")[1].split("}")[0]
    assert '"out of credits"' in words
    assert '"answer unknown"' in words
    assert '"no answer"' in words
    assert '"DRY"' not in words
    assert 'class="legend"' not in SRC
