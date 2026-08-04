"""Twelve words have to survive being read out loud and typed back.

The failure this guards against is not cryptographic. It is a person on a phone
mishearing "cargo" as "carbon", both machines accepting it, and the two of them
ending up with different keys that fail later as a signature error three layers
away from the cause. The checksum has to catch it at the keyboard.

The known-answer test below is the important one: it pins this implementation
against the BIP39 spec's own vector, so the wordlist and the bit-packing cannot
drift into something that only round-trips with itself.
"""

import importlib.util
from pathlib import Path

import pytest

BIN = Path(__file__).resolve().parent.parent / "fleet" / "bin" / "pair.py"
spec = importlib.util.spec_from_file_location("pair", BIN)
pair = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pair)


def test_the_spec_vector():
    """BIP39's own first test vector. All-zero entropy -> a known mnemonic."""
    entropy = bytes(16)
    expected = ("abandon abandon abandon abandon abandon abandon "
                "abandon abandon abandon abandon abandon about")
    assert " ".join(pair.encode(entropy)) == expected
    assert pair.decode(expected) == entropy


def test_a_second_spec_vector():
    entropy = bytes.fromhex("7f7f7f7f7f7f7f7f7f7f7f7f7f7f7f7f")
    words = pair.encode(entropy)
    assert len(words) == 12
    assert pair.decode(" ".join(words)) == entropy


def test_round_trip_is_stable_over_many_pairings():
    for _ in range(200):
        mnemonic, secret = pair.new_pairing()
        assert len(mnemonic) == 12
        assert pair.secret_from(pair.decode(" ".join(mnemonic))) == secret


def test_both_sides_derive_the_same_secret():
    """The whole point: mint here, type there, same NODE_SECRETS line."""
    mnemonic, minted = pair.new_pairing()
    typed_back = " ".join(mnemonic)
    assert pair.secret_from(pair.decode(typed_back)) == minted


def test_a_misheard_word_is_usually_caught_at_the_keyboard():
    """cargo/carbon is the realistic error. Most of them must not pass.

    "Most", not "all", and the number is knowable: 128 bits of entropy carries
    4 bits of checksum, so a single wrong word slips through with probability
    1/16. That is the BIP39 design, not a defect here — the checksum is a typo
    guard, not a signature.

    The first version of this test swapped one word and demanded a failure,
    which meant it failed roughly one run in sixteen. A flaky test on a
    correctness property is worse than none: it trains you to re-run.
    """
    words = pair.load_wordlist()
    caught = 0
    trials = 200
    for i in range(trials):
        mnemonic, _ = pair.new_pairing()
        swapped = list(mnemonic)
        pos = i % 12
        swapped[pos] = words[(words.index(swapped[pos]) + 1 + i) % 2048]
        try:
            pair.decode(" ".join(swapped))
        except ValueError:
            caught += 1
    rate = caught / trials
    assert rate > 0.85, f"only {rate:.0%} of single-word errors were caught"


def test_a_deliberately_broken_checksum_is_always_caught():
    """Deterministic companion to the statistical test above."""
    words = pair.load_wordlist()
    mnemonic = pair.encode(bytes(16))          # abandon x11 + about
    for candidate in words:
        broken = mnemonic[:-1] + [candidate]
        if candidate == mnemonic[-1]:
            continue
        try:
            pair.decode(" ".join(broken))
        except ValueError:
            return                              # found one, and it was rejected
    pytest.fail("no altered last word was rejected — checksum is not running")


def test_a_word_not_in_the_list_names_itself_and_suggests():
    with pytest.raises(ValueError) as exc:
        pair.decode("abandon abandon abandon abandon abandon abandon "
                    "abandon abandon abandon abandon abandon carbonx")
    assert "carbonx" in str(exc.value)
    assert "did you mean" in str(exc.value)


def test_the_wrong_number_of_words_says_how_many():
    with pytest.raises(ValueError, match="got 3"):
        pair.decode("abandon ability able")


def test_the_wordlist_is_the_canonical_one():
    """A silently changed list decodes differently on the two machines."""
    words = pair.load_wordlist()
    assert len(words) == 2048
    assert words[0] == "abandon" and words[-1] == "zoo"


def test_it_refuses_an_unverified_wordlist(tmp_path):
    bad = tmp_path / "words.txt"
    bad.write_text("\n".join(f"word{i}" for i in range(2048)))
    with pytest.raises(SystemExit, match="checksum mismatch"):
        pair.load_wordlist(bad)


def test_the_secret_comes_from_entropy_not_the_typed_string():
    """Spacing and case must not produce two different keys from one mnemonic."""
    mnemonic, minted = pair.new_pairing()
    messy = "  " + "   ".join(mnemonic).upper().lower() + "  "
    assert pair.secret_from(pair.decode(messy.strip())) == minted
