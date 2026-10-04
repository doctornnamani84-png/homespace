"""Booking creation endpoints, including double-booking prevention."""
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.extensions import db
from app.models import Booking, Property, BookingStatus, PropertyReview, UnavailableDate
from app.utils import role_required

bookings_bp = Blueprint("bookings", __name__)
PLATFORM_FEE_RATE = Decimal("0.05")
CENT = Decimal("0.01")


def _parse_date(value: str) -> date | None:
    """Parse a 'YYYY-MM-DD' string into a date object, or None if invalid."""
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _has_overlap(property_id: int, start_date: date, end_date: date) -> bool:
    """Check whether a proposed date range overlaps a CONFIRMED (paid)
    booking OR a landlord-blocked maintenance/unavailable range.

    Pending (unpaid) bookings do NOT block dates — otherwise someone
    who starts a booking but never completes payment would permanently
    lock those dates out for everyone else.
    """
    conflicting_booking = Booking.query.filter(
        Booking.property_id == property_id,
        Booking.status == BookingStatus.CONFIRMED.value,
        Booking.start_date < end_date,
        Booking.end_date > start_date,
    ).first()

    if conflicting_booking is not None:
        return True

    conflicting_block = UnavailableDate.query.filter(
        UnavailableDate.property_id == property_id,
        UnavailableDate.start_date < end_date,
        UnavailableDate.end_date > start_date,
    ).first()

    return conflicting_block is not None


def _booking_amounts(prop: Property, start_date: date, end_date: date):
    if prop.listing_type == "sale" or not prop.is_short_let:
        return None

    nights = (end_date - start_date).days
    if prop.price_per_night is None:
        return None
    subtotal = Decimal(str(prop.price_per_night)) * nights

    subtotal = subtotal.quantize(CENT, rounding=ROUND_HALF_UP)
    platform_fee = (subtotal * PLATFORM_FEE_RATE).quantize(CENT, rounding=ROUND_HALF_UP)
    return subtotal, platform_fee, subtotal + platform_fee


@bookings_bp.route("/quote", methods=["GET"])
def quote_booking():
    property_id = request.args.get("property_id", type=int)
    start_date = _parse_date(request.args.get("start_date"))
    end_date = _parse_date(request.args.get("end_date"))

    if not property_id or not start_date or not end_date:
        return jsonify({"error": "property_id, start_date, and end_date are required (dates as YYYY-MM-DD)"}), 400
    if end_date <= start_date:
        return jsonify({"error": "end_date must be after start_date"}), 400
    if start_date < date.today():
        return jsonify({"error": "start_date cannot be in the past"}), 400

    target_property = Property.query.get(property_id)
    if target_property is None:
        return jsonify({"error": "property not found"}), 404
    if _has_overlap(property_id, start_date, end_date):
        return jsonify({"error": "this property is unavailable for the selected dates"}), 409

    amounts = _booking_amounts(target_property, start_date, end_date)
    if amounts is None:
        return jsonify({"error": "only short-let properties can be booked online"}), 422

    subtotal, platform_fee, total = amounts
    return jsonify({
        "quote": {
            "nights": (end_date - start_date).days,
            "subtotal": float(subtotal),
            "platform_fee": float(platform_fee),
            "platform_fee_rate": 5,
            "total": float(total),
            "currency": "NGN",
        },
    }), 200

@bookings_bp.route("", methods=["POST"])
@jwt_required()
@role_required("tenant")
def create_booking():
    """Create a booking request for a property. Tenant-only.

    Expects JSON body:
        property_id (int, required)
        start_date (str 'YYYY-MM-DD', required)
        end_date (str 'YYYY-MM-DD', required)

    total_price is computed server-side from the property's rate —
    never trust a client-submitted price for something involving money.
    """
    data = request.get_json(silent=True) or {}

    property_id = data.get("property_id")
    start_date = _parse_date(data.get("start_date"))
    end_date = _parse_date(data.get("end_date"))

    if not property_id or not start_date or not end_date:
        return jsonify({
            "error": "property_id, start_date, and end_date are required (dates as YYYY-MM-DD)"
        }), 400

    if end_date <= start_date:
        return jsonify({"error": "end_date must be after start_date"}), 400

    if start_date < date.today():
        return jsonify({"error": "start_date cannot be in the past"}), 400

    target_property = Property.query.get(property_id)
    if target_property is None:
        return jsonify({"error": "property not found"}), 404

    if _has_overlap(property_id, start_date, end_date):
        return jsonify({
            "error": "this property is already booked for part or all of the requested dates"
        }), 409

    amounts = _booking_amounts(target_property, start_date, end_date)
    if amounts is None:
        return jsonify({
            "error": "this property cannot be booked for this booking type"
        }), 422
    _, platform_fee, total_price = amounts

    tenant_id = int(get_jwt_identity())

    booking = Booking(
        property_id=property_id,
        tenant_id=tenant_id,
        start_date=start_date,
        end_date=end_date,
        total_price=total_price,
        platform_fee=platform_fee,
        status=BookingStatus.PENDING.value,
    )
    db.session.add(booking)
    db.session.commit()

    return jsonify({
        "message": "booking request created successfully",
        "booking": _serialize_booking(booking),
    }), 201


@bookings_bp.route("/mine", methods=["GET"])
@jwt_required()
@role_required("tenant")
def list_my_bookings():
    tenant_id = int(get_jwt_identity())
    bookings = Booking.query.filter_by(tenant_id=tenant_id).order_by(Booking.created_at.desc()).all()
    return jsonify({
        "count": len(bookings),
        "bookings": [_serialize_booking_with_details(booking) for booking in bookings],
    }), 200


@bookings_bp.route("/<int:booking_id>/review", methods=["POST"])
@jwt_required()
@role_required("tenant")
def review_booking(booking_id: int):
    tenant_id = int(get_jwt_identity())
    booking = db.session.get(Booking, booking_id)
    if booking is None:
        return jsonify({"error": "booking not found"}), 404
    if booking.tenant_id != tenant_id:
        return jsonify({"error": "you can only review your own bookings"}), 403
    if booking.status != BookingStatus.CONFIRMED.value or booking.end_date >= date.today():
        return jsonify({"error": "reviews are available after a confirmed stay has ended"}), 409
    if booking.review is not None:
        return jsonify({"error": "you have already reviewed this stay"}), 409

    data = request.get_json(silent=True) or {}
    try:
        rating = int(data.get("rating"))
    except (TypeError, ValueError):
        rating = 0
    comment = (data.get("comment") or "").strip()
    if not 1 <= rating <= 5:
        return jsonify({"error": "rating must be between 1 and 5"}), 400
    if not comment or len(comment) > 1200:
        return jsonify({"error": "comment must be between 1 and 1200 characters"}), 400

    review = PropertyReview(
        booking_id=booking.id,
        property_id=booking.property_id,
        rating=rating,
        comment=comment,
    )
    db.session.add(review)
    db.session.commit()
    return jsonify({"message": "review submitted", "rating": review.rating}), 201


@bookings_bp.route("/<int:booking_id>/cancel", methods=["PATCH"])
@jwt_required()
@role_required("admin")
def cancel_booking(booking_id: int):
    """Cancel a booking. Admin-only.

    PATCH is the right verb here because we're updating ONE field
    (status) on an existing resource, not replacing the whole booking
    or creating a new one.
    """
    booking = Booking.query.get(booking_id)
    if booking is None:
        return jsonify({"error": "booking not found"}), 404

    if booking.status == BookingStatus.CANCELLED.value:
        return jsonify({"error": "booking is already cancelled"}), 409

    booking.status = BookingStatus.CANCELLED.value
    db.session.commit()

    return jsonify({
        "message": "booking cancelled successfully",
        "booking": _serialize_booking_with_details(booking),
    }), 200



def _serialize_booking(booking: Booking) -> dict:
    """Convert a Booking model instance into a JSON-serializable dict."""
    return {
        "id": booking.id,
        "property_id": booking.property_id,
        "tenant_id": booking.tenant_id,
        "start_date": booking.start_date.isoformat(),
        "end_date": booking.end_date.isoformat(),
        "subtotal": float(booking.total_price - booking.platform_fee),
        "platform_fee": float(booking.platform_fee),
        "total_price": float(booking.total_price),
        "status": booking.status,
        "payout_status": booking.payout_status,
        "created_at": booking.created_at.isoformat() if booking.created_at else None,
    }

@bookings_bp.route("/all", methods=["GET"])
@jwt_required()
@role_required("admin")
def list_all_bookings():
    """List every booking on the platform. Admin-only.

    Returns bookings with basic tenant and property info attached,
    so the admin dashboard doesn't need separate lookups per row.
    """
    bookings = Booking.query.order_by(Booking.created_at.desc()).all()

    return jsonify({
        "count": len(bookings),
        "bookings": [_serialize_booking_with_details(b) for b in bookings],
    }), 200


def _serialize_booking_with_details(booking: Booking) -> dict:
    """Serialize a booking with related tenant name/email and property title."""
    base = _serialize_booking(booking)
    base["tenant_name"] = booking.tenant.name if booking.tenant else None
    base["tenant_email"] = booking.tenant.email if booking.tenant else None
    base["property_title"] = booking.property.title if booking.property else None
    base["property_location"] = booking.property.location if booking.property else None
    base["review_submitted"] = booking.review is not None
    return base 

@bookings_bp.route("/<int:booking_id>/mark-paid-out", methods=["PATCH"])
@jwt_required()
@role_required("admin")
def mark_paid_out(booking_id: int):
    """Mark a booking's landlord payout as completed. Admin-only.

    This is purely a record-keeping flag for you (the admin) to track
    which landlords you've already manually paid — Paystack settlement
    to your account and paying the landlord their share happens outside
    this system for now (manual bank transfer).
    """
    booking = Booking.query.get(booking_id)
    if booking is None:
        return jsonify({"error": "booking not found"}), 404

    if booking.status != BookingStatus.CONFIRMED.value:
        return jsonify({"error": "only confirmed (paid) bookings can be marked as paid out"}), 409

    booking.payout_status = "paid_out"
    db.session.commit()

    return jsonify({
        "message": "booking marked as paid out",
        "booking": _serialize_booking_with_details(booking),
    }), 200       