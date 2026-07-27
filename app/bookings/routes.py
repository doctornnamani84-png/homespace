"""Booking creation endpoints, including double-booking prevention."""
from datetime import date, datetime

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.extensions import db
from app.models import Booking, Property, BookingStatus, UnavailableDate
from app.utils import role_required

bookings_bp = Blueprint("bookings", __name__)


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

    total_price = _calculate_total_price(target_property, start_date, end_date)
    if total_price is None:
        return jsonify({
            "error": "this property does not have a price configured for this booking type"
        }), 422

    tenant_id = int(get_jwt_identity())

    booking = Booking(
        property_id=property_id,
        tenant_id=tenant_id,
        start_date=start_date,
        end_date=end_date,
        total_price=total_price,
        status=BookingStatus.PENDING.value,
    )
    db.session.add(booking)
    db.session.commit()

    return jsonify({
        "message": "booking request created successfully",
        "booking": _serialize_booking(booking),
    }), 201


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



def _calculate_total_price(prop: Property, start_date: date, end_date: date) -> float | None:
    """Compute the total price for a booking based on the property's rate.

    Short-let properties are billed per night; long-term rentals here are
    treated as billed at the flat monthly_rent regardless of exact date
    span (a simplification — refine once lease-length rules are defined).
    """
    nights = (end_date - start_date).days

    if prop.is_short_let and prop.price_per_night is not None:
        return float(prop.price_per_night) * nights

    if not prop.is_short_let and prop.monthly_rent is not None:
        return float(prop.monthly_rent)

    return None


def _serialize_booking(booking: Booking) -> dict:
    """Convert a Booking model instance into a JSON-serializable dict."""
    return {
        "id": booking.id,
        "property_id": booking.property_id,
        "tenant_id": booking.tenant_id,
        "start_date": booking.start_date.isoformat(),
        "end_date": booking.end_date.isoformat(),
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