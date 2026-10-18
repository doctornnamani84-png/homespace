"""Property listing and search endpoints."""
from datetime import datetime

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt

from app.extensions import db, limiter
from app.seo import property_page_url
from app.models import Favorite, Property, PropertyReport, PropertyReview, User
from app.utils import role_required

properties_bp = Blueprint("properties", __name__)


@properties_bp.route("", methods=["POST"])
@jwt_required()
@role_required("landlord", "admin")
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
    bedrooms, bedrooms_error = _parse_bedrooms(data.get("bedrooms"))
    amenities, amenities_error = _parse_amenities(data.get("amenities"))
    latitude, longitude, coordinates_error = _parse_coordinates(
        data.get("latitude"), data.get("longitude")
    )
    listing_type = data.get("listing_type", "rent")
    if listing_type not in ("rent", "sale"):
        listing_type = "rent"
    price_negotiable = listing_type == "sale" and bool(data.get("price_negotiable", False))

    if not title or not location:
        return jsonify({"error": "title and location are required"}), 400
    if bedrooms_error or amenities_error or coordinates_error:
        return jsonify({"error": bedrooms_error or amenities_error or coordinates_error}), 400

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
        price_negotiable=price_negotiable,
        bedrooms=bedrooms,
        amenities="|".join(amenities),
        latitude=latitude,
        longitude=longitude,
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
    listing_type = request.args.get("listing_type")
    min_price = request.args.get("min_price", type=float)
    max_price = request.args.get("max_price", type=float)
    min_bedrooms = request.args.get("min_bedrooms", type=int)
    requested_amenities = _split_amenities(request.args.get("amenities", ""))
    sort_by = request.args.get("sort_by", "newest")

    if listing_type not in (None, "rent", "sale"):
        return jsonify({"error": "listing_type must be 'rent' or 'sale'"}), 400
    if sort_by not in {"newest", "price_asc", "price_desc"}:
        return jsonify({"error": "sort_by must be 'newest', 'price_asc', or 'price_desc'"}), 400
    if min_bedrooms is not None and min_bedrooms < 0:
        return jsonify({"error": "min_bedrooms cannot be negative"}), 400
    if min_price is not None and min_price < 0 or max_price is not None and max_price < 0:
        return jsonify({"error": "price filters cannot be negative"}), 400

    query = Property.query

    if location:
        query = query.filter(Property.location.ilike(f"%{location}%"))

    if min_bedrooms is not None:
        query = query.filter(Property.bedrooms >= min_bedrooms)

    for amenity in requested_amenities:
        escaped_amenity = amenity.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        query = query.filter(
            Property.amenities.ilike(f"%|{escaped_amenity}|%", escape="\\")
        )

    if listing_type is not None:
        query = query.filter(Property.listing_type == listing_type)

    if listing_type == "sale":
        price_column = Property.monthly_rent
    elif is_short_let is not None:
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

    if sort_by == "newest":
        query = query.order_by(Property.created_at.desc(), Property.id.desc())
    else:
        price_value = db.func.coalesce(Property.price_per_night, Property.monthly_rent)
        direction = price_value.asc() if sort_by == "price_asc" else price_value.desc()
        query = query.order_by(direction, Property.id.desc())
    results = query.all()
    review_rows = db.session.query(
        PropertyReview.property_id,
        db.func.avg(PropertyReview.rating),
        db.func.count(PropertyReview.id),
    ).group_by(PropertyReview.property_id).all()
    review_summary = {
        property_id: {"average_rating": round(float(average), 1), "review_count": count}
        for property_id, average, count in review_rows
    }

    return jsonify({
        "count": len(results),
        "properties": [
            _serialize_property(p, review_summary.get(p.id)) for p in results
        ],
    }), 200


@properties_bp.route("/favorites", methods=["GET"])
@jwt_required()
def list_favorites():
    user_id = int(get_jwt_identity())
    favorites = (
        Favorite.query.filter_by(user_id=user_id)
        .order_by(Favorite.created_at.desc())
        .all()
    )
    property_ids = [favorite.property_id for favorite in favorites]
    properties = (
        Property.query.filter(Property.id.in_(property_ids)).all()
        if property_ids else []
    )
    by_id = {prop.id: prop for prop in properties}
    return jsonify({
        "count": len(properties),
        "properties": [
            _serialize_property(by_id[property_id])
            for property_id in property_ids if property_id in by_id
        ],
    }), 200


@properties_bp.route("/favorites/<int:property_id>", methods=["PUT", "DELETE"])
@jwt_required()
def update_favorite(property_id: int):
    user_id = int(get_jwt_identity())
    target_property = db.session.get(Property, property_id)
    if target_property is None:
        return jsonify({"error": "property not found"}), 404

    favorite = Favorite.query.filter_by(
        user_id=user_id, property_id=property_id
    ).first()
    if request.method == "PUT":
        if favorite is None:
            db.session.add(Favorite(user_id=user_id, property_id=property_id))
            db.session.commit()
        return jsonify({"message": "property saved", "is_favorite": True}), 200

    if favorite is not None:
        db.session.delete(favorite)
        db.session.commit()
    return jsonify({"message": "property removed from saved listings", "is_favorite": False}), 200


@properties_bp.route("/<int:property_id>/reports", methods=["POST"])
@jwt_required()
@limiter.limit("5 per hour")
def report_property(property_id: int):
    target_property = db.session.get(Property, property_id)
    if target_property is None:
        return jsonify({"error": "property not found"}), 404
    reporter_id = int(get_jwt_identity())
    if target_property.landlord_id == reporter_id:
        return jsonify({"error": "you cannot report your own listing"}), 403

    data = request.get_json(silent=True) or {}
    reason = data.get("reason")
    details = (data.get("details") or "").strip()
    allowed_reasons = {"incorrect_information", "suspected_scam", "duplicate", "other"}
    if not isinstance(reason, str) or reason not in allowed_reasons:
        return jsonify({"error": "select a valid report reason"}), 400
    if len(details) > 1200:
        return jsonify({"error": "report details must be 1200 characters or fewer"}), 400

    report = PropertyReport(
        reporter_id=reporter_id,
        property_id=property_id,
        reason=reason,
        details=details,
    )
    db.session.add(report)
    db.session.commit()
    return jsonify({"message": "report submitted for review", "report_id": report.id}), 201


@properties_bp.route("/reports", methods=["GET"])
@jwt_required()
@role_required("admin")
def list_property_reports():
    reports = PropertyReport.query.order_by(PropertyReport.created_at.desc()).all()
    return jsonify({
        "count": len(reports),
        "reports": [_serialize_report(report) for report in reports],
    }), 200


@properties_bp.route("/reports/<int:report_id>", methods=["PATCH"])
@jwt_required()
@role_required("admin")
def update_property_report(report_id: int):
    report = db.session.get(PropertyReport, report_id)
    if report is None:
        return jsonify({"error": "report not found"}), 404
    data = request.get_json(silent=True) or {}
    status = data.get("status")
    if not isinstance(status, str) or status not in {"reviewed", "dismissed"}:
        return jsonify({"error": "status must be 'reviewed' or 'dismissed'"}), 400
    report.status = status
    report.reviewed_at = datetime.utcnow()
    report.reviewed_by_id = int(get_jwt_identity())
    db.session.commit()
    return jsonify({"message": "report updated", "report": _serialize_report(report)}), 200

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

    listing_type = data.get("listing_type", "rent")
    if listing_type not in ("rent", "sale"):
        listing_type = "rent"
    price_negotiable = listing_type == "sale" and bool(data.get("price_negotiable", False))

    if not title or not location:
        return jsonify({"error": "title and location are required"}), 400

    if price_per_night is None and monthly_rent is None:
        return jsonify({
            "error": "at least one of price_per_night or monthly_rent is required"
        }), 400

    bedrooms, bedrooms_error = _parse_bedrooms(data.get("bedrooms"))
    amenities, amenities_error = _parse_amenities(data.get("amenities"))
    latitude, longitude, coordinates_error = _parse_coordinates(
        data.get("latitude"), data.get("longitude")
    )
    if bedrooms_error or amenities_error or coordinates_error:
        return jsonify({"error": bedrooms_error or amenities_error or coordinates_error}), 400
    target_property.title = title
    target_property.description = description
    target_property.location = location
    target_property.price_per_night = price_per_night
    target_property.monthly_rent = monthly_rent
    target_property.is_short_let = is_short_let
    target_property.listing_type = listing_type
    target_property.price_negotiable = price_negotiable
    target_property.bedrooms = bedrooms
    target_property.amenities = "|".join(amenities)
    target_property.latitude = latitude
    target_property.longitude = longitude


    db.session.commit()

    return jsonify({
        "message": "property updated successfully",
        "property": _serialize_property(target_property),
    }), 200


VERIFICATION_STATUSES = {"unverified", "pending", "verified", "rejected"}


@properties_bp.route("/verification-queue", methods=["GET"])
@jwt_required()
@role_required("admin")
def list_verification_queue():
    properties = Property.query.order_by(Property.created_at.desc()).all()
    return jsonify({
        "count": len(properties),
        "properties": [
            {
                "id": prop.id,
                "title": prop.title,
                "owner_name": prop.landlord.name,
                "owner_phone_number": prop.landlord.phone_number,
                "identity_verification_status": prop.landlord.identity_verification_status,
                "phone_verification_status": prop.landlord.phone_verification_status,
                "ownership_verification_status": prop.ownership_verification_status,
            }
            for prop in properties
        ],
    }), 200


@properties_bp.route("/<int:property_id>/verification", methods=["PATCH"])
@jwt_required()
@role_required("admin")
def update_property_verification(property_id: int):
    target_property = db.session.get(Property, property_id)
    if target_property is None:
        return jsonify({"error": "property not found"}), 404

    data = request.get_json(silent=True) or {}
    status_fields = {
        "identity_verification_status": (
            target_property.landlord,
            "identity_verification_reviewed_at",
            "identity_verification_reviewed_by_id",
        ),
        "phone_verification_status": (
            target_property.landlord,
            "phone_verification_reviewed_at",
            "phone_verification_reviewed_by_id",
        ),
        "ownership_verification_status": (
            target_property,
            "ownership_verification_reviewed_at",
            "ownership_verification_reviewed_by_id",
        ),
    }
    if not data or set(data) - set(status_fields):
        return jsonify({"error": "provide one or more valid verification statuses"}), 400

    for field, value in data.items():
        if not isinstance(value, str) or value not in VERIFICATION_STATUSES:
            return jsonify({"error": f"invalid status for {field}"}), 400
        if field == "phone_verification_status" and value == "verified":
            if not target_property.landlord.phone_number:
                return jsonify({"error": "add an owner phone number before verifying it"}), 400

    admin_id = int(get_jwt_identity())
    reviewed_at = datetime.utcnow()
    for field, value in data.items():
        entity, reviewed_at_field, reviewed_by_field = status_fields[field]
        setattr(entity, field, value)
        setattr(entity, reviewed_at_field, reviewed_at)
        setattr(entity, reviewed_by_field, admin_id)

    db.session.commit()
    return jsonify({"message": "verification status updated"}), 200

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


def _serialize_property(prop: Property, review_summary: dict | None = None) -> dict:
    review_summary = review_summary or {"average_rating": None, "review_count": 0}
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
        "price_negotiable": prop.price_negotiable,
        "bedrooms": prop.bedrooms,
        "amenities": _split_amenities(prop.amenities),
        "latitude": prop.latitude,
        "longitude": prop.longitude,
        "ownership_verification_status": prop.ownership_verification_status,
        "owner_identity_verified": prop.landlord.identity_verification_status == "verified",
        "owner_phone_verified": prop.landlord.phone_verification_status == "verified",
        "ownership_documents_verified": prop.ownership_verification_status == "verified",
        "page_url": property_page_url(prop.id, prop.title),
        "average_rating": review_summary["average_rating"],
        "review_count": review_summary["review_count"],
        "landlord_id": prop.landlord_id,
        "created_at": prop.created_at.isoformat() if prop.created_at else None,
        "updated_at": prop.updated_at.isoformat() if prop.updated_at else None,
    }


def _split_amenities(value) -> list[str]:
    if isinstance(value, list):
        values = value
    elif isinstance(value, str):
        values = value.split(",") if "," in value else value.split("|")
    else:
        values = []
    return list(dict.fromkeys(
        item.strip() for item in values
        if isinstance(item, str) and item.strip()
    ))


def _parse_bedrooms(value) -> tuple[int | None, str | None]:
    if value in (None, ""):
        return None, None
    try:
        bedrooms = int(value)
    except (TypeError, ValueError):
        return None, "bedrooms must be a whole number"
    if bedrooms < 0 or bedrooms > 50:
        return None, "bedrooms must be between 0 and 50"
    return bedrooms, None


def _parse_amenities(value) -> tuple[list[str], str | None]:
    amenities = _split_amenities(value)
    if len(amenities) > 30 or any(len(item) > 60 for item in amenities):
        return [], "provide at most 30 amenities, each 60 characters or fewer"
    return amenities, None


def _parse_coordinates(latitude_value, longitude_value):
    if latitude_value in (None, "") and longitude_value in (None, ""):
        return None, None, None
    try:
        latitude = float(latitude_value)
        longitude = float(longitude_value)
    except (TypeError, ValueError):
        return None, None, "latitude and longitude must both be valid numbers"
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        return None, None, "coordinates are outside the valid latitude/longitude range"
    return latitude, longitude, None


def _serialize_report(report: PropertyReport) -> dict:
    return {
        "id": report.id,
        "property_id": report.property_id,
        "property_title": report.property.title,
        "property_location": report.property.location,
        "reporter_name": report.reporter.name,
        "reason": report.reason,
        "details": report.details,
        "status": report.status,
        "created_at": report.created_at.isoformat() if report.created_at else None,
    }