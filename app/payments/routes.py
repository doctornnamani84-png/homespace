"""Payment initialization and Paystack webhook handling."""
import hashlib
import hmac
import os

import requests
from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.extensions import db
from app.models import Booking, BookingStatus

payments_bp = Blueprint("payments", __name__)

PAYSTACK_BASE_URL = "https://api.paystack.co"


@payments_bp.route("/initialize", methods=["POST"])
@jwt_required()
def initialize_payment():
    print("DEBUG - PAYSTACK_SECRET_KEY:", repr(current_app.config.get("PAYSTACK_SECRET_KEY")))
    data = request.get_json(silent=True) or {}
    ...
    """Start a Paystack transaction for an existing pending booking.

    Expects JSON body: {booking_id}.

    Returns the Paystack authorization_url the frontend should redirect
    the user to in order to complete payment.
    """
    data = request.get_json(silent=True) or {}
    booking_id = data.get("booking_id")

    if not booking_id:
        return jsonify({"error": "booking_id is required"}), 400

    booking = Booking.query.get(booking_id)
    if booking is None:
        return jsonify({"error": "booking not found"}), 404

    current_user_id = int(get_jwt_identity())

    if booking.tenant_id != current_user_id:
        return jsonify({"error": "you can only pay for your own bookings"}), 403

    if booking.status != BookingStatus.PENDING.value:
        return jsonify({"error": f"booking is already '{booking.status}', cannot pay again"}), 409

    secret_key = current_app.config.get("PAYSTACK_SECRET_KEY")
    if not secret_key:
        return jsonify({"error": "payment provider is not configured"}), 503

    amount_kobo = int(float(booking.total_price) * 100)

    tenant_email = booking.tenant.email

    response = requests.post(
        f"{PAYSTACK_BASE_URL}/transaction/initialize",
        headers={"Authorization": f"Bearer {secret_key}"},
        json={
            "email": tenant_email,
            "amount": amount_kobo,
            "metadata": {"booking_id": booking.id},
        },
        timeout=10,
    )

    if response.status_code != 200:
        return jsonify({"error": "failed to initialize payment with Paystack"}), 502

    paystack_data = response.json().get("data", {})

    return jsonify({
        "authorization_url": paystack_data.get("authorization_url"),
        "access_code": paystack_data.get("access_code"),
        "reference": paystack_data.get("reference"),
    }), 200


@payments_bp.route("/webhook", methods=["POST"])
def paystack_webhook():
    """Receive and verify Paystack payment confirmation webhooks.

    Paystack signs every webhook request with an HMAC-SHA512 signature
    in the x-paystack-signature header. We MUST verify this before
    trusting the payload, or anyone could POST a fake "payment successful"
    request and get a free booking confirmed.
    """
    secret_key = current_app.config.get("PAYSTACK_SECRET_KEY", "")
    signature = request.headers.get("x-paystack-signature", "")

    computed_signature = hmac.new(
        secret_key.encode("utf-8"),
        request.data,
        hashlib.sha512,
    ).hexdigest()

    if not hmac.compare_digest(computed_signature, signature):
        return jsonify({"error": "invalid signature"}), 401

    payload = request.get_json(silent=True) or {}
    event = payload.get("event")

    if event == "charge.success":
        booking_id = payload.get("data", {}).get("metadata", {}).get("booking_id")
        booking = Booking.query.get(booking_id) if booking_id else None

        if booking is not None:
            booking.status = BookingStatus.CONFIRMED.value
            db.session.commit()

    return jsonify({"received": True}), 200