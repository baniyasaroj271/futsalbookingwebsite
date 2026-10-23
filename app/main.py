import os
import re
from datetime import date, datetime, time, timedelta
from uuid import uuid4

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, session, url_for
from werkzeug.utils import secure_filename
from sqlalchemy import and_, or_, text

from .extensions import db
from .areas import AREA_COORDINATES, SEARCH_AREAS
from .geo import distance_km
from .ocr import extract_receipt_text, parse_receipt_text
from .models import (
    Announcement,
    Booking,
    Notification,
    ReceiptScan,
    Tournament,
    TournamentRegistration,
    User,
    Venue,
    VenueClosure,
    Review,
    ReviewReport,
    FavoriteVenue,
    AuditLog,
)
from .security import login_required, role_required
from .venue_status import venue_status

main_bp = Blueprint("main", __name__)


def unique_venues(venues):
    seen = set()
    unique = []
    for venue in venues:
        identity = (
            re.sub(r"[^a-z0-9]+", " ", venue.name.casefold()).strip(),
            re.sub(r"[^a-z0-9]+", " ", venue.location.casefold()).strip(),
        )
        if identity in seen:
            continue
        seen.add(identity)
        unique.append(venue)
    return unique


def normalized_search_term(value):
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


@main_bp.app_context_processor
def inject_current_user():
    user_id = session.get("user_id")
    return {
        "current_user": db.session.get(User, user_id) if user_id else None,
        "now_date": datetime.utcnow().date().isoformat(),
    }


@main_bp.get("/")
def index():
    query = request.args.get("q", "").strip()
    venues_query = Venue.query.filter_by(approval_status="approved")
    if query:
        term = f"%{query}%"
        venues_query = venues_query.filter(or_(Venue.name.ilike(term), Venue.location.ilike(term)))
    venues = unique_venues(venues_query.order_by(Venue.rating.desc()).all())
    venue_coordinates = [
        {"name": venue.name, "coordinates": [venue.latitude, venue.longitude]}
        for venue in venues
    ]
    return render_template(
        "index.html",
        venues=venues,
        venue_coordinates=venue_coordinates,
        search_query=query,
    )


@main_bp.get("/search")
def search():
    query = request.args.get("q", "").strip()
    venues_query = Venue.query.filter_by(approval_status="approved")
    area_coordinates = AREA_COORDINATES.get(normalized_search_term(query))
    if query and not area_coordinates:
        term = f"%{query}%"
        venues_query = venues_query.filter(
            or_(Venue.name.ilike(term), Venue.location.ilike(term))
        )
    venues = unique_venues(venues_query.order_by(Venue.rating.desc()).all())
    if area_coordinates:
        latitude, longitude = area_coordinates
        venues = [
            venue
            for venue in venues
            if distance_km(latitude, longitude, venue.latitude, venue.longitude) <= 5
        ]
        venues.sort(
            key=lambda venue: distance_km(
                latitude, longitude, venue.latitude, venue.longitude
            )
        )
    venue_data = [
        {
            "id": venue.id,
            "name": venue.name,
            "slug": venue.slug,
            "location": venue.location,
            "latitude": venue.latitude,
            "longitude": venue.longitude,
            "price": venue.price_per_hour,
            "rating": (db.session.query(db.func.avg(Review.rating)).filter_by(venue_id=venue.id, status="published").scalar() or venue.rating),
            "available_slots": venue.available_slots,
            "is_open": venue.is_open,
            "image_url": venue.image_url,
            "open_time": venue.open_time,
            "close_time": venue.close_time,
            "distance": (
                distance_km(
                    area_coordinates[0],
                    area_coordinates[1],
                    venue.latitude,
                    venue.longitude,
                )
                if area_coordinates
                else None
            ),
        }
        for venue in venues
    ]
    return render_template(
        "search.html",
        venue_data=venue_data,
        search_query=query,
        search_areas=SEARCH_AREAS,
        area_search=bool(area_coordinates),
    )


@main_bp.get("/venues/<slug>")
def venue_detail(slug):
    venue = Venue.query.filter_by(slug=slug, approval_status="approved").first_or_404()
    reviews = Review.query.filter_by(venue_id=venue.id, status="published").order_by(Review.created_at.desc()).all()
    average_rating = db.session.query(db.func.avg(Review.rating)).filter_by(venue_id=venue.id, status="published").scalar()
    own_review = Review.query.filter_by(venue_id=venue.id, user_id=session.get("user_id")).first() if session.get("user_id") else None
    can_review = bool(
        session.get("user_id")
        and Booking.query.filter_by(
            venue_id=venue.id, user_id=session["user_id"], status="completed"
        ).first()
    )
    is_open, status_text = venue_status(venue, venue.closures)
    upcoming_closures = sorted(
        (closure for closure in venue.closures if closure.closure_date >= date.today()),
        key=lambda closure: closure.closure_date,
    )
    return render_template(
        "venues/detail.html",
        venue=venue,
        is_open=is_open,
        status_text=status_text,
        upcoming_closures=upcoming_closures,
        reviews=reviews,
        average_rating=round(average_rating, 1) if average_rating else venue.rating,
        own_review=own_review,
        can_review=can_review,
    )


@main_bp.route("/owner/venues/<slug>/edit", methods=["GET", "POST"])
@role_required("owner", "admin")
def edit_venue(slug):
    venue = Venue.query.filter_by(slug=slug).first_or_404()
    user = db.session.get(User, session["user_id"])
    if user.role != "admin" and venue.owner_id != user.id:
        abort(403)
    if request.method == "POST":
        try:
            venue.name = request.form["name"].strip()
            venue.address = request.form["address"].strip()
            venue.description = request.form["description"].strip()
            venue.price_per_hour = int(request.form["price_per_hour"])
            venue.open_time = request.form["open_time"]
            venue.close_time = request.form["close_time"]
            venue.available_slots = int(request.form["available_slots"])
            venue.is_open = request.form.get("is_open") == "on"
            closure_date = request.form.get("closure_date", "").strip()
            closure_reason = request.form.get("closure_reason", "").strip()
            if (
                not venue.name
                or not venue.address
                or not venue.description
                or venue.price_per_hour < 0
                or venue.available_slots < 0
                or venue.open_time >= venue.close_time
            ):
                raise ValueError
            if closure_date or closure_reason:
                parsed_date = datetime.strptime(closure_date, "%Y-%m-%d").date()
                if parsed_date < date.today() or not closure_reason:
                    raise ValueError
                db.session.add(
                    VenueClosure(
                        venue=venue,
                        closure_date=parsed_date,
                        reason=closure_reason,
                    )
                )
            db.session.commit()
        except (KeyError, TypeError, ValueError):
            db.session.rollback()
            flash("Enter valid venue details, hours, and closure information.", "error")
        else:
            flash("Venue information and schedule updated.", "success")
            return redirect(url_for("main.venue_detail", slug=venue.slug))
    return render_template("venues/edit.html", venue=venue)


@main_bp.post("/venues/<slug>/book")
@login_required
def create_booking(slug):
    venue = Venue.query.filter_by(slug=slug, approval_status="approved").first_or_404()
    try:
        booking_date = datetime.strptime(request.form["booking_date"], "%Y-%m-%d").date()
        start_time = request.form["start_time"]
        duration = int(request.form.get("duration", 1))
        start = datetime.strptime(start_time, "%H:%M").time()
        end = (datetime.combine(booking_date, start) + timedelta(hours=duration)).time()
        if (
            duration not in range(1, 5)
            or booking_date < datetime.utcnow().date()
            or start_time < venue.open_time
            or end.strftime("%H:%M") > venue.close_time
            or not venue.is_open
        ):
            raise ValueError
    except (KeyError, TypeError, ValueError):
        flash("Choose a valid date, time, and duration within the venue schedule.", "error")
        return redirect(url_for("main.venue_detail", slug=slug))


    if any(closure.closure_date == booking_date for closure in venue.closures):
        flash("This venue is closed on the selected date.", "error")
        return redirect(url_for("main.venue_detail", slug=slug))
    try:
        # SQLite takes a write lock before the conflict query; MySQL can map this
        # to its row-locking equivalent when the database URL is migrated.
        db.session.rollback()
        db.session.connection().exec_driver_sql("BEGIN IMMEDIATE")
        conflicts = Booking.query.filter(
            Booking.venue_id == venue.id,
            Booking.booking_date == booking_date,
            Booking.status.in_(["confirmed", "pending"]),
        ).all()
        requested_start = datetime.combine(booking_date, start)
        requested_end = requested_start + timedelta(hours=duration)
        for conflict in conflicts:
            conflict_start = datetime.combine(
                conflict.booking_date,
                datetime.strptime(conflict.start_time, "%H:%M").time(),
            )
            conflict_end = conflict_start + timedelta(hours=conflict.duration)
            if requested_start < conflict_end and conflict_start < requested_end:
                raise ValueError("overlap")
        booking = Booking(
            booking_reference=f"FH-{uuid4().hex[:10].upper()}",
            booking_date=booking_date,
            start_time=start_time,
            duration=duration,
            total_price=venue.price_per_hour * duration,
            user_id=session["user_id"],
            venue_id=venue.id,
            payment_method="cash_on_arrival",
            payment_status="pay_on_arrival",
        )
        db.session.add(booking)
        db.session.add(
            Notification(
                user_id=session["user_id"],
                title="Booking confirmed",
                message=f"{booking.booking_reference} at {venue.name}; pay cash on arrival.",
                category="booking",
            )
        )
        if venue.owner_id:
            db.session.add(
                Notification(
                    user_id=venue.owner_id,
                    title="New venue booking",
                    message=f"{booking.booking_reference} was booked at {venue.name}.",
                    category="booking",
                )
            )
        db.session.commit()
    except ValueError:
        db.session.rollback()
        flash("That time overlaps an existing booking. Choose another slot.", "error")
        return redirect(url_for("main.venue_detail", slug=slug))
    except Exception:
        db.session.rollback()
        raise
    flash("Your pitch is booked. See you on the turf!", "success")
    return redirect(url_for("main.dashboard"))


@main_bp.get("/dashboard")
@login_required
def dashboard():
    user = db.session.get(User, session["user_id"])
    search = request.args.get("q", "").strip()
    area = request.args.get("area", "").strip()
    max_distance = request.args.get("distance", "").strip()
    venue_query = Venue.query.filter_by(approval_status="approved")
    if search:
        term = f"%{search}%"
        venue_query = venue_query.filter(
            or_(Venue.name.ilike(term), Venue.location.ilike(term))
        )
    if area:
        venue_query = venue_query.filter(Venue.location.ilike(f"%{area}%"))
    if max_distance:
        try:
            venue_query = venue_query.filter(Venue.distance_km <= float(max_distance))
        except ValueError:
            flash("Distance filter must be a number.", "error")
    venues = venue_query.order_by(Venue.distance_km.asc(), Venue.rating.desc()).all()
    today = datetime.utcnow().date()
    bookings = (
        Booking.query.filter(
            Booking.user_id == user.id,
            Booking.booking_date >= today,
        )
        .order_by(Booking.booking_date.asc())
        .limit(3)
        .all()
    )
    booking_history = (
        Booking.query.filter_by(user_id=user.id)
        .order_by(Booking.created_at.desc())
        .all()
    )
    tournaments = (
        Tournament.query.filter(Tournament.tournament_date >= today)
        .order_by(Tournament.tournament_date.asc())
        .limit(3)
        .all()
    )
    announcements = (
        Announcement.query.filter(
            Announcement.published_at <= datetime.utcnow(),
            or_(Announcement.expires_at.is_(None), Announcement.expires_at > datetime.utcnow()),
        )
        .order_by(Announcement.published_at.desc())
        .limit(3)
        .all()
    )
    notifications = (
        Notification.query.filter_by(user_id=user.id, is_read=False)
        .order_by(Notification.created_at.desc())
        .limit(5)
        .all()
    )
    return render_template(
        "dashboard.html",
        bookings=bookings,
        booking_history=booking_history,
        venues=venues,
        tournaments=tournaments,
        announcements=announcements,
        notifications=notifications,
        filters={"q": search, "area": area, "distance": max_distance},
    )


@main_bp.post("/bookings/<booking_reference>/cancel")
@login_required
def cancel_booking(booking_reference):
    booking = Booking.query.filter_by(booking_reference=booking_reference).first_or_404()
    user = db.session.get(User, session["user_id"])
    if booking.user_id != user.id and booking.venue.owner_id != user.id and not user.is_admin:
        abort(403)
    if booking.status == "cancelled":
        flash("This booking is already cancelled.", "error")
    else:
        booking.status = "cancelled"
        db.session.add(
            Notification(
                user_id=booking.user_id,
                title="Booking cancelled",
                message=f"{booking.booking_reference} at {booking.venue.name} was cancelled.",
                category="booking",
            )
        )
        db.session.commit()
        flash("Booking cancelled successfully.", "success")
    return redirect(url_for("main.owner_bookings" if user.is_owner or user.is_admin else "main.dashboard"))


@main_bp.get("/owner")
@role_required("owner", "admin")
def owner_dashboard():
    user = db.session.get(User, session["user_id"])
    venues = Venue.query.filter_by(owner_id=user.id).order_by(Venue.id.desc()).all()
    venue_ids = [venue.id for venue in venues]
    booking_count = Booking.query.filter(Booking.venue_id.in_(venue_ids)).count() if venue_ids else 0
    revenue = db.session.query(db.func.coalesce(db.func.sum(Booking.total_price), 0)).filter(Booking.venue_id.in_(venue_ids), Booking.status != "cancelled").scalar() if venue_ids else 0
    return render_template("owner_dashboard.html", venues=venues, booking_count=booking_count, revenue=revenue)


@main_bp.route("/owner/venues/new", methods=["GET", "POST"])
@role_required("owner")
def register_venue():
    if request.method == "POST":
        try:
            name = request.form["name"].strip()
            slug = "-".join(name.lower().split())
            if not name or Venue.query.filter_by(slug=slug).first():
                raise ValueError
            venue = Venue(
                name=name, slug=slug, location=request.form["location"].strip(),
                address=request.form["address"].strip(), description=request.form["description"].strip(),
                image_url=request.form.get("image_url", "").strip(), price_per_hour=int(request.form["price_per_hour"]),
                amenities=request.form.get("amenities", "").strip(), latitude=float(request.form["latitude"]),
                longitude=float(request.form["longitude"]), open_time=request.form["open_time"],
                close_time=request.form["close_time"], available_slots=int(request.form["available_slots"]),
                owner_id=session["user_id"], approval_status="pending",
            )
            if not venue.image_url or venue.price_per_hour < 0 or venue.available_slots < 0 or venue.open_time >= venue.close_time:
                raise ValueError
            db.session.add(venue)
            db.session.commit()
            flash("Venue submitted for admin approval.", "success")
            return redirect(url_for("main.owner_dashboard"))
        except (KeyError, TypeError, ValueError):
            db.session.rollback()
            flash("Enter valid venue details.", "error")
    return render_template("venue_form.html")


@main_bp.get("/owner/bookings")
@role_required("owner", "admin")
def owner_bookings():
    user = db.session.get(User, session["user_id"])
    booking_query = Booking.query.join(Venue)
    if user.is_owner:
        booking_query = booking_query.filter(Venue.owner_id == user.id)
    bookings = booking_query.order_by(Booking.booking_date.asc(), Booking.start_time.asc()).all()
    return render_template("owner_bookings.html", bookings=bookings)


@main_bp.post("/owner/bookings/<booking_reference>/status")
@role_required("owner", "admin")
def update_booking_status(booking_reference):
    user = db.session.get(User, session["user_id"])
    booking = Booking.query.filter_by(booking_reference=booking_reference).first_or_404()
    if user.is_owner and booking.venue.owner_id != user.id:
        abort(403)
    status = request.form.get("status")
    if status not in {"confirmed", "completed", "cancelled"}:
        flash("Invalid booking status.", "error")
    else:
        booking.status = status
        db.session.commit()
        flash("Booking status updated.", "success")
    return redirect(url_for("main.owner_bookings"))


@main_bp.get("/tournaments")
def tournaments():
    today = date.today()
    all_tournaments = Tournament.query.order_by(Tournament.tournament_date.asc()).all()
    upcoming = [item for item in all_tournaments if item.tournament_date > today]
    ongoing = [item for item in all_tournaments if item.tournament_date == today]
    completed = [item for item in all_tournaments if item.tournament_date < today]
    registrations = {}
    if session.get("user_id"):
        registrations = {
            item.tournament_id: item
            for item in TournamentRegistration.query.filter_by(user_id=session["user_id"]).all()
        }
    return render_template(
        "tournaments.html",
        upcoming=upcoming,
        ongoing=ongoing,
        completed=completed,
        registrations=registrations,
        today=today,
    )


@main_bp.post("/tournaments/<int:tournament_id>/register")
@login_required
def register_tournament(tournament_id):
    tournament = db.get_or_404(Tournament, tournament_id)
    if date.today() > tournament.registration_deadline:
        flash("Registration for this tournament has closed.", "error")
    elif tournament.tournament_date < date.today():
        flash("This tournament has already completed.", "error")
    elif len([item for item in tournament.registrations if item.status != "cancelled"]) >= tournament.team_limit:
        flash("This tournament has reached team capacity.", "error")
    elif TournamentRegistration.query.filter_by(
        tournament_id=tournament.id, user_id=session["user_id"]
    ).filter(TournamentRegistration.status != "cancelled").first():
        flash("You have already registered a team for this tournament.", "error")
    else:
        team_name = request.form.get("team_name", "").strip()
        captain_name = request.form.get("captain_name", "").strip()
        captain_phone = request.form.get("captain_phone", "").strip()
        if not team_name or not captain_name or not captain_phone:
            flash("Team name and captain contact details are required.", "error")
        else:
            registration = TournamentRegistration(
                team_name=team_name,
                captain_name=captain_name,
                captain_phone=captain_phone,
                tournament=tournament,
                user_id=session["user_id"],
            )
            db.session.add(registration)
            db.session.add(
                Notification(
                    user_id=session["user_id"],
                    title="Tournament registration received",
                    message=f"{team_name} is registered for {tournament.name}.",
                    category="tournament",
                )
            )
            db.session.commit()
            flash("Team registration submitted.", "success")
    return redirect(url_for("main.tournaments"))


@main_bp.get("/announcements")
def announcements():
    items = Announcement.query.filter(
        Announcement.published_at <= datetime.utcnow(),
        or_(Announcement.expires_at.is_(None), Announcement.expires_at > datetime.utcnow()),
    ).order_by(Announcement.published_at.desc()).all()
    return render_template("announcements.html", announcements=items)


@main_bp.post("/notifications/<int:notification_id>/read")
@login_required
def mark_notification_read(notification_id):
    notification = Notification.query.filter_by(
        id=notification_id, user_id=session["user_id"]
    ).first_or_404()
    notification.is_read = True
    db.session.commit()
    return redirect(request.referrer or url_for("main.dashboard"))


@main_bp.get("/owner/tournaments")
@role_required("owner", "admin")
def owner_tournaments():
    user = db.session.get(User, session["user_id"])
    query = Tournament.query
    if user.is_owner:
        query = query.filter(Tournament.owner_id == user.id)
    return render_template("owner_tournaments.html", tournaments=query.order_by(Tournament.tournament_date).all())


@main_bp.post("/owner/tournaments/<int:tournament_id>/status")
@role_required("owner", "admin")
def update_tournament_status(tournament_id):
    tournament = db.get_or_404(Tournament, tournament_id)
    user = db.session.get(User, session["user_id"])
    if user.is_owner and tournament.owner_id != user.id:
        abort(403)
    status = request.form.get("status")
    if status not in {"Open", "Registering", "Closed", "Completed"}:
        flash("Invalid tournament status.", "error")
    else:
        tournament.status = status
        db.session.commit()
        flash("Tournament status updated.", "success")
    return redirect(url_for("main.owner_tournaments"))


@main_bp.route("/owner/tournaments/new", methods=["GET", "POST"])
@role_required("owner", "admin")
def create_tournament():
    if request.method == "POST":
        try:
            tournament_date = datetime.strptime(request.form["tournament_date"], "%Y-%m-%d").date()
            registration_deadline = datetime.strptime(request.form["registration_deadline"], "%Y-%m-%d").date()
            entry_fee = int(request.form["entry_fee"])
            team_limit = int(request.form["team_limit"])
            if not request.form["name"].strip() or registration_deadline > tournament_date or entry_fee < 0 or team_limit < 1:
                raise ValueError
            tournament = Tournament(
                name=request.form["name"].strip(),
                venue_name=request.form["venue_name"].strip(),
                tournament_date=tournament_date,
                registration_deadline=registration_deadline,
                entry_fee=entry_fee,
                prize=request.form["prize"].strip(),
                rules=request.form["rules"].strip(),
                team_limit=team_limit,
                owner_id=session["user_id"],
            )
            db.session.add(tournament)
            db.session.commit()
            flash("Tournament published.", "success")
            return redirect(url_for("main.owner_tournaments"))
        except (KeyError, ValueError):
            db.session.rollback()
            flash("Enter valid tournament details and dates.", "error")
    return render_template("tournament_form.html")


@main_bp.route("/receipts/new", methods=["GET", "POST"])
@login_required
def receipt_scan():
    if request.method == "POST" and request.files.get("receipt"):
        uploaded = request.files["receipt"]
        allowed = {"png", "jpg", "jpeg", "webp"}
        extension = uploaded.filename.rsplit(".", 1)[-1].lower() if uploaded.filename and "." in uploaded.filename else ""
        if extension not in allowed or uploaded.content_type not in {"image/png", "image/jpeg", "image/webp"}:
            flash("Upload a PNG, JPG, JPEG, or WEBP image.", "error")
            return redirect(url_for("main.receipt_scan"))
        original_filename = secure_filename(uploaded.filename)
        stored_filename = f"{uuid4().hex}.{extension}"
        upload_dir = current_app.config["UPLOAD_FOLDER"]
        os.makedirs(upload_dir, mode=0o700, exist_ok=True)
        path = os.path.join(upload_dir, stored_filename)
        uploaded.save(path)
        try:
            raw_text = extract_receipt_text(path)
            extracted = parse_receipt_text(raw_text)
            message = "OCR complete. Review every field before saving."
        except RuntimeError:
            raw_text = ""
            extracted = {}
            message = "OCR is unavailable. Enter receipt details manually."
        return render_template(
            "receipt_scan.html",
            extracted=extracted,
            upload=message,
            stored_filename=stored_filename,
            original_filename=original_filename,
        )
    if request.method == "POST":
        scan = ReceiptScan(
            stored_filename=request.form.get("stored_filename", ""),
            original_filename=request.form.get("original_filename", ""),
            merchant_name=request.form.get("merchant_name", "").strip(),
            transaction_date=request.form.get("transaction_date", "").strip(),
            amount=request.form.get("amount", "").strip(),
            transaction_reference=request.form.get("transaction_reference", "").strip(),
            user_id=session["user_id"],
            ocr_status="not_verified",
        )
        db.session.add(scan)
        db.session.add(
            Notification(
                user_id=session["user_id"],
                title="Receipt details saved",
                message="Receipt information was saved for your records; it does not verify payment.",
                category="payment",
            )
        )
        db.session.commit()
        flash("Receipt details saved. Payment remains unverified.", "success")
        return redirect(url_for("main.dashboard"))
    return render_template("receipt_scan.html", extracted={})


@main_bp.route("/owner/announcements/new", methods=["GET", "POST"])
@role_required("owner", "admin")
def create_announcement():
    user = db.session.get(User, session["user_id"])
    venues = Venue.query.filter_by(owner_id=user.id).all() if user.is_owner else Venue.query.all()
    if request.method == "POST":
        try:
            venue_id = request.form.get("venue_id") or None
            if user.is_owner and (
                not venue_id or int(venue_id) not in {venue.id for venue in venues}
            ):
                raise ValueError
            expires_at = request.form.get("expires_at", "").strip()
            announcement = Announcement(
                title=request.form["title"].strip(),
                body=request.form["body"].strip(),
                category=request.form["category"].strip(),
                expires_at=datetime.strptime(expires_at, "%Y-%m-%d") if expires_at else None,
                venue_id=int(venue_id) if venue_id else None,
                author_id=user.id,
            )
            if not announcement.title or not announcement.body:
                raise ValueError
            db.session.add(announcement)
            db.session.commit()
            flash("Announcement published.", "success")
            return redirect(url_for("main.announcements"))
        except (KeyError, ValueError):
            db.session.rollback()
            flash("Enter valid announcement details.", "error")
    return render_template("announcement_form.html", venues=venues)


@main_bp.get("/admin")
@role_required("admin")
def admin_dashboard():
    user_query = User.query
    if request.args.get("q"):
        term = f"%{request.args['q'].strip()}%"
        user_query = user_query.filter(or_(User.name.ilike(term), User.email.ilike(term)))
    page = max(request.args.get("page", 1, type=int), 1)
    users = user_query.order_by(User.created_at.desc()).paginate(page=page, per_page=10, error_out=False)
    venues = Venue.query.order_by(Venue.id.desc()).all()
    reports = ReviewReport.query.filter_by(status="open").order_by(ReviewReport.created_at.desc()).all()
    stats = {
        "users": User.query.count(),
        "venues": Venue.query.count(),
        "bookings": Booking.query.count(),
        "revenue": db.session.query(db.func.coalesce(db.func.sum(Booking.total_price), 0)).filter(Booking.status != "cancelled").scalar(),
    }
    logs = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(50).all()
    return render_template("admin_dashboard.html", users=users, venues=venues, reports=reports, stats=stats, logs=logs)


@main_bp.post("/admin/venues/<int:venue_id>/approval")
@role_required("admin")
def approve_venue(venue_id):
    venue = db.get_or_404(Venue, venue_id)
    status = request.form.get("status")
    if status not in {"approved", "rejected", "pending"}:
        abort(400)
    venue.approval_status = status
    db.session.add(AuditLog(action=f"venue_{status}", entity_type="venue", entity_id=venue.id, details=venue.name, admin_id=session["user_id"]))
    db.session.commit()
    flash(f"Venue {status}.", "success")
    return redirect(url_for("main.admin_dashboard"))


@main_bp.post("/admin/reviews/<int:review_id>/moderate")
@role_required("admin")
def moderate_review(review_id):
    review = db.get_or_404(Review, review_id)
    status = request.form.get("status")
    if status not in {"published", "hidden"}:
        abort(400)
    review.status = status
    ReviewReport.query.filter_by(review_id=review.id, status="open").update({"status": "resolved"})
    db.session.add(AuditLog(action=f"review_{status}", entity_type="review", entity_id=review.id, admin_id=session["user_id"]))
    db.session.commit()
    return redirect(url_for("main.admin_dashboard"))


@main_bp.post("/admin/users/<int:user_id>/role")
@role_required("admin")
def update_user_role(user_id):
    user = db.get_or_404(User, user_id)
    if user.id == session["user_id"]:
        abort(400)
    if request.form.get("role") not in {"customer", "owner", "admin"}:
        abort(400)
    user.role = request.form["role"]
    db.session.add(AuditLog(action="user_role_updated", entity_type="user", entity_id=user.id, details=user.role, admin_id=session["user_id"]))
    db.session.commit()
    return redirect(url_for("main.admin_dashboard"))


@main_bp.post("/venues/<slug>/favorite")
@login_required
def toggle_favorite(slug):
    venue = Venue.query.filter_by(slug=slug, approval_status="approved").first_or_404()
    favorite = FavoriteVenue.query.filter_by(user_id=session["user_id"], venue_id=venue.id).first()
    if favorite:
        db.session.delete(favorite)
    else:
        db.session.add(FavoriteVenue(user_id=session["user_id"], venue_id=venue.id))
    db.session.commit()
    return redirect(request.referrer or url_for("main.venue_detail", slug=slug))


@main_bp.post("/venues/<slug>/review")
@login_required
def save_review(slug):
    venue = Venue.query.filter_by(slug=slug, approval_status="approved").first_or_404()
    user_id = session["user_id"]
    completed = Booking.query.filter_by(user_id=user_id, venue_id=venue.id, status="completed").first()
    if not completed:
        flash("You can review a venue after a completed booking.", "error")
    elif Review.query.filter_by(user_id=user_id, venue_id=venue.id).first():
        flash("You have already reviewed this venue.", "error")
    else:
        rating = request.form.get("rating", type=int)
        body = request.form.get("body", "").strip()
        if rating not in range(1, 6):
            flash("Rating must be between 1 and 5 stars.", "error")
        else:
            db.session.add(Review(rating=rating, body=body, user_id=user_id, venue_id=venue.id))
            db.session.commit()
            flash("Thanks for rating this futsal.", "success")
    return redirect(url_for("main.venue_detail", slug=slug))


@main_bp.post("/reviews/<int:review_id>/edit")
@login_required
def edit_review(review_id):
    review = db.get_or_404(Review, review_id)
    if review.user_id != session["user_id"]:
        abort(403)
    rating = request.form.get("rating", type=int)
    body = request.form.get("body", "").strip()
    if rating not in range(1, 6) or not body:
        flash("Provide a rating from 1 to 5 and review text.", "error")
    else:
        review.rating = rating
        review.body = body
        review.status = "published"
        db.session.commit()
        flash("Your review was updated.", "success")
    return redirect(url_for("main.venue_detail", slug=review.venue.slug))


@main_bp.post("/reviews/<int:review_id>/delete")
@login_required
def delete_review(review_id):
    review = db.get_or_404(Review, review_id)
    if review.user_id != session["user_id"]:
        abort(403)
    slug = review.venue.slug
    db.session.delete(review)
    db.session.commit()
    flash("Your review was deleted.", "success")
    return redirect(url_for("main.venue_detail", slug=slug))


@main_bp.post("/reviews/<int:review_id>/report")
@login_required
def report_review(review_id):
    review = db.get_or_404(Review, review_id)
    db.session.add(ReviewReport(review_id=review.id, reporter_id=session["user_id"], reason=request.form.get("reason", "Inappropriate content").strip()))
    db.session.commit()
    flash("Review reported to the moderation team.", "success")
    return redirect(request.referrer or url_for("main.index"))
