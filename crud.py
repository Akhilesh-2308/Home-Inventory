from sqlalchemy.orm import Session
from sqlalchemy import or_
import models, schemas
from typing import Optional
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

# Guard against extremely large passwords (in bytes). pbkdf2_sha256 does not
# have bcrypt's 72-byte limit, so allow reasonably long passwords but prevent
# abuse by enforcing a maximum.
MAX_PASSWORD_BYTES = 4096

def _ensure_password_ok(password: str):
    if not isinstance(password, str) or password.strip() == "":
        raise ValueError("Password must be a non-empty string.")
    b = password.encode("utf-8")
    if len(b) > MAX_PASSWORD_BYTES:
        raise ValueError(f"Password is too long ({len(b)} bytes). Please choose a shorter password.")

# ---------------- User helpers ----------------

def get_user_by_email(db: Session, email: str) -> Optional[models.User]:
    return db.query(models.User).filter(models.User.email == email).first()

def get_user(db: Session, user_id: int) -> Optional[models.User]:
    return db.query(models.User).filter(models.User.id == user_id).first()

def create_user(db: Session, user_in: schemas.UserCreate) -> models.User:
    # validate password size first
    _ensure_password_ok(user_in.password)
    hashed = pwd_context.hash(user_in.password)   # passlib handles bcrypt_sha256
    db_user = models.User(
        email=user_in.email,
        hashed_password=hashed,
        full_name=getattr(user_in, "full_name", None),
        is_active=True
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

def authenticate_user(db: Session, email: str, plain_password: str) -> Optional[models.User]:
    user = get_user_by_email(db, email)
    if not user:
        return None
    try:
        _ensure_password_ok(plain_password)
    except ValueError:
        return None
    if not pwd_context.verify(plain_password, user.hashed_password):
        return None
    return user

def update_password(db: Session, user: models.User, new_password: str) -> models.User:
    _ensure_password_ok(new_password)
    user.hashed_password = pwd_context.hash(new_password)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user

def get_items(db: Session, owner_id: int | None = None, skip: int = 0, limit: int = 100):
    q = db.query(models.Item)
    if owner_id is not None:
        q = q.filter(models.Item.owner_id == owner_id)
    return q.offset(skip).limit(limit).all()

def get_item(db: Session, item_id: int, owner_id: int | None = None):
    q = db.query(models.Item).filter(models.Item.id == item_id)
    if owner_id is not None:
        q = q.filter(models.Item.owner_id == owner_id)
    return q.first()

def search_items(db: Session, search_term: str | None = None, owner_id: int | None = None, mode: str = 'text'):
    """Search items by text or return images when mode='image'.
    If search_term is provided and mode='text', search across several fields.
    """
    if mode == 'image':
        q = db.query(models.Item).filter(models.Item.image_path.isnot(None))
        if owner_id is not None:
            q = q.filter(models.Item.owner_id == owner_id)
        return q.all()

    # text search
    search_pattern = f"%{search_term or ''}%"
    q = db.query(models.Item).filter(
        or_(
            models.Item.name.ilike(search_pattern),
            models.Item.category.ilike(search_pattern),
            models.Item.room.ilike(search_pattern),
            models.Item.cupboard.ilike(search_pattern),
            models.Item.shelf.ilike(search_pattern),
            models.Item.notes.ilike(search_pattern),
            models.Item.image_name.ilike(search_pattern)
        )
    )
    if owner_id is not None:
        q = q.filter(models.Item.owner_id == owner_id)
    return q.all()

def create_item(db: Session, item: schemas.ItemCreate, owner_id: int | None = None):
    payload = item.dict()
    if owner_id is not None:
        payload['owner_id'] = owner_id
    db_item = models.Item(**payload)
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item

def update_item(db: Session, item_id: int, item: schemas.ItemUpdate):
    db_item = db.query(models.Item).filter(models.Item.id == item_id).first()
    if db_item:
        for key, value in item.dict(exclude_unset=True).items():
            setattr(db_item, key, value)
        db.commit()
        db.refresh(db_item)
    return db_item


def attach_image_to_item(db: Session, item_id: int, image_name: str, image_path: str, owner_id: int | None = None):
    """Attach uploaded image metadata to an existing item."""
    q = db.query(models.Item).filter(models.Item.id == item_id)
    if owner_id is not None:
        q = q.filter(models.Item.owner_id == owner_id)
    db_item = q.first()
    if not db_item:
        return None
    db_item.image_name = image_name
    db_item.image_path = image_path
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item

def delete_item(db: Session, item_id: int, owner_id: int | None = None):
    q = db.query(models.Item).filter(models.Item.id == item_id)
    if owner_id is not None:
        q = q.filter(models.Item.owner_id == owner_id)
    db_item = q.first()
    if db_item:
        db.delete(db_item)
        db.commit()
    return db_item