from datetime import UTC, datetime, timedelta
from typing import Annotated

import bcrypt
import jwt
from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import BCRYPT_ROUNDS, COOKIE_NAME, JWT_SECRET, PRODUCTION, SESSION_DAYS
from app.db import get_db
from app.errors import ApiError
from app.models import User
from app.schemas import Camel

router = APIRouter(prefix="/api/auth", tags=["auth"])
Db = Annotated[Session, Depends(get_db)]

# Checked against when the email is unknown, so a wrong email and a wrong password take the
# same time and nobody can probe which emails have accounts.
_DUMMY_HASH = bcrypt.hashpw(b"not-a-real-password", bcrypt.gensalt(BCRYPT_ROUNDS))


class SignupIn(Camel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=60)
    password: str = Field(min_length=8, max_length=72)


class LoginIn(Camel):
    email: EmailStr
    password: str = Field(max_length=72)


class UserOut(Camel):
    id: int
    email: str
    name: str


class SessionOut(BaseModel):
    user: UserOut | None


def _start_session(response: Response, user: User) -> None:
    exp = datetime.now(UTC) + timedelta(days=SESSION_DAYS)
    token = jwt.encode({"sub": str(user.id), "exp": exp}, JWT_SECRET, algorithm="HS256")
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=SESSION_DAYS * 86400,
        httponly=True,
        samesite="lax",
        secure=PRODUCTION,
    )


def optional_user(request: Request, db: Db) -> User | None:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    try:
        user_id = int(jwt.decode(token, JWT_SECRET, algorithms=["HS256"])["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None
    return db.get(User, user_id)


def current_user(user: Annotated[User | None, Depends(optional_user)]) -> User:
    if user is None:
        raise ApiError(401, "not_signed_in")
    return user


CurrentUser = Annotated[User, Depends(current_user)]


@router.post("/signup", status_code=201)
def signup(body: SignupIn, response: Response, db: Db) -> SessionOut:
    user = User(
        email=body.email.lower(),
        name=body.name.strip(),
        password_hash=bcrypt.hashpw(body.password.encode(), bcrypt.gensalt(BCRYPT_ROUNDS)).decode(),
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ApiError(409, "email_taken") from None
    _start_session(response, user)
    return SessionOut(user=UserOut.model_validate(user, from_attributes=True))


@router.post("/login")
def login(body: LoginIn, response: Response, db: Db) -> SessionOut:
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    stored = user.password_hash.encode() if user else _DUMMY_HASH
    if not bcrypt.checkpw(body.password.encode(), stored) or user is None:
        raise ApiError(401, "wrong_email_or_password")
    _start_session(response, user)
    return SessionOut(user=UserOut.model_validate(user, from_attributes=True))


@router.post("/logout", status_code=204)
def logout(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME)


@router.get("/me")
def me(user: Annotated[User | None, Depends(optional_user)]) -> SessionOut:
    return SessionOut(user=UserOut.model_validate(user, from_attributes=True) if user else None)
