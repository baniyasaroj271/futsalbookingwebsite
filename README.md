# FutsalHub Nepal

FutsalHub Nepal is a responsive futsal discovery and booking foundation for venues across Nepal. It includes a premium Emerald Ink and Champagne UI, venue discovery, Leaflet/OpenStreetMap mapping, secure user registration/login, role-protected workspaces, profiles, and booking history.

The authenticated dashboard is backed by SQLite records for nearby futsals, stored distance and availability metadata, upcoming bookings, tournaments, and announcements. Search and area/distance filters are applied by Flask before the dashboard is rendered. Searching a recognized area returns approved futsal grounds within 5 km, ordered from nearest to farthest.

Venue detail pages show stored photos, address, coordinates, distance, pricing, facilities, ratings, hours, live Nepal-time status, slots, and upcoming holiday or maintenance closures. Owners can edit their assigned venue's details and schedule at `/owner/venues/<slug>/edit`; admins can edit any venue.

Maps use Leaflet with the OpenStreetMap tile API by default. The tile endpoint and required attribution are configurable with `MAP_TILE_URL` and `MAP_ATTRIBUTION` in `.env`, allowing a hosted tile provider to be used later without changing the application code. Keep the provider's attribution and usage limits when switching providers.

Bookings receive a unique reference, support cash on arrival (`payment_method` is intentionally extensible for future eSewa/Khalti adapters), and can be cancelled by customers or venue owners. Server-side interval checks run inside a SQLite write transaction to reject overlapping active bookings.

Tournaments are available at `/tournaments`, with deadline/capacity/duplicate registration checks. Owners and admins can publish tournaments and announcements from their protected workspaces. New owner venues remain `pending` until an admin approves them; only approved venues appear in public search or accept bookings. Announcement publication and expiry dates are stored in SQLite, and booking/tournament/receipt events create user notifications.

Owners have an approval-aware dashboard for their venues, bookings, tournaments, and announcements. Administrators have a protected dashboard for venue approval, user role management, reported-review moderation, booking statistics, pagination, and audit-log review.

Customers can favorite venues and review venues after a completed booking. Reviews are limited to one per customer and venue, average ratings are calculated from published database reviews, and customers can edit or delete their own review or report inappropriate content. Admin moderation resolves open reports.

Receipt scanning is optional. Install `requirements-ocr.txt` and the Tesseract system binary to enable it. Uploads are limited to 5 MB, restricted to image extensions and MIME types, stored outside the public static directory under randomized filenames, and saved as `not_verified`; OCR output is editable and is never treated as proof of payment.

## Run locally

1. Create and activate a virtual environment:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

2. Install dependencies:

   ```powershell
   pip install -r requirements.txt
   ```

   The `tzdata` dependency supplies the IANA timezone database required by `zoneinfo` on Windows.

3. Copy `.env.example` to `.env` and set a secure `SECRET_KEY` for anything beyond local development.

4. Start the development server:

   ```powershell
   py run.py
   ```

Open http://127.0.0.1:5000. The SQLite database (`futsalhub.db`) and sample venues are initialized automatically on first run.

## Project structure

- `app/__init__.py` — Flask application factory and database initialization
- `app/models.py` — SQLAlchemy models for users, venues, bookings, tournaments, announcements, notifications, receipts, reviews, favorites, and audit logs
- `app/auth.py` — registration, login, and logout routes
- `app/security.py` — CSRF protection, login guards, and role guards
- `app/main.py` — venue discovery, map data, booking, and dashboard routes
- `app/ocr.py` — optional receipt text extraction with Tesseract
- `templates/` — reusable Jinja layouts and page templates
- `static/` — responsive CSS and Leaflet/map navigation JavaScript
- `tests/` — focused application smoke and booking tests

The models use SQLAlchemy rather than SQLite-specific queries, keeping the persistence layer ready for a future MySQL connection by changing `DATABASE_URL`. Receipt OCR is available through `app.ocr.extract_receipt_text` when the optional `pytesseract`, Pillow, and system Tesseract packages are installed; `TESSERACT_CMD` points to the executable on Windows.

## Authentication and roles

Registration collects name, email, phone number, and an 8-character minimum password. Email addresses are normalized and unique, passwords are stored with Werkzeug hashing, and new accounts default to the `customer` role. Existing development databases are upgraded with the phone and role columns automatically.

The `owner` role can access `/owner`, while `admin` can access both `/owner` and `/admin`. Role assignment is intentionally not exposed in public registration; administrators can update roles from the admin dashboard. Owners are restricted to their own venues, bookings, tournaments, and venue announcements, while all admin actions are backend-protected and audited.

All state-changing forms require a session-bound CSRF token. Sessions are HTTP-only, use SameSite Lax cookies, are permanent for seven days after authentication, and can be marked Secure with `SESSION_COOKIE_SECURE=1` behind HTTPS. Logout is POST-only.

Run tests with:

```powershell
pytest
```
