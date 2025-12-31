from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(200), unique=True, index=True, nullable=False)
    full_name = Column(String(200), nullable=True)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Item(Base):
    __tablename__ = "items"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    category = Column(String(50), nullable=True)     # e.g., Luggage, Document, Electronics
    room = Column(String(50), nullable=False)        # e.g., Second Bedroom
    cupboard = Column(String(50), nullable=True)     # e.g., 1st Cupboard
    shelf = Column(String(50), nullable=True)        # e.g., Top Shelf
    loft = Column(String(50), nullable=True)         # e.g., Loft Area
    inside_items = Column(Text, nullable=True)      # e.g., Items inside a box
    notes = Column(Text, nullable=True)
    # Image metadata for uploaded photo
    image_name = Column(String(255), nullable=True)  # original filename
    image_path = Column(String(255), nullable=True)  # path/URL served by static files
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    # owner (user) relationship
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    owner = relationship("User", backref="items")

class Room(Base):
    __tablename__ = "rooms"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), unique=True, nullable=False)
    description = Column(String(255), nullable=True)
