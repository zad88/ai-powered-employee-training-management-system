from datetime import datetime, timezone

from backend.app.db.database import SessionLocal
from backend.app.services.token_revocation import cleanup_expired_access_tokens


def main() -> None:
    with SessionLocal.begin() as db:
        deleted_count = cleanup_expired_access_tokens(
            db,
            now=datetime.now(timezone.utc),
        )
    print(f"Removed {deleted_count} expired access-token revocation records.")


if __name__ == "__main__":
    main()
