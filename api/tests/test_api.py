import random
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest


def balances(group_json):
    return {m["id"]: m["balance"] for m in group_json["members"]}


def new_group(owner, *others, name="Goa trip"):
    res = owner.post("/api/groups", json={"name": name, "memberEmails": [o.email for o in others]})
    assert res.status_code == 201, res.text
    return res.json()["id"]


def add_expense(client, gid, amount, paid_by, split, **extra):
    body = {"description": "Dinner", "amountPaise": amount, "paidBy": paid_by, "split": split}
    return client.post(f"/api/groups/{gid}/expenses", json=body | extra)


# --- auth -------------------------------------------------------------------------------------


def test_signup_sets_httponly_cookie_and_me_works(anon):
    res = anon.post(
        "/api/auth/signup",
        json={"email": "Asha@Example.com", "name": "Asha", "password": "password123"},
    )
    assert res.status_code == 201
    assert "httponly" in res.headers["set-cookie"].lower()
    assert anon.get("/api/auth/me").json()["user"]["email"] == "asha@example.com"


def test_duplicate_email_and_bad_login(make_user, anon):
    asha = make_user("Asha")
    dup = anon.post(
        "/api/auth/signup", json={"email": asha.email, "name": "X", "password": "password123"}
    )
    assert dup.status_code == 409
    wrong = anon.post("/api/auth/login", json={"email": asha.email, "password": "nope-nope"})
    ghost = anon.post("/api/auth/login", json={"email": "ghost@x.dev", "password": "nope-nope"})
    assert wrong.status_code == ghost.status_code == 401
    assert wrong.json() == ghost.json()


def test_forged_cookie_is_ignored(anon):
    anon.cookies.set("splitkit_session", "not.a.jwt")
    assert anon.get("/api/groups").status_code == 401


# --- groups and access ------------------------------------------------------------------------


def test_create_group_with_members_by_email(make_user):
    asha, ravi, meera = make_user("Asha"), make_user("Ravi"), make_user("Meera")
    gid = new_group(asha, ravi, meera)
    group = asha.get(f"/api/groups/{gid}").json()
    assert {m["name"] for m in group["members"]} == {"Asha", "Ravi", "Meera"}
    assert ravi.get("/api/groups").json()[0]["memberCount"] == 3


def test_unknown_emails_are_listed(make_user):
    asha = make_user("Asha")
    res = asha.post("/api/groups", json={"name": "G", "memberEmails": ["nobody@x.dev"]})
    assert res.status_code == 404
    assert res.json() == {"error": "users_not_found", "details": {"emails": ["nobody@x.dev"]}}


def test_outsiders_get_404_everywhere(make_user):
    asha, ravi, eve = make_user("Asha"), make_user("Ravi"), make_user("Eve")
    gid = new_group(asha, ravi)
    assert eve.get(f"/api/groups/{gid}").status_code == 404
    split = {"method": "equal", "userIds": [eve.id]}
    assert add_expense(eve, gid, 100, eve.id, split).status_code == 404
    assert eve.post(f"/api/groups/{gid}/members", json={"email": eve.email}).status_code == 404
    assert eve.get("/api/groups").json() == []


def test_cannot_split_with_or_be_paid_by_a_non_member(make_user):
    asha, ravi, eve = make_user("Asha"), make_user("Ravi"), make_user("Eve")
    gid = new_group(asha, ravi)
    res = add_expense(asha, gid, 900, asha.id, {"method": "equal", "userIds": [asha.id, eve.id]})
    assert res.status_code == 422
    assert res.json()["details"] == {"userIds": [eve.id]}
    res = add_expense(asha, gid, 900, eve.id, {"method": "equal", "userIds": [asha.id]})
    assert res.status_code == 422


# --- expenses and balances --------------------------------------------------------------------


def test_hundred_rupees_three_ways(make_user):
    asha, ravi, meera = make_user("Asha"), make_user("Ravi"), make_user("Meera")
    gid = new_group(asha, ravi, meera)
    ids = [asha.id, ravi.id, meera.id]
    group = add_expense(asha, gid, 10_000, asha.id, {"method": "equal", "userIds": ids}).json()
    shares = {s["userId"]: s["owedPaise"] for s in group["activity"][0]["shares"]}
    assert sorted(shares.values()) == [3333, 3333, 3334]
    assert sum(shares.values()) == 10_000
    assert balances(group)[asha.id] == 10_000 - shares[asha.id]
    assert sum(balances(group).values()) == 0


def test_shares_and_exact_splits(make_user):
    asha, ravi = make_user("Asha"), make_user("Ravi")
    gid = new_group(asha, ravi)
    shares = {"method": "shares", "shares": {str(asha.id): 2, str(ravi.id): 1}}
    g = add_expense(asha, gid, 30_000, asha.id, shares).json()
    assert balances(g) == {asha.id: 10_000, ravi.id: -10_000}

    exact = {"method": "exact", "amounts": {str(asha.id): 500, str(ravi.id): 1500}}
    g = add_expense(ravi, gid, 2_000, ravi.id, exact).json()
    assert balances(g) == {asha.id: 9_500, ravi.id: -9_500}


@pytest.mark.parametrize(
    ("amount", "split", "error"),
    [
        (1000, {"method": "exact", "amounts": {"1": 400, "2": 500}}, "invalid_split"),
        (1000, {"method": "shares", "shares": {"1": 0}}, "invalid_split"),
        (0, {"method": "equal", "userIds": [1]}, "invalid_request"),
        (10.5, {"method": "equal", "userIds": [1]}, "invalid_request"),
        (1000, {"method": "thirds", "userIds": [1]}, "invalid_request"),
    ],
)
def test_bad_expenses_are_rejected(make_user, amount, split, error):
    asha, ravi = make_user("Asha"), make_user("Ravi")
    gid = new_group(asha, ravi)
    res = add_expense(asha, gid, amount, asha.id, split)
    assert res.status_code == 422
    assert res.json()["error"] == error


def test_settle_up_then_record_payments_clears_everything(make_user):
    asha, ravi, meera = make_user("Asha"), make_user("Ravi"), make_user("Meera")
    gid = new_group(asha, ravi, meera)
    everyone = {"method": "equal", "userIds": [asha.id, ravi.id, meera.id]}
    add_expense(asha, gid, 90_000, asha.id, everyone)  # hotel
    g = add_expense(ravi, gid, 30_000, ravi.id, everyone).json()  # cab

    suggested = g["settleUp"]
    assert len(suggested) <= 2
    for t in suggested:
        body = {"fromUser": t["fromUser"], "toUser": t["toUser"], "amountPaise": t["amount"]}
        g = meera.post(f"/api/groups/{gid}/payments", json=body).json()
    assert set(balances(g).values()) == {0}
    assert g["settleUp"] == []


def test_payment_rules(make_user):
    asha, ravi, eve = make_user("Asha"), make_user("Ravi"), make_user("Eve")
    gid = new_group(asha, ravi)
    pay = lambda f, t, a=100: asha.post(  # noqa: E731
        f"/api/groups/{gid}/payments", json={"fromUser": f, "toUser": t, "amountPaise": a}
    )
    assert pay(asha.id, asha.id).json()["error"] == "payment_to_self"
    assert pay(asha.id, eve.id).status_code == 422
    assert pay(asha.id, ravi.id, -5).status_code == 422
    assert pay(ravi.id, asha.id).status_code == 201


def test_deleting_an_expense_reverses_it(make_user):
    asha, ravi = make_user("Asha"), make_user("Ravi")
    gid = new_group(asha, ravi)
    g = add_expense(asha, gid, 5_000, asha.id, {"method": "equal", "userIds": [asha.id, ravi.id]})
    eid = g.json()["activity"][0]["id"]
    g = ravi.delete(f"/api/groups/{gid}/expenses/{eid}").json()
    assert set(balances(g).values()) == {0}
    assert asha.delete(f"/api/groups/{gid}/expenses/{eid}").status_code == 404


# --- retries ----------------------------------------------------------------------------------


def test_retried_add_expense_is_recorded_once(make_user):
    asha, ravi = make_user("Asha"), make_user("Ravi")
    gid = new_group(asha, ravi)
    rid = str(uuid.uuid4())
    split = {"method": "equal", "userIds": [asha.id, ravi.id]}
    first = add_expense(asha, gid, 4_000, asha.id, split, clientRequestId=rid)
    again = add_expense(asha, gid, 4_000, asha.id, split, clientRequestId=rid)
    assert (first.status_code, again.status_code) == (201, 200)
    assert len(again.json()["activity"]) == 1


def test_simultaneous_retries_still_record_once(make_user):
    """16 copies of one request released at the same instant, five times over. Only the unique
    constraint can stop the copies that all passed the "already recorded?" check together."""
    asha, ravi = make_user("Asha"), make_user("Ravi")
    gid = new_group(asha, ravi)
    split = {"method": "equal", "userIds": [asha.id, ravi.id]}
    copies = 16

    for _ in range(5):
        rid = str(uuid.uuid4())
        start = threading.Barrier(copies)

        def submit(_, rid=rid, start=start):
            start.wait()
            return add_expense(asha, gid, 4_000, asha.id, split, clientRequestId=rid).status_code

        with ThreadPoolExecutor(copies) as pool:
            statuses = list(pool.map(submit, range(copies)))
        assert sorted(statuses) == [200] * (copies - 1) + [201]

    assert len(asha.get(f"/api/groups/{gid}").json()["activity"]) == 5


# --- the two balance calculations agree -------------------------------------------------------


def test_group_list_balance_matches_group_page(make_user):
    """The list computes your balance in SQL; the group page computes it in Python. Throw a random
    mix of expenses, payments and deletions at both and check they always agree."""
    rng = random.Random(7)
    people = [make_user(n) for n in ["Asha", "Ravi", "Meera", "Kabir"]]
    gid = new_group(people[0], *people[1:])
    ids = [p.id for p in people]
    for _ in range(40):
        actor = rng.choice(people)
        roll = rng.random()
        if roll < 0.6:
            among = rng.sample(ids, rng.randint(1, 4))
            method = rng.choice(["equal", "shares"])
            split = (
                {"method": "equal", "userIds": among}
                if method == "equal"
                else {"method": "shares", "shares": {str(u): rng.randint(1, 5) for u in among}}
            )
            add_expense(actor, gid, rng.randint(1, 500_000), rng.choice(ids), split)
        elif roll < 0.85:
            a, b = rng.sample(ids, 2)
            body = {"fromUser": a, "toUser": b, "amountPaise": rng.randint(1, 100_000)}
            actor.post(f"/api/groups/{gid}/payments", json=body)
        else:
            expenses = [
                a
                for a in actor.get(f"/api/groups/{gid}").json()["activity"]
                if a["kind"] == "expense"
            ]
            if expenses:
                actor.delete(f"/api/groups/{gid}/expenses/{rng.choice(expenses)['id']}")

    page = balances(people[0].get(f"/api/groups/{gid}").json())
    assert sum(page.values()) == 0
    for p in people:
        listed = p.get("/api/groups").json()[0]["myBalance"]
        assert listed == page[p.id]
