"""Authentication endpoints: registration and login."""
from flask import Blueprint, jsonify, request
from flask_jwt_extended import create_access_token, create_refresh_token

from app.extensions import db, bcrypt
from app.models import User, UserRole

auth_bp = Blueprint("auth", __name__)


def hash_password(plain_password: str) -> str:
    """Hash a plaintext password for storage.

    Args:
        plain_password: The user's raw password.

    Returns:
        A bcrypt hash suitable for storing in the database.
    """
    return bcrypt.generate_password_hash(plain_password).decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Check a plaintext password against a stored hash.

    Args:
        plain_password: The password submitted at login.
        password_hash: The hash stored in the database.

    Returns:
        True if the password matches, False otherwise.
    """
    return bcrypt.check_password_hash(password_hash, plain_password)


@auth_bp.route("/register", methods=["POST"])
def register():
    """Register a new user.

    Expects JSON body: {name, email, password, role}.
    `role` must be one of 'tenant' or 'landlord' (not 'admin' —
    admin accounts should be created separately, not via public signup).
    """
    data = request.get_json(silent=True) or {}

    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    role = (data.get("role") or UserRole.TENANT.value).strip().lower()

    if not name or not email or not password:
        return jsonify({"error": "name, email, and password are required"}), 400

    if role not in (UserRole.TENANT.value, UserRole.LANDLORD.value):
        return jsonify({"error": "role must be 'tenant' or 'landlord'"}), 400

    if len(password) < 6:
        return jsonify({"error": "password must be at least 6 characters"}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({"error": "an account with that email already exists"}), 409

    user = User(
        name=name,
        email=email,
        password_hash=hash_password(password),
        role=role,
    )
    db.session.add(user)
    db.session.commit()

    return jsonify({
        "message": "account created successfully",
        "user": {"id": user.id, "name": user.name, "email": user.email, "role": user.role},
    }), 201


@auth_bp.route("/login", methods=["POST"])
def login():
    """Authenticate a user and issue JWT access + refresh tokens.

    Expects JSON body: {email, password}.
    """
    data = request.get_json(silent=True) or {}

    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not email or not password:
        return jsonify({"error": "email and password are required"}), 400

    user = User.query.filter_by(email=email).first()

    if not user or not verify_password(password, user.password_hash):
        return jsonify({"error": "invalid email or password"}), 401

    # Include role in the token's identity claims so protected routes
    # can check permissions without an extra database lookup.
    additional_claims = {"role": user.role}
    access_token = create_access_token(identity=str(user.id), additional_claims=additional_claims)
    refresh_token = create_refresh_token(identity=str(user.id), additional_claims=additional_claims)
    
    return jsonify({
        "access_token": access_token,
        "refresh_token": refresh_token,
        "user": {"id": user.id, "name": user.name, "email": user.email, "role": user.role},
    }), 200