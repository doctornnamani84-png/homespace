import hashlib
import hmac
import json
from datetime import date, timedelta
from decimal import Decimal

import pytest
from flask_jwt_extended import create_access_token

from app import create_app
from app.extensions import db
from app.models import Booking, BookingStatus, Property, PropertyVideo, User


@pytest.fixture
def app():
	application = create_app("testing")
	application.config["PAYSTACK_SECRET_KEY"] = "test-paystack-secret"
	with application.app_context():
		db.create_all()
		yield application
		db.session.remove()
		db.drop_all()


@pytest.fixture
def property_data(app):
	landlord = User(name="Host", email="host@example.com", password_hash="unused")
	tenant = User(name="Guest", email="guest@example.com", password_hash="unused")
	db.session.add_all([landlord, tenant])
	db.session.flush()

	short_let = Property(
		title="Short stay",
		location="Enugu",
		price_per_night=Decimal("100.00"),
		is_short_let=True,
		listing_type="rent",
		landlord_id=landlord.id,
	)
	monthly_rental = Property(
		title="Monthly rental",
		location="Enugu",
		monthly_rent=Decimal("900.00"),
		is_short_let=False,
		listing_type="rent",
		landlord_id=landlord.id,
	)
	sale = Property(
		title="Property for sale",
		location="Enugu",
		monthly_rent=Decimal("5000.00"),
		is_short_let=False,
		listing_type="sale",
		landlord_id=landlord.id,
	)
	db.session.add_all([short_let, monthly_rental, sale])
	db.session.commit()

	token = create_access_token(
		identity=str(tenant.id), additional_claims={"role": "tenant"}
	)
	landlord_token = create_access_token(
		identity=str(landlord.id), additional_claims={"role": "landlord"}
	)
	return {
		"short_let_id": short_let.id,
		"monthly_rental_id": monthly_rental.id,
		"sale_id": sale.id,
		"token": token,
		"landlord_token": landlord_token,
	}


def date_range():
	start = date.today() + timedelta(days=30)
	end = start + timedelta(days=2)
	return start.isoformat(), end.isoformat()


def auth_headers(property_data):
	return {"Authorization": f"Bearer {property_data['token']}"}


def create_booking(client, property_data):
	start_date, end_date = date_range()
	return client.post(
		"/api/bookings",
		json={
			"property_id": property_data["short_let_id"],
			"start_date": start_date,
			"end_date": end_date,
		},
		headers=auth_headers(property_data),
	)


def test_quote_and_booking_include_itemized_platform_fee(app, property_data):
	client = app.test_client()
	start_date, end_date = date_range()
	quote_response = client.get(
		"/api/bookings/quote",
		query_string={
			"property_id": property_data["short_let_id"],
			"start_date": start_date,
			"end_date": end_date,
		},
	)

	assert quote_response.status_code == 200
	assert quote_response.json["quote"] == {
		"nights": 2,
		"subtotal": 200.0,
		"platform_fee": 10.0,
		"platform_fee_rate": 5,
		"total": 210.0,
		"currency": "NGN",
	}

	booking_response = create_booking(client, property_data)
	assert booking_response.status_code == 201
	assert booking_response.json["booking"]["subtotal"] == 200.0
	assert booking_response.json["booking"]["platform_fee"] == 10.0
	assert booking_response.json["booking"]["total_price"] == 210.0


def test_guest_can_only_book_short_lets(app, property_data):
	client = app.test_client()
	start_date, end_date = date_range()

	for property_id in (property_data["monthly_rental_id"], property_data["sale_id"]):
		response = client.post(
			"/api/bookings",
			json={
				"property_id": property_id,
				"start_date": start_date,
				"end_date": end_date,
			},
			headers=auth_headers(property_data),
		)
		assert response.status_code == 422


def test_guest_can_view_own_booking_history(app, property_data):
	client = app.test_client()
	assert create_booking(client, property_data).status_code == 201

	response = client.get("/api/bookings/mine", headers=auth_headers(property_data))

	assert response.status_code == 200
	assert response.json["count"] == 1
	assert response.json["bookings"][0]["property_title"] == "Short stay"
	assert response.json["bookings"][0]["property_location"] == "Enugu"


def test_paystack_initialization_charges_fee_and_saves_reference(
	app, property_data, monkeypatch
):
	client = app.test_client()
	booking_response = create_booking(client, property_data)
	booking_id = booking_response.json["booking"]["id"]
	request_data = {}

	class FakePaystackResponse:
		status_code = 200

		@staticmethod
		def json():
			return {
				"data": {
					"authorization_url": "https://checkout.example/pay",
					"reference": "pay_ref_test",
				}
			}

	def fake_post(url, **kwargs):
		request_data.update(kwargs)
		return FakePaystackResponse()

	monkeypatch.setattr("app.payments.routes.requests.post", fake_post)
	response = client.post(
		"/api/payments/initialize",
		json={"booking_id": booking_id},
		headers=auth_headers(property_data),
	)

	assert response.status_code == 200
	assert request_data["json"]["amount"] == 21000
	assert request_data["json"]["currency"] == "NGN"
	booking = db.session.get(Booking, booking_id)
	assert booking.paystack_reference == "pay_ref_test"


def test_webhook_requires_matching_reference_amount_and_currency(app, property_data):
	client = app.test_client()
	booking_response = create_booking(client, property_data)
	booking_id = booking_response.json["booking"]["id"]
	booking = db.session.get(Booking, booking_id)
	booking.paystack_reference = "pay_ref_test"
	db.session.commit()

	payload = {
		"event": "charge.success",
		"data": {
			"metadata": {"booking_id": booking_id},
			"reference": "pay_ref_test",
			"amount": 20999,
			"currency": "NGN",
		},
	}
	raw_payload = json.dumps(payload, separators=(",", ":")).encode()
	signature = hmac.new(
		b"test-paystack-secret", raw_payload, hashlib.sha512
	).hexdigest()
	headers = {"x-paystack-signature": signature, "Content-Type": "application/json"}

	mismatch_response = client.post("/api/payments/webhook", data=raw_payload, headers=headers)
	assert mismatch_response.status_code == 400
	assert booking.status == BookingStatus.PENDING.value

	payload["data"]["amount"] = 21000
	raw_payload = json.dumps(payload, separators=(",", ":")).encode()
	headers["x-paystack-signature"] = hmac.new(
		b"test-paystack-secret", raw_payload, hashlib.sha512
	).hexdigest()
	confirmed_response = client.post("/api/payments/webhook", data=raw_payload, headers=headers)

	assert confirmed_response.status_code == 200
	assert db.session.get(Booking, booking_id).status == BookingStatus.CONFIRMED.value


def test_property_search_filters_listing_and_short_let_type(app, property_data):
	client = app.test_client()

	response = client.get(
		"/api/properties",
		query_string={
			"listing_type": "rent",
			"is_short_let": "true",
			"min_price": 50,
			"max_price": 150,
		},
	)

	assert response.status_code == 200
	assert response.json["count"] == 1
	assert response.json["properties"][0]["title"] == "Short stay"


def test_only_completed_confirmed_guest_can_review_and_rating_is_listed(
	app, property_data
):
	client = app.test_client()
	booking_response = create_booking(client, property_data)
	booking = db.session.get(Booking, booking_response.json["booking"]["id"])
	booking.start_date = date.today() - timedelta(days=4)
	booking.end_date = date.today() - timedelta(days=2)
	booking.status = BookingStatus.CONFIRMED.value
	db.session.commit()

	review_response = client.post(
		f"/api/bookings/{booking.id}/review",
		json={"rating": 5, "comment": "Clean, comfortable, and exactly as listed."},
		headers=auth_headers(property_data),
	)

	assert review_response.status_code == 201
	duplicate_response = client.post(
		f"/api/bookings/{booking.id}/review",
		json={"rating": 4, "comment": "Submitting twice should fail."},
		headers=auth_headers(property_data),
	)
	assert duplicate_response.status_code == 409

	property_response = client.get("/api/properties")
	listed_property = next(
		item for item in property_response.json["properties"]
		if item["id"] == property_data["short_let_id"]
	)
	assert listed_property["average_rating"] == 5.0
	assert listed_property["review_count"] == 1


def test_property_can_show_multiple_videos_and_owner_can_delete_one(
	app, property_data, monkeypatch
):
	first_video = PropertyVideo(
		property_id=property_data["short_let_id"],
		video_url="https://res.cloudinary.com/test/video/upload/v123456/homespace/first.mp4",
		cloudinary_public_id="homespace/first",
	)
	legacy_video = PropertyVideo(
		property_id=property_data["short_let_id"],
		video_url="https://res.cloudinary.com/test/video/upload/v123456/homespace/legacy.mp4",
	)
	db.session.add_all([first_video, legacy_video])
	db.session.commit()
	first_video_id = first_video.id
	legacy_video_id = legacy_video.id
	destroyed_assets = []

	def fake_destroy(public_id, **kwargs):
		destroyed_assets.append((public_id, kwargs))
		return {"result": "ok"}

	monkeypatch.setattr("app.properties.image_routes.cloudinary.uploader.destroy", fake_destroy)
	client = app.test_client()

	list_response = client.get(
		f"/api/properties/{property_data['short_let_id']}/videos"
	)
	assert list_response.status_code == 200
	assert list_response.json["count"] == 2

	denied_response = client.delete(
		f"/api/properties/videos/{first_video_id}",
		headers=auth_headers(property_data),
	)
	assert denied_response.status_code == 403
	assert destroyed_assets == []

	delete_response = client.delete(
		f"/api/properties/videos/{legacy_video_id}",
		headers={"Authorization": f"Bearer {property_data['landlord_token']}"},
	)
	assert delete_response.status_code == 200
	assert destroyed_assets == [
		("homespace/legacy", {"resource_type": "video", "invalidate": True})
	]
	remaining_response = client.get(
		f"/api/properties/{property_data['short_let_id']}/videos"
	)
	assert [video["id"] for video in remaining_response.json["videos"]] == [first_video_id]


def test_sale_listing_accepts_price_above_100_million_and_negotiability(
	app, property_data
):
	response = app.test_client().post(
		"/api/properties",
		json={
			"title": "High-value property",
			"location": "Enugu",
			"listing_type": "sale",
			"monthly_rent": 1_000_000_000.99,
			"price_negotiable": True,
		},
		headers={"Authorization": f"Bearer {property_data['landlord_token']}"},
	)

	assert response.status_code == 201
	assert response.json["property"]["monthly_rent"] == 1_000_000_000.99
	assert response.json["property"]["price_negotiable"] is True
