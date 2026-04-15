"""
Super Admin хэрэглэгч үүсгэх эсвэл одоо байгаа хэрэглэгчийг super_admin болгох скрипт.

Ашиглах:
  python shoplift_detector/create_admin.py --create --username admin --email admin@example.com --password "YourPass123!"
  python shoplift_detector/create_admin.py --promote --username existing_user
"""

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from app.core.security import get_password_hash  # noqa: E402
from app.db.repository.users import UserRepository  # noqa: E402


async def create_super_admin(username, email, password, full_name=None):
    repo = UserRepository()
    await repo._create_table()

    existing = await repo.get_by_identifier(username)
    if existing:
        print(f"'{username}' нэртэй хэрэглэгч аль хэдийн бүртгэлтэй байна.")
        return False

    user_id = await repo.create(
        username=username,
        email=email,
        phone_number=None,
        hashed_password=get_password_hash(password),
        full_name=full_name or username,
        role="super_admin",
    )

    if user_id:
        print(f"Super Admin амжилттай үүсгэлээ! ID: {user_id}, Username: {username}")
        return True
    else:
        print("Алдаа гарлаа.")
        return False


async def promote_to_admin(username):
    repo = UserRepository()
    await repo._create_table()

    user = await repo.get_by_identifier(username)
    if not user:
        print(f"'{username}' нэртэй хэрэглэгч олдсонгүй.")
        return False

    success = await repo._execute_update(
        "UPDATE users SET role = 'super_admin' WHERE username = %s",
        (username,),
    )

    if success:
        print(f"'{username}' хэрэглэгч super_admin болгогдлоо!")
        return True
    else:
        print("Алдаа гарлаа.")
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Super Admin удирдлага")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--create", action="store_true", help="Шинэ super_admin үүсгэх")
    group.add_argument("--promote", action="store_true", help="Байгаа хэрэглэгчийг super_admin болгох")

    parser.add_argument("--username", required=True)
    parser.add_argument("--email", default=None)
    parser.add_argument("--password", default=None)
    parser.add_argument("--fullname", default=None)

    args = parser.parse_args()

    if args.create:
        if not args.email or not args.password:
            print("--create ашиглахад --email болон --password заавал шаардлагатай.")
            sys.exit(1)
        asyncio.run(create_super_admin(args.username, args.email, args.password, args.fullname))
    elif args.promote:
        asyncio.run(promote_to_admin(args.username))
