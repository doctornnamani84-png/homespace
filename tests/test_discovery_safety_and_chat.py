import pytest
from flask_jwt_extended import create_access_token

from app import create_app
from app.extensions import db
from app.models import Property, PropertyReport, User, UserRole


@pytest.fixture
def app():
    application = create_app("testing")
    with application.app_context():
        db.create_all()
        landlord = User(
            name="Property Host",
            email="discovery-host@example.com",
            password_hash="unused",
            role=UserRole.LANDLORD.value,
        )
        guest = User(
            name="Property Guest",
            email="discovery-guest@example.com",
            password_hash="unused",
            role=UserRole.TENANT.value,
        )
        admin = User(
            name="Safety Admin",
            email="discovery-admin@example.com",
            password_hash="unused",
            role=UserRole.ADMIN.value,
        )
        db.session.add_all([landlord, guest, admin])
        db.session.flush()
        listing = Property(
            title="Garden Apartment",
            description="Wi-Fi and secure parking are included.",
            location="Enugu",
            price_per_night=25000,
            is_short_let=True,
            listing_type="rent",
            bedrooms=2,
            amenities="|Wi-Fi|Secure parking|",
            latitude=6.4584,
            longitude=7.5464,
            landlord_id=landlord.id,
        )
        db.session.add(listing)
        db.session.commit()
        application.config["FEATURE_TEST_IDS"] = {
            "property": listing.id,
            "landlord": landlord.id,
            "guest": guest.id,
            "admin": admin.id,
        }
        yield application
        db.session.remove()
        db.drop_all()


def auth_headers(user_id, role):
    token = create_access_token(
        identity=str(user_id), additional_claims={"role": role}
    )
    return {"Authorization": f"Bearer {token}"}


def test_favorites_are_persisted_and_idempotent(app):
    client = app.test_client()
    ids = app.config["FEATURE_TEST_IDS"]
    headers = auth_headers(ids["guest"], "tenant")

    first_save = client.put(
        f"/api/properties/favorites/{ids['property']}", headers=headers
    )
    repeated_save = client.put(
        f"/api/properties/favorites/{ids['property']}", headers=headers
    )
    saved = client.get("/api/properties/favorites", headers=headers)

    assert first_save.status_code == 200
    assert repeated_save.status_code == 200
    assert saved.json["count"] == 1
    assert saved.json["properties"][0]["title"] == "Garden Apartment"

    removed = client.delete(
        f"/api/properties/favorites/{ids['property']}", headers=headers
    )
    assert removed.status_code == 200
    assert client.get("/api/properties/favorites", headers=headers).json["count"] == 0


def test_search_filters_bedrooms_amenities_and_sort_order(app):
    ids = app.config["FEATURE_TEST_IDS"]
    with app.app_context():
        landlord_id = ids["landlord"]
        db.session.add(
            Property(
                title="Smaller House",
                location="Enugu",
                monthly_rent=100000,
                listing_type="rent",
                bedrooms=1,
                amenities="|Wi-Fi|",
                landlord_id=landlord_id,
            )
        )
        db.session.commit()

    response = app.test_client().get(
        "/api/properties",
        query_string={
            "min_bedrooms": 2,
            "amenities": "Wi-Fi,Secure parking",
            "sort_by": "price_asc",
        },
    )

    assert response.status_code == 200
    assert response.json["count"] == 1
    property_data = response.json["properties"][0]
    assert property_data["bedrooms"] == 2
    assert property_data["amenities"] == ["Wi-Fi", "Secure parking"]
    assert property_data["latitude"] == pytest.approx(6.4584)


def test_listing_metadata_can_be_created_and_invalid_update_is_rejected(app):
    client = app.test_client()
    ids = app.config["FEATURE_TEST_IDS"]
    headers = auth_headers(ids["landlord"], "landlord")
    created = client.post(
        "/api/properties",
        json={
            "title": "Coordinate-ready home",
            "location": "Enugu",
            "monthly_rent": 150000,
            "bedrooms": 3,
            "amenities": ["Balcony", "Water"],
            "latitude": 6.45,
            "longitude": 7.55,
        },
        headers=headers,
    )

    assert created.status_code == 201
    created_property = created.json["property"]
    assert created_property["bedrooms"] == 3
    assert created_property["amenities"] == ["Balcony", "Water"]
    assert created_property["latitude"] == pytest.approx(6.45)

    invalid_update = client.put(
        f"/api/properties/{created_property['id']}",
        json={
            "title": "Should not be saved",
            "location": "Enugu",
            "monthly_rent": 150000,
            "latitude": 92,
            "longitude": 7.55,
        },
        headers=headers,
    )
    assert invalid_update.status_code == 400
    unchanged_property = next(
        item
        for item in client.get("/api/properties").json["properties"]
        if item["id"] == created_property["id"]
    )
    assert unchanged_property["title"] == "Coordinate-ready home"


def test_property_report_can_be_reviewed_by_admin(app):
    client = app.test_client()
    ids = app.config["FEATURE_TEST_IDS"]
    report_response = client.post(
        f"/api/properties/{ids['property']}/reports",
        json={
            "reason": "incorrect_information",
            "details": "The advertised parking is not available.",
        },
        headers=auth_headers(ids["guest"], "tenant"),
    )

    assert report_response.status_code == 201
    reports = client.get(
        "/api/properties/reports", headers=auth_headers(ids["admin"], "admin")
    )
    assert reports.status_code == 200
    report_id = reports.json["reports"][0]["id"]
    assert reports.json["reports"][0]["status"] == "open"

    reviewed = client.patch(
        f"/api/properties/reports/{report_id}",
        json={"status": "reviewed"},
        headers=auth_headers(ids["admin"], "admin"),
    )
    assert reviewed.status_code == 200
    with app.app_context():
        assert db.session.get(PropertyReport, report_id).status == "reviewed"


def test_property_owner_cannot_report_own_listing(app):
    client = app.test_client()
    ids = app.config["FEATURE_TEST_IDS"]
    response = client.post(
        f"/api/properties/{ids['property']}/reports",
        json={"reason": "other", "details": ""},
        headers=auth_headers(ids["landlord"], "landlord"),
    )
    assert response.status_code == 403


def test_chatbot_uses_anthropic_and_returns_grounded_response(app, monkeypatch):
    app.config["ANTHROPIC_API_KEY"] = "test-key"
    captured = {}

    class FakeResponse:
        @staticmethod
        def raise_for_status():
            return None

        @staticmethod
        def json():
            return {"content": [{"type": "text", "text": "The listing includes Wi-Fi."}]}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return FakeResponse()

    monkeypatch.setattr("app.chatbot.routes.requests.post", fake_post)
    ids = app.config["FEATURE_TEST_IDS"]
    response = app.test_client().post(
        "/api/chat",
        json={"property_id": ids["property"], "question": "Is Wi-Fi included?"},
    )

    assert response.status_code == 200
    assert response.json["answer"] == "The listing includes Wi-Fi."
    assert captured["url"].endswith("/v1/messages")
    assert "Wi-Fi and secure parking" in captured["json"]["messages"][0]["content"]
    assert "only the listing facts" in captured["json"]["system"]


def test_chatbot_reports_unconfigured_provider_explicitly(app):
    response = app.test_client().post(
        "/api/chat",
        json={
            "property_id": app.config["FEATURE_TEST_IDS"]["property"],
            "question": "Is Wi-Fi included?",
        },
    )
    assert response.status_code == 503
    assert response.json["error"] == "property Q&A is not configured yet"
