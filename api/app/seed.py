"""Local demo data: four people and a Goa trip. Wipes the database first.

uv run python -m app.seed
"""

import bcrypt

from app import money
from app.config import BCRYPT_ROUNDS
from app.db import Base, SessionLocal, engine
from app.models import Expense, ExpenseShare, Group, Membership, Payment, User

DEMO_PASSWORD = "splitkit-demo"
PEOPLE = [
    ("demo@splitkit.dev", "Asha"),
    ("ravi@splitkit.dev", "Ravi"),
    ("meera@splitkit.dev", "Meera"),
    ("kabir@splitkit.dev", "Kabir"),
]


def seed() -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    pw = bcrypt.hashpw(DEMO_PASSWORD.encode(), bcrypt.gensalt(BCRYPT_ROUNDS)).decode()
    with SessionLocal() as db:
        users = [User(email=e, name=n, password_hash=pw) for e, n in PEOPLE]
        db.add_all(users)
        db.flush()
        asha, ravi, meera, kabir = (u.id for u in users)
        group = Group(name="Goa, March", created_by=asha)
        group.members = [Membership(user_id=u.id) for u in users]
        db.add(group)
        db.flush()

        def expense(desc, paid_by, amount, owed, method="equal"):
            db.add(
                Expense(
                    group_id=group.id,
                    paid_by=paid_by,
                    description=desc,
                    amount_paise=amount,
                    split_method=method,
                    created_by=paid_by,
                    shares=[ExpenseShare(user_id=u, owed_paise=a) for u, a in owed.items() if a],
                )
            )

        everyone = [asha, ravi, meera, kabir]
        expense("Villa, 3 nights", asha, 2_400_000, money.split_equal(2_400_000, everyone))
        expense("Scooter rentals", ravi, 360_000, money.split_equal(360_000, [ravi, meera, kabir]))
        expense(
            "Seafood dinner at Fisherman's Wharf",
            meera,
            845_050,
            money.split_by_shares(845_050, {asha: 2, ravi: 1, meera: 1, kabir: 2}),
            "shares",
        )
        expense("Airport cab", kabir, 180_000, money.split_equal(180_000, everyone))
        db.add(
            Payment(
                group_id=group.id,
                from_user=ravi,
                to_user=asha,
                amount_paise=300_000,
                created_by=ravi,
            )
        )
        db.commit()
    print(f"seeded 4 users and one group; demo login {PEOPLE[0][0]}")


if __name__ == "__main__":
    seed()
