"""Property-based tests: Hypothesis generates thousands of random inputs and checks invariants
that must hold for every one of them, then shrinks any failure to the smallest example."""

from itertools import permutations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.money import (
    Expense,
    SplitError,
    Transfer,
    balances,
    settle_greedy,
    settle_up,
    split_by_shares,
    split_equal,
    split_exact,
)

amounts = st.integers(min_value=1, max_value=10_000_000)  # up to ₹1,00,000
user_sets = st.sets(st.integers(min_value=1, max_value=50), min_size=1, max_size=12)


# --- splitting --------------------------------------------------------------------------------


def test_hundred_rupees_three_ways():
    assert split_equal(10_000, [3, 1, 2]) == {1: 3334, 2: 3333, 3: 3333}


@given(amounts, user_sets)
def test_equal_split_sums_exactly_and_differs_by_at_most_one_paisa(total, users):
    parts = split_equal(total, users)
    assert sum(parts.values()) == total
    assert set(parts) == users
    assert max(parts.values()) - min(parts.values()) <= 1


@given(amounts, st.dictionaries(st.integers(1, 50), st.integers(1, 100), min_size=1, max_size=12))
def test_share_split_sums_exactly_and_is_within_a_paisa_of_exact(total, shares):
    parts = split_by_shares(total, shares)
    assert sum(parts.values()) == total
    weight = sum(shares.values())
    for uid, s in shares.items():
        exact = total * s / weight
        assert abs(parts[uid] - exact) < 1


@given(amounts, st.dictionaries(st.integers(1, 50), st.integers(1, 100), min_size=2, max_size=12))
def test_more_shares_never_means_paying_less(total, shares):
    parts = split_by_shares(total, shares)
    for a, b in permutations(shares, 2):
        if shares[a] > shares[b]:
            assert parts[a] >= parts[b]


def test_percent_split():
    # ₹999.99 at 50:30:20 is 49999.5 / 29999.7 / 19999.8. Floors leave 2 paise over; they go to the
    # two people who lost the most to rounding (0.8 and 0.7), not to the biggest share.
    assert split_by_shares(99_999, {1: 50, 2: 30, 3: 20}) == {1: 49_999, 2: 30_000, 3: 20_000}


@pytest.mark.parametrize(
    ("call", "args"),
    [
        (split_equal, (100, [])),
        (split_equal, (0, [1])),
        (split_by_shares, (100, {1: 0})),
        (split_exact, (100, {1: 60, 2: 30})),
        (split_exact, (100, {1: 110, 2: -10})),
    ],
)
def test_impossible_splits_are_rejected(call, args):
    with pytest.raises(SplitError):
        call(*args)


# --- balances and settling up -----------------------------------------------------------------


@st.composite
def ledgers(draw):
    """A random group: some people, some expenses split equally among random subsets."""
    people = sorted(draw(st.sets(st.integers(1, 30), min_size=2, max_size=12)))
    expenses = []
    for _ in range(draw(st.integers(1, 15))):
        payer = draw(st.sampled_from(people))
        among = draw(st.sets(st.sampled_from(people), min_size=1))
        amount = draw(amounts)
        expenses.append(Expense(payer, amount, split_equal(amount, among)))
    return expenses


@given(ledgers())
def test_balances_always_sum_to_zero(expenses):
    assert sum(balances(expenses).values()) == 0


@given(ledgers())
@settings(max_examples=300)
def test_settle_up_clears_every_balance(expenses):
    net = balances(expenses)
    transfers = settle_up(net)
    after = balances(expenses, transfers)
    assert all(v == 0 for v in after.values())
    assert all(t.amount > 0 and t.from_user != t.to_user for t in transfers)


@given(ledgers())
@settings(max_examples=300)
def test_settle_up_never_needs_more_payments_than_greedy(expenses):
    net = balances(expenses)
    people = sum(1 for v in net.values() if v)
    exact, greedy = settle_up(net), settle_greedy(net)
    assert len(exact) <= len(greedy) <= max(people - 1, 0)


@given(ledgers())
def test_nobody_both_pays_and_gets_paid(expenses):
    transfers = settle_up(balances(expenses))
    payers = {t.from_user for t in transfers}
    receivers = {t.to_user for t in transfers}
    assert not payers & receivers


def test_exact_settle_up_beats_greedy_on_a_known_case():
    # Person 1 is owed ₹8 and person 2 owes exactly ₹8, but greedy starts with the biggest numbers
    # (5 is owed ₹12, 2 owes ₹8) and never sees the pair. Found by random search.
    net = {1: 800, 2: -800, 3: -500, 4: -700, 5: 1200}
    assert len(settle_greedy(net)) == 4
    best = settle_up(net)
    assert len(best) == 3
    assert Transfer(2, 1, 800) in best
    after = dict(net)
    for t in best:
        after[t.from_user] += t.amount
        after[t.to_user] -= t.amount
    assert set(after.values()) == {0}


def test_settle_up_rejects_unbalanced_input():
    with pytest.raises(ValueError):
        settle_up({1: 100, 2: -99})


def test_payments_move_balance_both_ways():
    net = balances([Expense(1, 900, {1: 300, 2: 300, 3: 300})], [Transfer(2, 1, 300)])
    assert net == {1: 300, 2: 0, 3: -300}
