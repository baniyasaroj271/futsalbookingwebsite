from datetime import datetime
from uuid import uuid4

from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    phone = db.Column(db.String(30), nullable=False, default="")
    role = db.Column(db.String(20), nullable=False, default="customer")
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    bookings = db.relationship("Booking", back_populates="user", cascade="all, delete-orphan")
    venues = db.relationship("Venue", back_populates="owner")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_customer(self):
        return self.role == "customer"

    @property
    def is_owner(self):
        return self.role == "owner"

    @property
    def is_admin(self):
        return self.role == "admin"


class Venue(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False)
    slug = db.Column(db.String(160), unique=True, nullable=False)
    location = db.Column(db.String(160), nullable=False)
    address = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=False)
    image_url = db.Column(db.String(500), nullable=False)
    price_per_hour = db.Column(db.Integer, nullable=False)
    rating = db.Column(db.Float, default=4.8, nullable=False)
    amenities = db.Column(db.String(500), default="", nullable=False)
    latitude = db.Column(db.Float, default=27.7172, nullable=False)
    longitude = db.Column(db.Float, default=85.3240, nullable=False)
    distance_km = db.Column(db.Float, default=2.5, nullable=False)
    open_time = db.Column(db.String(10), default="06:00", nullable=False)
    close_time = db.Column(db.String(10), default="22:00", nullable=False)
    available_slots = db.Column(db.Integer, default=8, nullable=False)
    is_open = db.Column(db.Boolean, default=True, nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    approval_status = db.Column(db.String(20), nullable=False, default="approved")
    owner = db.relationship("User", back_populates="venues")
    closures = db.relationship("VenueClosure", back_populates="venue", cascade="all, delete-orphan")
    bookings = db.relationship("Booking", back_populates="venue", cascade="all, delete-orphan")

    @property
    def amenity_list(self):
        return [item.strip() for item in self.amenities.split(",") if item.strip()]


class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    booking_reference = db.Column(
        db.String(16), unique=True, nullable=False, default=lambda: f"FH-{uuid4().hex[:10].upper()}"
    )
    booking_date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.String(10), nullable=False)
    duration = db.Column(db.Integer, nullable=False, default=1)
    total_price = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(30), nullable=False, default="confirmed")
    payment_method = db.Column(db.String(30), nullable=False, default="cash_on_arrival")
    payment_status = db.Column(db.String(30), nullable=False, default="pay_on_arrival")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    venue_id = db.Column(db.Integer, db.ForeignKey("venue.id"), nullable=False)
    user = db.relationship("User", back_populates="bookings")
    venue = db.relationship("Venue", back_populates="bookings")


class Tournament(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(180), nullable=False)
    venue_name = db.Column(db.String(180), nullable=False)
    tournament_date = db.Column(db.Date, nullable=False)
    registration_deadline = db.Column(db.Date, nullable=False)
    entry_fee = db.Column(db.Integer, nullable=False, default=0)
    prize = db.Column(db.String(120), nullable=False)
    rules = db.Column(db.Text, nullable=False, default="")
    team_limit = db.Column(db.Integer, nullable=False, default=16)
    status = db.Column(db.String(30), nullable=False, default="Open")
    owner_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    registrations = db.relationship("TournamentRegistration", back_populates="tournament", cascade="all, delete-orphan")


class Announcement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(180), nullable=False)
    body = db.Column(db.Text, nullable=False)
    published_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=True)
    category = db.Column(db.String(40), nullable=False, default="Community")
    venue_id = db.Column(db.Integer, db.ForeignKey("venue.id"), nullable=True)
    author_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    venue = db.relationship("Venue")


class TournamentRegistration(db.Model):
    __table_args__ = (db.UniqueConstraint("tournament_id", "user_id", name="uq_tournament_user"),)
    id = db.Column(db.Integer, primary_key=True)
    team_name = db.Column(db.String(120), nullable=False)
    captain_name = db.Column(db.String(120), nullable=False)
    captain_phone = db.Column(db.String(30), nullable=False)
    status = db.Column(db.String(30), nullable=False, default="registered")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    tournament_id = db.Column(db.Integer, db.ForeignKey("tournament.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    tournament = db.relationship("Tournament", back_populates="registrations")
    user = db.relationship("User")


class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(180), nullable=False)
    message = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(40), nullable=False, default="booking")
    is_read = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)


class ReceiptScan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    stored_filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    merchant_name = db.Column(db.String(180), default="")
    transaction_date = db.Column(db.String(30), default="")
    amount = db.Column(db.String(40), default="")
    transaction_reference = db.Column(db.String(120), default="")
    raw_text = db.Column(db.Text, default="")
    ocr_status = db.Column(db.String(30), nullable=False, default="not_verified")
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class VenueClosure(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    venue_id = db.Column(db.Integer, db.ForeignKey("venue.id"), nullable=False)
    closure_date = db.Column(db.Date, nullable=False)
    reason = db.Column(db.String(255), nullable=False)
    venue = db.relationship("Venue", back_populates="closures")


class Review(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    rating = db.Column(db.Integer, nullable=False)
    body = db.Column(db.Text, nullable=False, default="")
    status = db.Column(db.String(20), nullable=False, default="published")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    venue_id = db.Column(db.Integer, db.ForeignKey("venue.id"), nullable=False)
    user = db.relationship("User")
    venue = db.relationship("Venue")
    __table_args__ = (db.UniqueConstraint("user_id", "venue_id", name="uq_review_user_venue"),)


class ReviewReport(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    reason = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="open")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    review_id = db.Column(db.Integer, db.ForeignKey("review.id"), nullable=False)
    reporter_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    review = db.relationship("Review")


class FavoriteVenue(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    venue_id = db.Column(db.Integer, db.ForeignKey("venue.id"), nullable=False)
    __table_args__ = (db.UniqueConstraint("user_id", "venue_id", name="uq_favorite_user_venue"),)


class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    action = db.Column(db.String(80), nullable=False)
    entity_type = db.Column(db.String(40), nullable=False)
    entity_id = db.Column(db.Integer, nullable=False)
    details = db.Column(db.String(500), nullable=False, default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    admin_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
