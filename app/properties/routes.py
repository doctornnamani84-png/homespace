"""Property listing and search endpoints."""
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt

from app.extensions import db
from app.models import Property
from app.utils import role_required

properties_bp = Blueprint("properties", __name__)


@properties_bp.route("", methods=["POST"])
@jwt_required()
@role_required("landlord")
def create_property():
    """Create a new property listing. Landlord-only.

    Expects JSON body:
        title (str, required)
        description (str, optional)
        location (str, required)
        price_per_night (number, optional — required if is_short_let)
        monthly_rent (number, optional — required if not is_short_let)
        is_short_let (bool, optional, default False)
    """
    data = request.get_json(silent=True) or {}

    title = (data.get("title") or "").strip()
    location = (data.get("location") or "").strip()
    description = data.get("description")
    price_per_night = data.get("price_per_night")
    monthly_rent = data.get("monthly_rent")
    is_short_let = bool(data.get("is_short_let", False))
    video_url = data.get("video_url")
    listing_type = data.get("listing_type", "rent")
    if listing_type not in ("rent", "sale"):
        listing_type = "rent"

    if not title or not location:
        return jsonify({"error": "title and location are required"}), 400

    if listing_type == "sale":
        if monthly_rent is None:
            return jsonify({"error": "price is required for a sale listing"}), 400
    else:
        if price_per_night is None and monthly_rent is None:
            return jsonify({
                "error": "at least one of price_per_night or monthly_rent is required"
            }), 400

    landlord_id = int(get_jwt_identity())

    new_property = Property(
        title=title,
        description=description,
        location=location,
        price_per_night=price_per_night,
        monthly_rent=monthly_rent,
        is_short_let=is_short_let,
        video_url=video_url,
        listing_type=listing_type,
        landlord_id=landlord_id,
    )

    db.session.add(new_property)
    db.session.commit()

    return jsonify({
        "message": "property listed successfully",
        "property": _serialize_property(new_property),
    }), 201


@properties_bp.route("", methods=["GET"])
def list_properties():
    """List properties, with optional filters. Public — no auth required.

    Query params:
        location (str, optional) — case-insensitive partial match
        is_short_let (str, optional) — 'true' or 'false'
        min_price (number, optional)
        max_price (number, optional)
    """
    location = request.args.get("location")
    is_short_let = request.args.get("is_short_let")
    min_price = request.args.get("min_price", type=float)
    max_price = request.args.get("max_price", type=float)

    query = Property.query

    if location:
        query = query.filter(Property.location.ilike(f"%{location}%"))

    if is_short_let is not None:
        wants_short_let = is_short_let.lower() == "true"
        query = query.filter(Property.is_short_let == wants_short_let)
        price_column = Property.price_per_night if wants_short_let else Property.monthly_rent
    else:
        price_column = None

    if min_price is not None:
        if price_column is not None:
            query = query.filter(price_column >= min_price)
        else:
            query = query.filter(
                db.or_(Property.price_per_night >= min_price, Property.monthly_rent >= min_price)
            )

    if max_price is not None:
        if price_column is not None:
            query = query.filter(price_column <= max_price)
        else:
            query = query.filter(
                db.or_(Property.price_per_night <= max_price, Property.monthly_rent <= max_price)
            )

    results = query.order_by(Property.created_at.desc()).all()

    return jsonify({
        "count": len(results),
        "properties": [_serialize_property(p) for p in results],
    }), 200

@properties_bp.route("/<int:property_id>", methods=["PUT"])
@jwt_required()
@role_required("landlord", "admin")
def update_property(property_id: int):
    """Fully replace a property listing's details.

    Landlords may only update their OWN properties. Admins may update
    ANY property — e.g., to fix formatting/details for a landlord who
    isn't comfortable with the platform themselves.
    """
    target_property = Property.query.get(property_id)
    if target_property is None:
        return jsonify({"error": "property not found"}), 404

    claims = get_jwt()
    current_user_id = int(get_jwt_identity())
    is_admin = claims.get("role") == "admin"

    if not is_admin and target_property.landlord_id != current_user_id:
        return jsonify({"error": "you can only edit your own properties"}), 403

    data = request.get_json(silent=True) or {}

    title = (data.get("title") or "").strip()
    location = (data.get("location") or "").strip()
    description = data.get("description")
    price_per_night = data.get("price_per_night")
    monthly_rent = data.get("monthly_rent")
    is_short_let = bool(data.get("is_short_let", False))

    if not title or not location:
        return jsonify({"error": "title and location are required"}), 400

    if price_per_night is None and monthly_rent is None:
        return jsonify({
            "error": "at least one of price_per_night or monthly_rent is required"
        }), 400

    target_property.title = title
    target_property.description = description
    target_property.location = location
    target_property.price_per_night = price_per_night
    target_property.monthly_rent = monthly_rent
    target_property.is_short_let = is_short_let

    db.session.commit()

    return jsonify({
        "message": "property updated successfully",
        "property": _serialize_property(target_property),
    }), 200

@properties_bp.route("/<int:property_id>", methods=["DELETE"])
@jwt_required()
@role_required("admin")
def delete_property(property_id: int):
    """Remove a property listing entirely. Admin-only.

    DELETE means exactly what it says — the resource is permanently
    removed. Unlike our earlier hatchery example in a previous project,
    we're not soft-deleting here; this genuinely erases the row.

    Because Property has cascade="all, delete-orphan" on its bookings
    relationship (set up in models.py), deleting a property also
    deletes any bookings tied to it — worth knowing, since that's a
    real consequence, not a side detail.
    """
    target_property = Property.query.get(property_id)
    if target_property is None:
        return jsonify({"error": "property not found"}), 404

    db.session.delete(target_property)
    db.session.commit()

    return jsonify({
        "message": f"property '{target_property.title}' deleted successfully"
    }), 200


def _serialize_property(prop: Property) -> dict:
    return {
        "id": prop.id,
        "title": prop.title,
        "description": prop.description,
        "location": prop.location,
        "price_per_night": float(prop.price_per_night) if prop.price_per_night else None,
        "monthly_rent": float(prop.monthly_rent) if prop.monthly_rent else None,
        "is_short_let": prop.is_short_let,
        "video_url": prop.video_url,
        "listing_type": prop.listing_type,
        "landlord_id": prop.landlord_id,
        "created_at": prop.created_at.isoformat() if prop.created_at else None,
    }