from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime


# --- User / Auth schemas ---
class UserBase(BaseModel):
    email: EmailStr
    full_name: Optional[str] = None

class UserCreate(UserBase):
    password: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserOut(UserBase):
    id: int
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None

class ItemBase(BaseModel):
    name: str
    category: Optional[str] = None
    room: str
    cupboard: Optional[str] = None
    shelf: Optional[str] = None
    loft: Optional[str] = None
    inside_items: Optional[str] = None
    notes: Optional[str] = None
    image_name: Optional[str] = None
    image_path: Optional[str] = None

class RoomBase(BaseModel):
    name: str
    description: str | None = None

class RoomCreate(RoomBase):
    pass

class RoomUpdate(RoomBase):
    pass

class Room(RoomBase):
    id: int

    class Config:
        from_attributes = True

class ItemCreate(ItemBase):
    pass

class ItemUpdate(ItemBase):
    pass

class ItemOut(ItemBase):
    id: int
    created_at: datetime
    image_name: Optional[str] = None
    image_path: Optional[str] = None

    class Config:
        from_attributes = True