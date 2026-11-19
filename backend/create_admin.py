import argparse
import getpass
import os
import sys

from dotenv import load_dotenv

import backend.app.db.models
load_dotenv()

from sqlalchemy.orm import Session

from backend.app.db.database import SessionLocal
from backend.app.db.auth_models import User, UserCompanyRole
from backend.app.db.company import Company
from backend.app.core.security import hash_password


def main():
    parser = argparse.ArgumentParser(
        description="Create the first Training Manager account."
    )
    parser.add_argument("--company-id", type=int, required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True)
    args = parser.parse_args()

    email = args.email.strip().lower()
    password = getpass.getpass("Choose account password: ")
    confirmation = getpass.getpass("Confirm password: ")

    if len(password) < 12:
        print("Password must contain at least 12 characters.")
        sys.exit(1)

    if password != confirmation:
        print("Passwords do not match.")
        sys.exit(1)

    db: Session = SessionLocal()

    try:
        company = db.query(Company).filter(
            Company.company_id == args.company_id
        ).first()

        if company is None:
            print("Company ID does not exist.")
            sys.exit(1)

        user = db.query(User).filter(User.email == email).first()

        if user is not None:
            print("This email already has an account.")
            sys.exit(1)

        user = User(
            full_name=args.name.strip(),
            email=email,
            password_hash=hash_password(password),
            is_active=True,
        )
        db.add(user)
        db.flush()

        membership = UserCompanyRole(
            user_id=user.user_id,
            company_id=company.company_id,
            employee_id=None,
            role="Training Manager",
            is_active=True,
        )
        db.add(membership)
        db.commit()

        print("Training Manager account created successfully.")
        print(f"User ID: {user.user_id}")
        print(f"Company ID: {company.company_id}")

    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()

