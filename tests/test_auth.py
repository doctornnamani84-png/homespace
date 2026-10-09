import pytest

from app import create_app
from app.auth.routes import _verification_serializer, hash_password
from app.extensions import db
from app.models import User, UserRole
from flask_jwt_extended import create_access_token


@pytest.fixture
def app():
	application = create_app("testing")
	with application.app_context():
		db.create_all()
		yield application
		db.session.remove()
		db.drop_all()


def test_new_account_must_verify_email_before_login(app, monkeypatch):
	monkeypatch.setattr("app.auth.routes._send_verification_email", lambda user: None)
	client = app.test_client()
	registration = client.post(
		"/api/auth/register",
		json={
			"name": "New Tenant",
			"email": "new-tenant@example.com",
			"password": "a-long-test-password",
			"role": "tenant",
			"phone_number": "+2348012345678",
		},
	)
	assert registration.status_code == 201
	assert User.query.filter_by(email="new-tenant@example.com").one().phone_number == "+2348012345678"

	login_payload = {
		"email": "new-tenant@example.com",
		"password": "a-long-test-password",
	}
	blocked_login = client.post("/api/auth/login", json=login_payload)
	assert blocked_login.status_code == 403
	assert blocked_login.json["email_verification_required"] is True

	user = User.query.filter_by(email=login_payload["email"]).one()
	token = _verification_serializer().dumps({"user_id": user.id, "email": user.email})
	verification = client.post("/api/auth/verify-email", json={"token": token})
	assert verification.status_code == 200
	assert user.email_verified is True

	successful_login = client.post("/api/auth/login", json=login_payload)
	assert successful_login.status_code == 200
	assert successful_login.json["access_token"]


def test_existing_accounts_remain_verified_by_default(app):
	user = User(
		name="Existing Landlord",
		email="existing-landlord@example.com",
		password_hash=hash_password("a-long-test-password"),
		role=UserRole.LANDLORD.value,
	)
	db.session.add(user)
	db.session.commit()

	response = app.test_client().post(
		"/api/auth/login",
		json={"email": user.email, "password": "a-long-test-password"},
	)

	assert response.status_code == 200


def test_resend_verification_does_not_disclose_unknown_email(app, monkeypatch):
	user = User(
		name="Unverified Tenant",
		email="unverified@example.com",
		password_hash=hash_password("a-long-test-password"),
		role=UserRole.TENANT.value,
		email_verified=False,
	)
	db.session.add(user)
	db.session.commit()
	sent_to = []
	monkeypatch.setattr(
		"app.auth.routes._send_verification_email",
		lambda target: sent_to.append(target.email),
	)
	client = app.test_client()

	existing_response = client.post(
		"/api/auth/resend-verification",
		json={"email": "unverified@example.com"},
	)
	unknown_response = client.post(
		"/api/auth/resend-verification",
		json={"email": "unknown@example.com"},
	)

	assert existing_response.status_code == 200
	assert existing_response.json == unknown_response.json
	assert sent_to == ["unverified@example.com"]


def test_invalid_verification_token_is_rejected(app):
	response = app.test_client().post(
		"/api/auth/verify-email", json={"token": "not-a-valid-token"}
	)

	assert response.status_code == 400


def test_user_phone_update_resets_previous_verification(app):
	user = User(
		name="Existing Landlord",
		email="phone-owner@example.com",
		password_hash=hash_password("a-long-test-password"),
		role=UserRole.LANDLORD.value,
		phone_number="+2348011111111",
		phone_verification_status="verified",
	)
	db.session.add(user)
	db.session.commit()
	with app.app_context():
		token = create_access_token(identity=str(user.id))

	response = app.test_client().put(
		"/api/auth/phone",
		headers={"Authorization": f"Bearer {token}"},
		json={"phone_number": "+2348022222222"},
	)

	assert response.status_code == 200
	assert response.json["phone_verification_status"] == "unverified"
	assert db.session.get(User, user.id).phone_number == "+2348022222222"
