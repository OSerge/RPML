import bcrypt

# Bcrypt of "no-user-timing-mitigation" — used so login always runs verify when user is missing.
DUMMY_PASSWORD_HASH = (
    "$2b$12$0IGR1E8QsI7XOvHe4MM9.eWFso7L/wlr8Pgi7zzB8BD2NBuTFOkT2"
)


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("ascii"))
