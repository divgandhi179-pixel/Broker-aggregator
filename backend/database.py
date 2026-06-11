import os
import json
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Text
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

# Database Connection URL configuration
DATABASE_URL = os.environ.get("DATABASE_URL")

if not DATABASE_URL:
    if os.environ.get("VERCEL"):
        # Ephemeral database for Vercel preview environments
        DATABASE_URL = "sqlite:////tmp/database.db"
    else:
        # Local SQLite database
        os.makedirs("data", exist_ok=True)
        DATABASE_URL = "sqlite:///data/database.db"
else:
    # Ensure postgresql scheme compatibility (Vercel/Render connection string fix)
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Connect to database
# SQLite requires 'check_same_thread=False' configuration
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Models
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    username = Column(String, nullable=False)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    brokers = relationship("Broker", back_populates="user", cascade="all, delete-orphan")
    orders = relationship("Order", back_populates="user", cascade="all, delete-orphan")
    ipo_applications = relationship("IPOApplication", back_populates="user", cascade="all, delete-orphan")


class Broker(Base):
    __tablename__ = "brokers"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    broker_name = Column(String, nullable=False)
    credentials_json = Column(Text, nullable=False) # JSON encoded credentials

    user = relationship("User", back_populates="brokers")

    @property
    def credentials(self):
        try:
            return json.loads(self.credentials_json)
        except Exception:
            return {}

    @credentials.setter
    def credentials(self, val):
        self.credentials_json = json.dumps(val)


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    broker_name = Column(String, nullable=False)
    order_id = Column(String, nullable=False)
    symbol = Column(String, nullable=False)
    qty = Column(Integer, nullable=False)
    side = Column(String, nullable=False)
    execution_price = Column(Float, nullable=False)
    status = Column(String, nullable=False)
    timestamp = Column(String, nullable=False)

    user = relationship("User", back_populates="orders")


class IPOApplication(Base):
    __tablename__ = "ipo_applications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    broker_name = Column(String, nullable=False)
    ipo_symbol = Column(String, nullable=False)
    ipo_name = Column(String, nullable=False)
    lots = Column(Integer, nullable=False)
    shares = Column(Integer, nullable=False)
    bid_price = Column(Float, nullable=False)
    amount = Column(Float, nullable=False)
    upi_id = Column(String, nullable=False)
    status = Column(String, nullable=False)
    timestamp = Column(String, nullable=False)

    user = relationship("User", back_populates="ipo_applications")


# Dependency helper for FastAPI routes
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Database initialization helper
def init_db():
    Base.metadata.create_all(bind=engine)
