"""SQLAlchemy session factory for hacklog."""

from sqlalchemy.orm import sessionmaker

Session = sessionmaker(autoflush=True, autocommit=False, expire_on_commit=False)
