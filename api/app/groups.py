import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Response
from pydantic import EmailStr, Field
from sqlalchemy import func, literal, select, union_all
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import money
from app.auth import CurrentUser
from app.db import get_db
from app.errors import ApiError
from app.models import Expense, ExpenseShare, Group, Membership, Payment, User
from app.schemas import Camel

router = APIRouter(prefix="/api/groups", tags=["groups"])
Db = Annotated[Session, Depends(get_db)]
Paise = Annotated[int, Field(gt=0, le=1_000_000_000)]  # up to ₹1 crore


# --- request bodies ---------------------------------------------------------------------------


class GroupIn(Camel):
    name: str = Field(min_length=1, max_length=80)
    member_emails: list[EmailStr] = Field(default_factory=list, max_length=49)


class MemberIn(Camel):
    email: EmailStr


class EqualSplit(Camel):
    method: Literal["equal"]
    user_ids: list[int] = Field(min_length=1, max_length=50)


class SharesSplit(Camel):
    method: Literal["shares"]
    shares: dict[int, int] = Field(min_length=1, max_length=50)


class ExactSplit(Camel):
    method: Literal["exact"]
    amounts: dict[int, int] = Field(min_length=1, max_length=50)


class ExpenseIn(Camel):
    description: str = Field(min_length=1, max_length=120)
    amount_paise: Paise
    paid_by: int
    split: Annotated[EqualSplit | SharesSplit | ExactSplit, Field(discriminator="method")]
    client_request_id: uuid.UUID | None = None


class PaymentIn(Camel):
    from_user: int
    to_user: int
    amount_paise: Paise


# --- responses --------------------------------------------------------------------------------


class GroupSummary(Camel):
    id: int
    name: str
    member_count: int
    my_balance: int


class MemberOut(Camel):
    id: int
    name: str
    email: str
    balance: int


class TransferOut(Camel):
    from_user: int
    to_user: int
    amount: int


class ShareOut(Camel):
    user_id: int
    owed_paise: int


class ExpenseOut(Camel):
    kind: Literal["expense"] = "expense"
    id: int
    description: str
    amount_paise: int
    paid_by: int
    split_method: str
    shares: list[ShareOut]
    created_by: int
    created_at: datetime


class PaymentOut(Camel):
    kind: Literal["payment"] = "payment"
    id: int
    from_user: int
    to_user: int
    amount_paise: int
    created_by: int
    created_at: datetime


class GroupDetail(Camel):
    id: int
    name: str
    members: list[MemberOut]
    settle_up: list[TransferOut]
    activity: list[ExpenseOut | PaymentOut]


# --- helpers ----------------------------------------------------------------------------------


def _group_for(db: Session, group_id: int, user: User) -> Group:
    """The group, if `user` belongs to it. Non-members get 404, not 403, so group ids can't be
    probed to learn which groups exist."""
    group = db.scalar(
        select(Group).join(Membership).where(Group.id == group_id, Membership.user_id == user.id)
    )
    if group is None:
        raise ApiError(404, "group_not_found")
    return group


def _member_ids(group: Group) -> set[int]:
    return {m.user_id for m in group.members}


def _detail(db: Session, group: Group) -> GroupDetail:
    expenses = db.scalars(
        select(Expense).where(Expense.group_id == group.id).order_by(Expense.id.desc())
    ).all()
    payments = db.scalars(
        select(Payment).where(Payment.group_id == group.id).order_by(Payment.id.desc())
    ).all()

    net = money.balances(
        [
            money.Expense(e.paid_by, e.amount_paise, {s.user_id: s.owed_paise for s in e.shares})
            for e in expenses
        ],
        [money.Transfer(p.from_user, p.to_user, p.amount_paise) for p in payments],
    )
    members = sorted(group.members, key=lambda m: m.user.name.lower())
    activity: list[ExpenseOut | PaymentOut] = [
        ExpenseOut(
            id=e.id,
            description=e.description,
            amount_paise=e.amount_paise,
            paid_by=e.paid_by,
            split_method=e.split_method,
            shares=[ShareOut(user_id=s.user_id, owed_paise=s.owed_paise) for s in e.shares],
            created_by=e.created_by,
            created_at=e.created_at,
        )
        for e in expenses
    ] + [
        PaymentOut(
            id=p.id,
            from_user=p.from_user,
            to_user=p.to_user,
            amount_paise=p.amount_paise,
            created_by=p.created_by,
            created_at=p.created_at,
        )
        for p in payments
    ]
    activity.sort(key=lambda a: a.created_at, reverse=True)

    return GroupDetail(
        id=group.id,
        name=group.name,
        members=[
            MemberOut(
                id=m.user_id, name=m.user.name, email=m.user.email, balance=net.get(m.user_id, 0)
            )
            for m in members
        ],
        settle_up=[
            TransferOut(from_user=t.from_user, to_user=t.to_user, amount=t.amount)
            for t in money.settle_up(net)
        ],
        activity=activity[:200],
    )


def _users_by_email(db: Session, emails: list[str]) -> list[User]:
    wanted = {e.lower() for e in emails}
    found = db.scalars(select(User).where(User.email.in_(wanted))).all()
    missing = wanted - {u.email for u in found}
    if missing:
        raise ApiError(404, "users_not_found", {"emails": sorted(missing)})
    return list(found)


# --- routes -----------------------------------------------------------------------------------


@router.get("")
def list_groups(user: CurrentUser, db: Db) -> list[GroupSummary]:
    """Each of my groups with my balance in it, computed in one SQL query.

    The same sum as money.balances, written in SQL so the list stays one query however many
    groups there are. A test checks the two always agree.
    """
    me = user.id
    movements = union_all(
        select(Expense.group_id, Expense.amount_paise.label("delta")).where(Expense.paid_by == me),
        select(Expense.group_id, (-ExpenseShare.owed_paise).label("delta"))
        .join(ExpenseShare)
        .where(ExpenseShare.user_id == me),
        select(Payment.group_id, Payment.amount_paise.label("delta")).where(
            Payment.from_user == me
        ),
        select(Payment.group_id, (-Payment.amount_paise).label("delta")).where(
            Payment.to_user == me
        ),
        select(Membership.group_id, literal(0).label("delta")).where(Membership.user_id == me),
    ).subquery()
    mine = (
        select(movements.c.group_id, func.sum(movements.c.delta).label("balance"))
        .group_by(movements.c.group_id)
        .subquery()
    )
    counts = (
        select(Membership.group_id, func.count().label("n"))
        .group_by(Membership.group_id)
        .subquery()
    )
    rows = db.execute(
        select(Group.id, Group.name, counts.c.n, mine.c.balance)
        .join(mine, mine.c.group_id == Group.id)
        .join(counts, counts.c.group_id == Group.id)
        .join(Membership, (Membership.group_id == Group.id) & (Membership.user_id == me))
        .order_by(Group.id.desc())
    ).all()
    return [
        GroupSummary(id=r.id, name=r.name, member_count=r.n, my_balance=int(r.balance))
        for r in rows
    ]


@router.post("", status_code=201)
def create_group(body: GroupIn, user: CurrentUser, db: Db) -> GroupDetail:
    others = _users_by_email(db, [str(e) for e in body.member_emails]) if body.member_emails else []
    group = Group(name=body.name.strip(), created_by=user.id)
    member_ids = {user.id} | {u.id for u in others}
    group.members = [Membership(user_id=uid) for uid in member_ids]
    db.add(group)
    db.commit()
    db.refresh(group)
    return _detail(db, group)


@router.get("/{group_id}")
def get_group(group_id: int, user: CurrentUser, db: Db) -> GroupDetail:
    return _detail(db, _group_for(db, group_id, user))


@router.post("/{group_id}/members")
def add_member(group_id: int, body: MemberIn, user: CurrentUser, db: Db) -> GroupDetail:
    group = _group_for(db, group_id, user)
    (new,) = _users_by_email(db, [str(body.email)])
    if new.id not in _member_ids(group):
        group.members.append(Membership(user_id=new.id))
        db.commit()
    return _detail(db, group)


def _shares_for(body: ExpenseIn) -> dict[int, int]:
    split = body.split
    try:
        if isinstance(split, EqualSplit):
            return money.split_equal(body.amount_paise, split.user_ids)
        if isinstance(split, SharesSplit):
            return money.split_by_shares(body.amount_paise, split.shares)
        return money.split_exact(body.amount_paise, split.amounts)
    except money.SplitError as err:
        raise ApiError(422, "invalid_split", {"reason": str(err)}) from None


@router.post("/{group_id}/expenses", status_code=201)
def add_expense(
    group_id: int, body: ExpenseIn, user: CurrentUser, db: Db, response: Response
) -> GroupDetail:
    group = _group_for(db, group_id, user)
    members = _member_ids(group)
    shares = _shares_for(body)
    outsiders = ({body.paid_by} | set(shares)) - members
    if outsiders:
        raise ApiError(422, "not_group_members", {"userIds": sorted(outsiders)})

    if body.client_request_id and _already_recorded(db, group.id, body.client_request_id):
        response.status_code = 200
        return _detail(db, group)

    expense = Expense(
        group_id=group.id,
        paid_by=body.paid_by,
        description=body.description.strip(),
        amount_paise=body.amount_paise,
        split_method=body.split.method,
        created_by=user.id,
        client_request_id=body.client_request_id,
        shares=[ExpenseShare(user_id=uid, owed_paise=amt) for uid, amt in shares.items() if amt],
    )
    db.add(expense)
    try:
        db.commit()
    except IntegrityError:
        # Two copies of the same request raced past the check above; the unique constraint let
        # exactly one in. Answer the loser as if it were a retry.
        db.rollback()
        if body.client_request_id and _already_recorded(db, group.id, body.client_request_id):
            response.status_code = 200
            return _detail(db, group)
        raise
    return _detail(db, group)


def _already_recorded(db: Session, group_id: int, request_id: uuid.UUID) -> bool:
    return (
        db.scalar(
            select(Expense.id).where(
                Expense.group_id == group_id, Expense.client_request_id == request_id
            )
        )
        is not None
    )


@router.delete("/{group_id}/expenses/{expense_id}")
def delete_expense(group_id: int, expense_id: int, user: CurrentUser, db: Db) -> GroupDetail:
    group = _group_for(db, group_id, user)
    expense = db.get(Expense, expense_id)
    if expense is None or expense.group_id != group.id:
        raise ApiError(404, "expense_not_found")
    db.delete(expense)
    db.commit()
    return _detail(db, group)


@router.post("/{group_id}/payments", status_code=201)
def record_payment(group_id: int, body: PaymentIn, user: CurrentUser, db: Db) -> GroupDetail:
    group = _group_for(db, group_id, user)
    if body.from_user == body.to_user:
        raise ApiError(422, "payment_to_self")
    outsiders = {body.from_user, body.to_user} - _member_ids(group)
    if outsiders:
        raise ApiError(422, "not_group_members", {"userIds": sorted(outsiders)})
    db.add(
        Payment(
            group_id=group.id,
            from_user=body.from_user,
            to_user=body.to_user,
            amount_paise=body.amount_paise,
            created_by=user.id,
        )
    )
    db.commit()
    return _detail(db, group)
