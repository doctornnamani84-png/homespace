"""Landlord-managed unavailable date ranges for a property."""
from datetime import date, datetime

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt

from app.extensions import db
from app.models import Property, UnavailableDate

availability_bp = Blueprint("availability", __name__)


def _parse_date(value: str) -> date | None:
    """Parse a 'YYYY-MM-DD' string into a date object, or None if invalid."""
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


@availability_bp.route("/<int:property_id>/block", methods=["POST"])
@jwt_required()
def block_dates(property_id: int):
    """Block a date range on a property (e.g., for maintenance).

    Landlords may only block their own properties. Admins may block any.
    """
    target_property = Property.query.get(property_id)
    if target_property is None:
        return jsonify({"error": "property not found"}), 404

    claims = get_jwt()
    current_user_id = int(get_jwt_identity())
    is_admin = claims.get("role") == "admin"

    if not is_admin and target_property.landlord_id != current_user_id:
        return jsonify({"error": "you can only block dates on your own properties"}), 403

    data = request.get_json(silent=True) or {}
    start_date = _parse_date(data.get("start_date"))
    end_date = _parse_date(data.get("end_date"))
    reason = data.get("reason")

    if not start_date or not end_date:
        return jsonify({"error": "start_date and end_date are required (YYYY-MM-DD)"}), 400

    if end_date <= start_date:
        return jsonify({"error": "end_date must be after start_date"}), 400

    block = UnavailableDate(
        property_id=property_id,
        start_date=start_date,
        end_date=end_date,
        reason=reason,
    )
    db.session.add(block)
    db.session.commit()

    return jsonify({
        "message": "dates blocked successfully",
        "block": {
            "id": block.id,
            "property_id": block.property_id,
            "start_date": block.start_date.isoformat(),
            "end_date": block.end_date.isoformat(),
            "reason": block.reason,
        },
    }), 201


@availability_bp.route("/<int:property_id>/blocks", methods=["GET"])
def list_blocks(property_id: int):
    """List all blocked date ranges for a property. Public — tenants need
    to see this too, so they know which dates aren't available."""
    blocks = UnavailableDate.query.filter_by(property_id=property_id).all()

    return jsonify({
        "count": len(blocks),
        "blocks": [
            {
                "id": b.id,
                "start_date": b.start_date.isoformat(),
                "end_date": b.end_date.isoformat(),
                "reason": b.reason,
            }
            for b in blocks
        ],
    }), 200


@availability_bp.route("/blocks/<int:block_id>", methods=["DELETE"])
@jwt_required()
def unblock_dates(block_id: int):
    """Remove a previously blocked date range."""
    block = UnavailableDate.query.get(block_id)
    if block is None:
        return jsonify({"error": "block not found"}), 404

    claims = get_jwt()
    current_user_id = int(get_jwt_identity())
    is_admin = claims.get("role") == "admin"

    if not is_admin and block.property.landlord_id != current_user_id:
        return jsonify({"error": "you can only unblock dates on your own properties"}), 403

    db.session.delete(block)
    db.session.commit()

    return jsonify({"message": "block removed successfully"}), 200