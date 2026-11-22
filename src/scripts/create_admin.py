import argparse
import sys

from src.api.crud_modules import extra_a, user_crud
from src.api.security import hash_password
from src.api.settings import ROLE_ADMIN
from src.database import SessionLocal


def main() -> int:
    parser = argparse.ArgumentParser(description="Create an ADMIN user")
    parser.add_argument("email")
    parser.add_argument("password")
    args = parser.parse_args()

    email = args.email.lower()
    with SessionLocal() as db:
        existing = user_crud.get_user_by_email(db, email)
        if existing:
            extra_a.update_user_role(db, existing.id, ROLE_ADMIN)
            print(f"User {email} promoted to ADMIN")
        else:
            user_crud.create_user(db, email, hash_password(args.password), ROLE_ADMIN)
            print(f"ADMIN {email} created")
    return 0


if __name__ == "__main__":
    sys.exit(main())