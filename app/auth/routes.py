"""Authentication endpoints: registration, email verification, and login."""
import smtplib
import ssl
from email.message import EmailMessage

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import create_access_token, create_refresh_token
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.extensions import db, bcrypt, limiter

from app.models import User, UserRole

auth_bp = Blueprint("auth", __name__)
EMAIL_VERIFICATION_SALT = "homespace-email-verification"


def _verification_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(
        current_app.config["SECRET_KEY"], salt=EMAIL_VERIFICATION_SALT
    )


def _send_verification_email(user: User) -> None:
    mail_server = current_app.config.get("MAIL_SERVER")
    mail_sender = current_app.config.get("MAIL_DEFAULT_SENDER")
    if not mail_server or not mail_sender:
        raise RuntimeError("email delivery is not configured")

    token = _verification_serializer().dumps({"user_id": user.id, "email": user.email})
    verify_url = (
        f"{current_app.config['PUBLIC_BASE_URL'].rstrip('/')}/verify-email.html"
        f"?token={token}"
    )
    message = EmailMessage()
    message["Subject"] = "Verify your HomeSpace email"
    message["From"] = mail_sender
    message["To"] = user.email
    message.set_content(
        f"Hello {user.name},\n\n"
        "Please verify your email address to activate your HomeSpace account. "
        "This link expires in 24 hours.\n\n"
        f"{verify_url}\n\n"
        "If you did not create this account, you can ignore this email."
    )

    mail_port = current_app.config["MAIL_PORT"]
    with smtplib.SMTP(mail_server, mail_port, timeout=15) as smtp:
        if current_app.config["MAIL_USE_TLS"]:
            smtp.starttls(context=ssl.create_default_context())
        if current_app.config.get("MAIL_USERNAME"):
            smtp.login(
                current_app.config["MAIL_USERNAME"],
                current_app.config.get("MAIL_PASSWORD", ""),
            )
        smtp.send_message(message)


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
@limiter.limit("5 per hour")
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

    if "@" not in email or "." not in email.split("@")[-1]:
        return jsonify({"error": "please enter a valid email address"}), 400

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
        email_verified=False,
    )
    db.session.add(user)
    db.session.commit()

    try:
        _send_verification_email(user)
    except (OSError, smtplib.SMTPException, RuntimeError) as exc:
        current_app.logger.warning(
            "Verification email send failed for user %s (%s)",
            user.id,
            type(exc).__name__,
        )
        return jsonify({
            "error": "account created, but the verification email could not be sent. Check email settings or use resend verification."
        }), 503

    return jsonify({
        "message": "account created. Check your email for a verification link before logging in.",
        "user": {"id": user.id, "name": user.name, "email": user.email, "role": user.role},
    }), 201


@auth_bp.route("/verify-email", methods=["POST"])
@limiter.limit("20 per hour")
def verify_email():
    data = request.get_json(silent=True) or {}
    token = data.get("token")
    if not token:
        return jsonify({"error": "verification token is required"}), 400

    try:
        token_data = _verification_serializer().loads(
            token, max_age=current_app.config["EMAIL_VERIFICATION_MAX_AGE"]
        )
        user_id = int(token_data["user_id"])
        email = token_data["email"]
    except (BadSignature, SignatureExpired, TypeError, ValueError, KeyError):
        return jsonify({"error": "verification link is invalid or expired"}), 400

    user = db.session.get(User, user_id)
    if user is None or user.email != email:
        return jsonify({"error": "verification link is invalid or expired"}), 400
    if not user.email_verified:
        user.email_verified = True
        db.session.commit()

    return jsonify({"message": "email verified. You can now log in."}), 200


@auth_bp.route("/resend-verification", methods=["POST"])
@limiter.limit("3 per hour")
def resend_verification():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    user = User.query.filter_by(email=email).first() if email else None
    if user is not None and not user.email_verified:
        try:
            _send_verification_email(user)
        except (OSError, smtplib.SMTPException, RuntimeError) as exc:
            current_app.logger.warning(
                "Verification email resend failed for user %s (%s)",
                user.id,
                type(exc).__name__,
            )
            return jsonify({"error": "verification email could not be sent. Please try again later."}), 503

    return jsonify({
        "message": "If an unverified account exists for that email, a verification link has been sent."
    }), 200


@auth_bp.route("/login", methods=["POST"])
@limiter.limit("10 per minute")
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
    if not user.email_verified:
        return jsonify({
            "error": "verify your email before logging in",
            "email_verification_required": True,
        }), 403

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