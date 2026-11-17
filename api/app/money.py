"""The money core: splitting an expense, computing balances, and settling up.

Everything here is pure functions over integers. Amounts are always in paise (1/100 of a rupee),
never floats: 0.1 + 0.2 != 0.3 in floating point, and a ledger that drifts by a paisa per expense
stops balancing.
"""

from __future__ import annotations

import heapq
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

# Above this many people with a non-zero balance, settle_up falls back to the greedy method.
# The exact search is O(2^n * n): 12 people is about 50k steps, 20 would be about 20M.
EXACT_SETTLE_LIMIT = 12


class SplitError(ValueError):
    """The requested split is impossible (bad shares, amounts that don't add up, ...)."""


# ---------------------------------------------------------------------------------------------
# Splitting one expense
# ---------------------------------------------------------------------------------------------


def split_equal(total: int, user_ids: Iterable[int]) -> dict[int, int]:
    """Split `total` as evenly as possible. Parts differ by at most one paisa and sum to `total`.

    ₹100 three ways is 3334 + 3333 + 3333 paise. The leftover paise go to the lowest user ids,
    so the same expense always splits the same way.
    """
    ids = sorted(set(user_ids))
    if not ids:
        raise SplitError("split between nobody")
    if total <= 0:
        raise SplitError("amount must be positive")
    base, extra = divmod(total, len(ids))
    return {uid: base + (1 if i < extra else 0) for i, uid in enumerate(ids)}


def split_by_shares(total: int, shares: Mapping[int, int]) -> dict[int, int]:
    """Split in proportion to whole-number shares (2:1:1, or percentages like 50:30:20).

    Uses the largest-remainder method: everyone gets the floor of their exact share, then the
    paise left over go to whoever lost the most to rounding. The result always sums to `total`.
    """
    if not shares:
        raise SplitError("split between nobody")
    if total <= 0:
        raise SplitError("amount must be positive")
    if any(s <= 0 for s in shares.values()):
        raise SplitError("every share must be at least 1")
    weight = sum(shares.values())
    floors = {uid: total * s // weight for uid, s in shares.items()}
    leftover = total - sum(floors.values())
    # Biggest rounding loss first; ties go to the lower user id.
    by_loss = sorted(shares, key=lambda uid: (-(total * shares[uid] % weight), uid))
    for uid in by_loss[:leftover]:
        floors[uid] += 1
    return floors


def split_exact(total: int, amounts: Mapping[int, int]) -> dict[int, int]:
    """Use amounts the user typed in. They must be non-negative and add up to `total` exactly."""
    if not amounts:
        raise SplitError("split between nobody")
    if any(a < 0 for a in amounts.values()):
        raise SplitError("amounts cannot be negative")
    if sum(amounts.values()) != total:
        raise SplitError(f"amounts add up to {sum(amounts.values())}, not {total}")
    return dict(amounts)


# ---------------------------------------------------------------------------------------------
# Balances
# ---------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Expense:
    paid_by: int
    amount: int
    owed: Mapping[int, int]  # user id -> paise, sums to amount


@dataclass(frozen=True)
class Transfer:
    """`from_user` pays `to_user` `amount` paise."""

    from_user: int
    to_user: int
    amount: int


def balances(expenses: Iterable[Expense], payments: Iterable[Transfer] = ()) -> dict[int, int]:
    """Net position per user: positive means the group owes them, negative means they owe.

    Paying for an expense raises your balance; your share of it lowers it. Paying someone back
    raises yours and lowers theirs. Every step moves money between people, so the balances of a
    group always sum to exactly zero.
    """
    net: dict[int, int] = defaultdict(int)
    for e in expenses:
        net[e.paid_by] += e.amount
        for uid, owed in e.owed.items():
            net[uid] -= owed
    for p in payments:
        net[p.from_user] += p.amount
        net[p.to_user] -= p.amount
    return dict(net)


# ---------------------------------------------------------------------------------------------
# Settling up
# ---------------------------------------------------------------------------------------------


def settle_up(net: Mapping[int, int]) -> list[Transfer]:
    """Payments that bring every balance to zero, using as few payments as practical.

    Finding the true minimum is NP-hard in general. It equals (people with a balance) minus (the
    most groups they can be split into that each sum to zero), because a group of k people that
    nets to zero can always settle among themselves in k - 1 payments. For up to
    EXACT_SETTLE_LIMIT people that partition is found exactly by a search over subsets; beyond it,
    the greedy method still guarantees at most n - 1 payments.
    """
    owed = {uid: b for uid, b in net.items() if b != 0}
    if sum(owed.values()) != 0:
        raise ValueError("balances must sum to zero")
    if not owed:
        return []
    people = sorted(owed)
    groups = _zero_sum_groups(people, owed) if len(people) <= EXACT_SETTLE_LIMIT else [people]
    transfers: list[Transfer] = []
    for group in groups:
        transfers.extend(settle_greedy({uid: owed[uid] for uid in group}))
    return transfers


def settle_greedy(net: Mapping[int, int]) -> list[Transfer]:
    """Repeatedly have the biggest debtor pay the biggest creditor.

    Each payment clears at least one person, so n people need at most n - 1 payments.
    """
    creditors = [(-b, uid) for uid, b in net.items() if b > 0]
    debtors = [(b, uid) for uid, b in net.items() if b < 0]  # most negative first
    heapq.heapify(creditors)
    heapq.heapify(debtors)
    transfers = []
    while creditors and debtors:
        credit, to_user = heapq.heappop(creditors)
        debt, from_user = heapq.heappop(debtors)
        amount = min(-credit, -debt)
        transfers.append(Transfer(from_user, to_user, amount))
        if -credit > amount:
            heapq.heappush(creditors, (credit + amount, to_user))
        if -debt > amount:
            heapq.heappush(debtors, (debt + amount, from_user))
    return transfers


def _zero_sum_groups(people: list[int], owed: Mapping[int, int]) -> list[list[int]]:
    """Split `people` into the largest number of groups whose balances each sum to zero.

    best[mask] = the most zero-sum groups the people in `mask` can be ordered into: adding people
    one at a time, a group closes every time the running total returns to zero.
    """
    n = len(people)
    full = (1 << n) - 1
    total = [0] * (1 << n)
    for mask in range(1, 1 << n):
        low = (mask & -mask).bit_length() - 1
        total[mask] = total[mask & (mask - 1)] + owed[people[low]]

    best = [0] * (1 << n)
    last = [0] * (1 << n)  # which person was added last on the best path
    for mask in range(1, 1 << n):
        top, pick = -1, 0
        m = mask
        while m:
            i = (m & -m).bit_length() - 1
            m &= m - 1
            if best[mask ^ (1 << i)] > top:
                top, pick = best[mask ^ (1 << i)], i
        best[mask] = top + (1 if total[mask] == 0 else 0)
        last[mask] = pick

    # Walk back to recover the order, then cut it wherever the running total hits zero.
    order: list[int] = []
    mask = full
    while mask:
        order.append(last[mask])
        mask ^= 1 << last[mask]
    order.reverse()

    groups, current, running = [], [], 0
    for i in order:
        current.append(people[i])
        running += owed[people[i]]
        if running == 0:
            groups.append(current)
            current = []
    return groups
