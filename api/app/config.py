import os

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql+psycopg://seatlock:seatlock@localhost:55440/splitkit"
)
JWT_SECRET = os.environ.get("JWT_SECRET", "dev-only-secret-change-me")
PRODUCTION = os.environ.get("ENV") == "production"
COOKIE_NAME = "splitkit_session"
SESSION_DAYS = 7
# bcrypt work factor. Tests lower it to keep sign-ups fast; never lower it in production.
BCRYPT_ROUNDS = int(os.environ.get("BCRYPT_ROUNDS", "12"))

if PRODUCTION and "JWT_SECRET" not in os.environ:
    raise RuntimeError("JWT_SECRET must be set in production")
