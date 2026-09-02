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
    assert 'hazy:"unknown"' in SRC.split("CREDIT_WORD")[1].split("}")[0]
    assert "#credit .st.hazy" in SRC


def test_the_unsure_rows_sort_above_the_sure_ones():
    rank = SRC.split("const rank = ")[1].split(";")[0]
    assert rank.index("hazy") < rank.index("rich")
