import pytest
import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

from app import create_app
from app.extensions import db
from app.models import User, Venue, VenueClosure, Booking
from app.venue_status import venue_status


@pytest.fixture()
def client(tmp_path):
    class TestConfig:
        TESTING = True
        SECRET_KEY = "test-secret"
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'test.db'}"
        SQLALCHEMY_TRACK_MODIFICATIONS = False

    app = create_app(TestConfig)
    with app.test_client() as test_client:
        yield test_client
    with app.app_context():
        db.drop_all()


def test_homepage_has_seeded_venues(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"The Futsal Arena" in response.data


def test_dashboard_loads_real_content_and_filters(client):
    csrf = re.search(
        r'name="csrf_token" value="([^"]+)"',
        client.get("/auth/register").get_data(as_text=True),
    ).group(1)
    client.post(
        "/auth/register",
        data={
            "name": "Dashboard Player",
            "email": "dashboard@example.com",
            "phone": "9812345678",
            "password": "secret123",
            "csrf_token": csrf,
        },
    )
    response = client.get("/dashboard?q=Kick+Off&distance=3")
    assert response.status_code == 200
    assert b"Kick Off Futsal" in response.data
    assert b"Kathmandu Valley 5-a-side Cup" in response.data
    assert b"FutsalHub is now live" in response.data
    assert b"Goal Getter" not in response.data


def test_user_can_register_and_book(client):
    csrf = re.search(r'name="csrf_token" value="([^"]+)"', client.get("/auth/register").get_data(as_text=True)).group(1)
    response = client.post(
        "/auth/register",
        data={"name": "Test Player", "email": "player@example.com", "phone": "9812345678", "password": "secret123", "csrf_token": csrf},
        follow_redirects=True,
    )
    assert response.status_code == 200
    response = client.post(
        "/venues/the-futsal-arena/book",
        data={"booking_date": "2099-01-01", "start_time": "18:00", "duration": "2", "csrf_token": csrf},
        follow_redirects=True,
    )
    assert b"Your pitch is booked" in response.data
    assert b"3,600" in response.data


def test_authentication_and_permissions(client):
    register_page = client.get("/auth/register").get_data(as_text=True)
    csrf = re.search(r'name="csrf_token" value="([^"]+)"', register_page).group(1)
    data = {"name": "Customer", "email": "customer@example.com", "phone": "9812345678", "password": "secret123", "csrf_token": csrf}
    assert client.post("/auth/register", data=data).status_code == 302
    assert client.get("/auth/profile").status_code == 200
    assert client.get("/admin").status_code == 403
    assert client.post("/auth/logout", data={"csrf_token": csrf}).status_code == 302
    assert client.get("/auth/profile").status_code == 302


def test_csrf_and_duplicate_registration_are_rejected(client):
    assert client.post("/auth/register", data={"name": "No Token", "email": "x@example.com", "phone": "9812345678", "password": "secret123"}).status_code == 400
    csrf = re.search(r'name="csrf_token" value="([^"]+)"', client.get("/auth/register").get_data(as_text=True)).group(1)
    data = {"name": "Customer", "email": "customer@example.com", "phone": "9812345678", "password": "secret123", "csrf_token": csrf}
    client.post("/auth/register", data=data)
    response = client.post("/auth/register", data=data, follow_redirects=True)
    assert b"already exists" in response.data


def test_owner_and_admin_permissions(client):
    with client.application.app_context():
        owner = User(name="Owner", email="owner@example.com", phone="9812345678", role="owner")
        owner.set_password("secret123")
        admin = User(name="Admin", email="admin@example.com", phone="9812345679", role="admin")
        admin.set_password("secret123")
        db.session.add_all([owner, admin])
        db.session.commit()
    csrf = re.search(r'name="csrf_token" value="([^"]+)"', client.get("/auth/login").get_data(as_text=True)).group(1)
    client.post("/auth/login", data={"email": "owner@example.com", "password": "secret123", "csrf_token": csrf})
    assert client.get("/owner").status_code == 200
    assert client.get("/admin").status_code == 403
    client.post("/auth/logout", data={"csrf_token": csrf})
    csrf = re.search(r'name="csrf_token" value="([^"]+)"', client.get("/auth/login").get_data(as_text=True)).group(1)
    client.post("/auth/login", data={"email": "admin@example.com", "password": "secret123", "csrf_token": csrf})
    assert client.get("/admin").status_code == 200


def test_venue_status_uses_nepal_time_and_closures(client):
    with client.application.app_context():
        venue = Venue.query.filter_by(slug="the-futsal-arena").first()
        kathmandu = ZoneInfo("Asia/Kathmandu")
        open_now, open_label = venue_status(
            venue,
            [],
            datetime(2026, 10, 24, 12, 0, tzinfo=kathmandu),
        )
        closed_now, closed_label = venue_status(
            venue,
            [],
            datetime(2026, 10, 23, 23, 30, tzinfo=kathmandu),
        )
        closure = VenueClosure(
            venue_id=venue.id,
            closure_date=date(2026, 10, 24),
            reason="Dashain holiday",
        )
        holiday_closed, holiday_label = venue_status(
            venue,
            [closure],
            datetime(2026, 10, 24, 12, 0, tzinfo=kathmandu),
        )
    assert open_now is True
    assert "Open until" in open_label
    assert closed_now is False
    assert "opens" in closed_label
    assert holiday_closed is False
    assert "Dashain holiday" in holiday_label


def test_owner_can_update_assigned_venue_and_add_closure(client):
    with client.application.app_context():
        owner = User(name="Venue Owner", email="venue-owner@example.com", phone="9812345680", role="owner")
        owner.set_password("secret123")
        db.session.add(owner)
        db.session.flush()
        venue = Venue.query.filter_by(slug="the-futsal-arena").first()
        venue.owner_id = owner.id
        db.session.commit()
    csrf = re.search(r'name="csrf_token" value="([^"]+)"', client.get("/auth/login").get_data(as_text=True)).group(1)
    client.post("/auth/login", data={"email": "venue-owner@example.com", "password": "secret123", "csrf_token": csrf})
    assert client.get("/owner/venues/the-futsal-arena/edit").status_code == 200
    csrf = re.search(r'name="csrf_token" value="([^"]+)"', client.get("/owner/venues/the-futsal-arena/edit").get_data(as_text=True)).group(1)
    response = client.post(
        "/owner/venues/the-futsal-arena/edit",
        data={
            "csrf_token": csrf,
            "name": "Arena Updated",
            "address": "Updated Road, Lalitpur",
            "description": "Updated venue description.",
            "price_per_hour": "2000",
            "available_slots": "4",
            "open_time": "07:00",
            "close_time": "22:00",
            "is_open": "on",
            "closure_date": "2099-01-01",
            "closure_reason": "Private event",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Arena Updated" in response.data
    assert b"Private event" in response.data


def test_owner_registration_requires_admin_approval(client):
    with client.application.app_context():
        owner = User(name="New Owner", email="new-owner@example.com", phone="9812345683", role="owner")
        owner.set_password("secret123")
        db.session.add(owner)
        db.session.commit()
    csrf = re.search(r'name="csrf_token" value="([^"]+)"', client.get("/auth/login").get_data(as_text=True)).group(1)
    client.post("/auth/login", data={"email": "new-owner@example.com", "password": "secret123", "csrf_token": csrf})
    csrf = re.search(r'name="csrf_token" value="([^"]+)"', client.get("/owner/venues/new").get_data(as_text=True)).group(1)
    response = client.post("/owner/venues/new", data={
        "csrf_token": csrf, "name": "Pending Pitch", "location": "Kathmandu",
        "address": "Test Road", "description": "A pending pitch", "image_url": "https://example.com/pitch.jpg",
        "amenities": "Parking", "latitude": "27.7", "longitude": "85.3",
        "price_per_hour": "1000", "available_slots": "4", "open_time": "06:00", "close_time": "22:00",
    }, follow_redirects=True)
    assert b"approval" in response.data
    assert client.get("/venues/pending-pitch").status_code == 404


def test_admin_dashboard_can_approve_venue(client):
    with client.application.app_context():
        admin = User(name="Admin", email="approval-admin@example.com", phone="9812345684", role="admin")
        admin.set_password("secret123")
        venue = Venue.query.filter_by(slug="the-futsal-arena").first()
        venue.approval_status = "pending"
        db.session.add(admin)
        db.session.commit()
    csrf = re.search(r'name="csrf_token" value="([^"]+)"', client.get("/auth/login").get_data(as_text=True)).group(1)
    client.post("/auth/login", data={"email": "approval-admin@example.com", "password": "secret123", "csrf_token": csrf})
    assert client.get("/admin").status_code == 200
    csrf = re.search(r'name="csrf_token" value="([^"]+)"', client.get("/admin").get_data(as_text=True)).group(1)
    response = client.post("/admin/venues/1/approval", data={"csrf_token": csrf, "status": "approved"}, follow_redirects=True)
    assert response.status_code == 200
    assert client.get("/venues/the-futsal-arena").status_code == 200


def test_review_requires_completed_booking_and_prevents_duplicate(client):
    csrf = re.search(r'name="csrf_token" value="([^"]+)"', client.get("/auth/register").get_data(as_text=True)).group(1)
    client.post("/auth/register", data={"name": "Reviewer", "email": "reviewer@example.com", "phone": "9812345685", "password": "secret123", "csrf_token": csrf})
    response = client.post("/venues/the-futsal-arena/review", data={"csrf_token": csrf, "rating": "5", "body": "Great pitch"}, follow_redirects=True)
    assert b"completed booking" in response.data
    with client.application.app_context():
        booking = Booking(booking_date=date(2099, 1, 1), start_time="18:00", duration=1, total_price=1800, status="completed", user_id=1, venue_id=1)
        db.session.add(booking)
        db.session.commit()
    response = client.post("/venues/the-futsal-arena/review", data={"csrf_token": csrf, "rating": "5", "body": "Great pitch"}, follow_redirects=True)
    assert b"Thanks for rating" in response.data
    response = client.post("/venues/the-futsal-arena/review", data={"csrf_token": csrf, "rating": "4", "body": "Again"}, follow_redirects=True)
    assert b"already reviewed" in response.data


def test_overlapping_booking_is_rejected(client):
    csrf = re.search(r'name="csrf_token" value="([^"]+)"', client.get("/auth/register").get_data(as_text=True)).group(1)
    client.post(
        "/auth/register",
        data={"name": "First Player", "email": "first@example.com", "phone": "9812345680", "password": "secret123", "csrf_token": csrf},
    )
    booking_data = {"booking_date": "2099-01-01", "start_time": "18:00", "duration": "2", "csrf_token": csrf}
    first = client.post("/venues/the-futsal-arena/book", data=booking_data, follow_redirects=True)
    assert b"FH-" in first.data
    client.post("/auth/logout", data={"csrf_token": csrf})
    csrf = re.search(r'name="csrf_token" value="([^"]+)"', client.get("/auth/register").get_data(as_text=True)).group(1)
    client.post(
        "/auth/register",
        data={"name": "Second Player", "email": "second@example.com", "phone": "9812345681", "password": "secret123", "csrf_token": csrf},
    )
    booking_data["csrf_token"] = csrf
    conflict = client.post("/venues/the-futsal-arena/book", data=booking_data, follow_redirects=True)
    assert b"overlaps an existing booking" in conflict.data


def test_tournament_duplicate_registration_is_rejected(client):
    csrf = re.search(r'name="csrf_token" value="([^"]+)"', client.get("/auth/register").get_data(as_text=True)).group(1)
    client.post(
        "/auth/register",
        data={"name": "Captain", "email": "captain@example.com", "phone": "9812345682", "password": "secret123", "csrf_token": csrf},
    )
    with client.application.app_context():
        tournament = db.session.query(__import__("app.models", fromlist=["Tournament"]).Tournament).first()
        tournament_id = tournament.id
    data = {"team_name": "Champions", "captain_name": "Captain", "captain_phone": "9812345682", "csrf_token": csrf}
    assert client.post(f"/tournaments/{tournament_id}/register", data=data, follow_redirects=True).status_code == 200
    second = client.post(f"/tournaments/{tournament_id}/register", data=data, follow_redirects=True)
    assert b"already registered" in second.data
