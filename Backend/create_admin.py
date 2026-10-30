"""Create the first admin user. Run once after database setup."""
import sys
from getpass import getpass

sys.path.insert(0, ".")

from sqlalchemy import select
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.admin import Admin

db = SessionLocal()

email = input("Admin email: ").strip()
full_name = input("Admin full name: ").strip()
password = getpass("Admin password (min 8 chars): ")

if len(password) < 8:
    print("Password must be at least 8 characters")
    sys.exit(1)

existing = db.scalar(select(Admin).where(Admin.email == email.lower()))
if existing:
    print(f"Admin {email} already exists.")
    if input("Reset password? (y/n): ").lower() == 'y':
        existing.password_hash = hash_password(password)
        db.commit()
        print("Password reset successfully.")
    db.close()
    sys.exit(0)

admin = Admin(
    full_name=full_name,
    email=email.lower(),
    password_hash=hash_password(password),
    is_active=True,
)
db.add(admin)
db.commit()
print(f"Admin '{email}' created successfully.")
print(f"Admin ID: {admin.id}")
db.close()
