from pathlib import Path

from flask import Flask
from sqlalchemy import inspect

from config import Config
from .extensions import db
from .security import csrf_token, validate_csrf


def create_app(config_class=Config):
    root_dir = Path(__file__).resolve().parent.parent
    app = Flask(
        __name__,
        template_folder=str(root_dir / "templates"),
        static_folder=str(root_dir / "static"),
    )
    app.config.from_object(config_class)
    db.init_app(app)
    app.jinja_env.globals["csrf_token"] = csrf_token
    app.before_request(validate_csrf)

    from .auth import auth_bp
    from .main import main_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp, url_prefix="/auth")

    with app.app_context():
        db.create_all()
        _upgrade_user_table()
        _upgrade_venue_table()
        _upgrade_approval_column()
        _upgrade_booking_table()
        _upgrade_tournament_table()
        _upgrade_announcement_table()
        from .seed import seed_dashboard_content, seed_venues

        seed_venues()
        seed_dashboard_content()

    return app


def _upgrade_user_table():
    """Add auth columns for development databases created before role support."""
    columns = {column["name"] for column in inspect(db.engine).get_columns("user")}
    with db.engine.begin() as connection:
        if "phone" not in columns:
            connection.exec_driver_sql("ALTER TABLE user ADD COLUMN phone VARCHAR(30) NOT NULL DEFAULT ''")
        if "role" not in columns:
            connection.exec_driver_sql(
                "ALTER TABLE user ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'customer'"
            )


def _upgrade_venue_table():
    columns = {column["name"] for column in inspect(db.engine).get_columns("venue")}
    additions = {
        "distance_km": "FLOAT NOT NULL DEFAULT 2.5",
        "open_time": "VARCHAR(10) NOT NULL DEFAULT '06:00'",
        "close_time": "VARCHAR(10) NOT NULL DEFAULT '22:00'",
        "available_slots": "INTEGER NOT NULL DEFAULT 8",
        "is_open": "BOOLEAN NOT NULL DEFAULT 1",
        "owner_id": "INTEGER",
        "approval_status": "VARCHAR(20) NOT NULL DEFAULT 'approved'",
    }
    with db.engine.begin() as connection:
        for column, definition in additions.items():
            if column not in columns:
                connection.exec_driver_sql(
                    f"ALTER TABLE venue ADD COLUMN {column} {definition}"
                )


def _upgrade_approval_column():
    # Kept as a named migration hook for existing development databases.
    return None


def _upgrade_booking_table():
    columns = {column["name"] for column in inspect(db.engine).get_columns("booking")}
    additions = {
        "booking_reference": "VARCHAR(16)",
        "payment_method": "VARCHAR(30) NOT NULL DEFAULT 'cash_on_arrival'",
        "payment_status": "VARCHAR(30) NOT NULL DEFAULT 'pay_on_arrival'",
    }
    with db.engine.begin() as connection:
        for column, definition in additions.items():
            if column not in columns:
                connection.exec_driver_sql(
                    f"ALTER TABLE booking ADD COLUMN {column} {definition}"
                )
        missing_references = connection.exec_driver_sql(
            "SELECT id FROM booking WHERE booking_reference IS NULL"
        ).fetchall()
        for (booking_id,) in missing_references:
            reference = f"FH-{booking_id:010d}"
            connection.exec_driver_sql(
                "UPDATE booking SET booking_reference = ? WHERE id = ?",
                (reference, booking_id),
            )


def _upgrade_tournament_table():
    columns = {column["name"] for column in inspect(db.engine).get_columns("tournament")}
    additions = {
        "registration_deadline": "DATE",
        "entry_fee": "INTEGER NOT NULL DEFAULT 0",
        "rules": "TEXT NOT NULL DEFAULT ''",
        "owner_id": "INTEGER",
    }
    with db.engine.begin() as connection:
        for column, definition in additions.items():
            if column not in columns:
                connection.exec_driver_sql(
                    f"ALTER TABLE tournament ADD COLUMN {column} {definition}"
                )
        connection.exec_driver_sql(
            "UPDATE tournament SET registration_deadline = tournament_date "
            "WHERE registration_deadline IS NULL"
        )


def _upgrade_announcement_table():
    columns = {column["name"] for column in inspect(db.engine).get_columns("announcement")}
    additions = {
        "expires_at": "DATETIME",
        "venue_id": "INTEGER",
        "author_id": "INTEGER",
    }
    with db.engine.begin() as connection:
        for column, definition in additions.items():
            if column not in columns:
                connection.exec_driver_sql(
                    f"ALTER TABLE announcement ADD COLUMN {column} {definition}"
                )
