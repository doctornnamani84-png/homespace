"""Database models for HomeSpace."""
from datetime import datetime
from enum import Enum

from app.extensions import db


class UserRole(str, Enum):
    TENANT = "tenant"
    LANDLORD = "landlord"
    ADMIN = "admin"


class BookingStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class User(db.Model):
    """A platform user: tenant, landlord, or admin."""

    __tablename__ = "users"

    id: int = db.Column(db.Integer, primary_key=True)
    name: str = db.Column(db.String(120), nullable=False)
    email: str = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash: str = db.Column(db.String(255), nullable=False)
    role: str = db.Column(
        db.Enum(UserRole, values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=UserRole.TENANT,
    )
    created_at: datetime = db.Column(db.DateTime, default=datetime.utcnow)

    properties = db.relationship(
        "Property", back_populates="landlord", lazy="dynamic",
        foreign_keys="Property.landlord_id",
    )
    bookings = db.relationship(
        "Booking", back_populates="tenant", lazy="dynamic",
        foreign_keys="Booking.tenant_id",
    )

    def __repr__(self) -> str:
        return f"<User {self.id} {self.email} ({self.role})>"


class Property(db.Model):
    """A rentable or short-let-able property listing."""

    __tablename__ = "properties"

    id: int = db.Column(db.Integer, primary_key=True)
    title: str = db.Column(db.String(200), nullable=False)
    description: str = db.Column(db.Text, nullable=True)
    location: str = db.Column(db.String(200), nullable=False, index=True)

    price_per_night: float = db.Column(db.Numeric(10, 2), nullable=True)
    monthly_rent: float = db.Column(db.Numeric(10, 2), nullable=True)
    is_short_let: bool = db.Column(db.Boolean, default=False, nullable=False)
    video_url: str = db.Column(db.String(500), nullable=True)

    landlord_id: int = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    created_at: datetime = db.Column(db.DateTime, default=datetime.utcnow)

    landlord = db.relationship("User", back_populates="properties")
    bookings = db.relationship(
        "Booking", back_populates="property", lazy="dynamic",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        db.CheckConstraint(
            "price_per_night IS NOT NULL OR monthly_rent IS NOT NULL",
            name="ck_property_has_a_price",
        ),
    )

    def __repr__(self) -> str:
        return f"<Property {self.id} {self.title!r} in {self.location}>"


class UnavailableDate(db.Model):
    """A date range a landlord has blocked off (e.g., for maintenance).

    Any booking attempt overlapping a blocked range should be rejected,
    exactly the same way an existing confirmed booking would be — this
    reuses the same overlap logic, just against a different table.
    """

    __tablename__ = "unavailable_dates"

    id: int = db.Column(db.Integer, primary_key=True)
    property_id: int = db.Column(
        db.Integer, db.ForeignKey("properties.id"), nullable=False, index=True
    )
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    reason: str = db.Column(db.String(255), nullable=True)
    created_at: datetime = db.Column(db.DateTime, default=datetime.utcnow)

    property = db.relationship("Property", backref="unavailable_dates")

    __table_args__ = (
        db.CheckConstraint("end_date > start_date", name="ck_unavailable_dates_valid"),
    )

    def __repr__(self) -> str:
        return f"<UnavailableDate property={self.property_id} {self.start_date}→{self.end_date}>"    


class Booking(db.Model):
    """A tenant's booking request for a property over a date range."""

    __tablename__ = "bookings"

    id: int = db.Column(db.Integer, primary_key=True)
    property_id: int = db.Column(
        db.Integer, db.ForeignKey("properties.id"), nullable=False, index=True
    )
    tenant_id: int = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    total_price: float = db.Column(db.Numeric(10, 2), nullable=False)
    status: str = db.Column(
        db.Enum(BookingStatus, values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=BookingStatus.PENDING,
    )
    created_at: datetime = db.Column(db.DateTime, default=datetime.utcnow)
    payout_status: str = db.Column(db.String(20), nullable=False, default="not_paid_out")

    property = db.relationship("Property", back_populates="bookings")
    tenant = db.relationship("User", back_populates="bookings")

    __table_args__ = (
        db.CheckConstraint("end_date > start_date", name="ck_booking_dates_valid"),
    )

    def __repr__(self) -> str:
        return f"<Booking {self.id} property={self.property_id} {self.start_date}→{self.end_date}>"


class PropertyImage(db.Model):
    """A single photo attached to a property listing.

    A property can have many images (gallery-style); each image is its
    own row so ordering, deleting, or adding one doesn't disturb others.
    """

    __tablename__ = "property_images"

    id: int = db.Column(db.Integer, primary_key=True)
    property_id: int = db.Column(
        db.Integer, db.ForeignKey("properties.id"), nullable=False, index=True
    )
    image_url: str = db.Column(db.String(500), nullable=False)
    created_at: datetime = db.Column(db.DateTime, default=datetime.utcnow)

    property = db.relationship("Property", backref=db.backref("images", cascade="all, delete-orphan"))

    def __repr__(self) -> str:
        return f"<PropertyImage property={self.property_id} url={self.image_url[:30]}...>" 


class PropertyVideo(db.Model):
    """A short video tour attached to a property listing.

    Uploaded directly (by landlord or admin) via Cloudinary, same
    pattern as PropertyImage — no external link required.
    """

    __tablename__ = "property_videos"

    id: int = db.Column(db.Integer, primary_key=True)
    property_id: int = db.Column(
        db.Integer, db.ForeignKey("properties.id"), nullable=False, index=True
    )
    video_url: str = db.Column(db.String(500), nullable=False)
    created_at: datetime = db.Column(db.DateTime, default=datetime.utcnow)

    property = db.relationship("Property", backref=db.backref("videos", cascade="all, delete-orphan"))

    def __repr__(self) -> str:
        return f"<PropertyVideo property={self.property_id}>"           