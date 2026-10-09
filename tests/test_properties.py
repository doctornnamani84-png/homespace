from pathlib import Path

import pytest

from app import create_app
from app.extensions import db
from app.models import Property, User, UserRole
from flask_jwt_extended import create_access_token


@pytest.fixture
def app():
    application = create_app("testing")
    with application.app_context():
        db.create_all()
        landlord = User(
            name="HomeSpace Host",
            email="seo-host@example.com",
            password_hash="unused",
            role=UserRole.LANDLORD.value,
            phone_number="+2348012345678",
        )
        db.session.add(landlord)
        db.session.flush()
        listing = Property(
            title="New Haven Short-let Apartment",
            description="A bright short-let apartment close to central Enugu.",
            location="New Haven, Enugu",
            price_per_night=25000,
            is_short_let=True,
            listing_type="rent",
            landlord_id=landlord.id,
        )
        db.session.add(listing)
        db.session.commit()
        yield application
        db.session.remove()
        db.drop_all()

def test_upload_video_form_is_connected_to_frontend_submit_handler():
    script = Path(__file__).resolve().parents[1] / "frontend" / "script.js"
    source = script.read_text(encoding="utf-8")

    assert 'document.getElementById("upload-video-form")' in source
    assert 'formData.append("video", file);' in source


def test_property_detail_page_has_listing_metadata_and_content(app):
    response = app.test_client().get("/property/1/new-haven-short-let-apartment")

    assert response.status_code == 200
    assert b"New Haven Short-let Apartment in New Haven, Enugu | HomeSpace" in response.data
    assert b"name=\"description\"" in response.data
    assert b"rel=\"canonical\"" in response.data
    assert b"NGN 25,000.00 per night" in response.data


def test_sitemap_and_robots_include_canonical_property_discovery(app):
    client = app.test_client()
    sitemap_response = client.get("/sitemap.xml")
    robots_response = client.get("/robots.txt")

    assert sitemap_response.status_code == 200
    assert b"/property/1/new-haven-short-let-apartment" in sitemap_response.data
    assert robots_response.status_code == 200
    assert b"Sitemap: https://www.homespace.ng/sitemap.xml" in robots_response.data


def test_public_property_data_shows_verification_without_phone_number(app):
    response = app.test_client().get("/api/properties")

    assert response.status_code == 200
    property_data = response.json["properties"][0]
    assert property_data["owner_identity_verified"] is False
    assert property_data["owner_phone_verified"] is False
    assert property_data["ownership_documents_verified"] is False
    assert property_data["updated_at"]
    assert "owner_phone_number" not in property_data


def test_admin_can_update_verification_statuses(app):
    with app.app_context():
        admin = User(
            name="HomeSpace Admin",
            email="verification-admin@example.com",
            password_hash="unused",
            role=UserRole.ADMIN.value,
        )
        db.session.add(admin)
        db.session.commit()
        token = create_access_token(
            identity=str(admin.id), additional_claims={"role": UserRole.ADMIN.value}
        )

    client = app.test_client()
    response = client.patch(
        "/api/properties/1/verification",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "identity_verification_status": "verified",
            "phone_verification_status": "verified",
            "ownership_verification_status": "verified",
        },
    )

    assert response.status_code == 200
    property_data = client.get("/api/properties").json["properties"][0]
    assert property_data["owner_identity_verified"] is True
    assert property_data["owner_phone_verified"] is True
    assert property_data["ownership_documents_verified"] is True
    detail = client.get("/property/1/new-haven-short-let-apartment")
    assert b"Owner identity: Verified" in detail.data
    assert b"Ownership documents: Reviewed" in detail.data


def test_non_admin_cannot_update_verification_statuses(app):
    with app.app_context():
        landlord = User.query.filter_by(email="seo-host@example.com").one()
        token = create_access_token(
            identity=str(landlord.id), additional_claims={"role": UserRole.LANDLORD.value}
        )

    response = app.test_client().patch(
        "/api/properties/1/verification",
        headers={"Authorization": f"Bearer {token}"},
        json={"ownership_verification_status": "verified"},
    )

    assert response.status_code == 403
