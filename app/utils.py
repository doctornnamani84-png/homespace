"""Shared utility decorators for route protection."""
from functools import wraps
from typing import Callable

from flask import jsonify
from flask_jwt_extended import get_jwt, jwt_required


def role_required(*allowed_roles: str) -> Callable:
    """Restrict a route to users holding one of the given roles.

    Must be used together with @jwt_required() — this decorator reads
    the 'role' claim we embedded in the JWT at login time, so it does
    NOT need a database lookup to check permissions.

    Usage:
        @properties_bp.route('/properties', methods=['POST'])
        @jwt_required()
        @role_required('landlord')
        def create_property():
            ...

    Args:
        *allowed_roles: One or more role strings that may access the route.

    Returns:
        A decorator that enforces the role check before the view runs.
    """
    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            claims = get_jwt()
            user_role = claims.get("role")

            if user_role not in allowed_roles:
                return jsonify({
                    "error": f"this action requires one of these roles: {', '.join(allowed_roles)}"
                }), 403

            return fn(*args, **kwargs)
        return wrapper
    return decorator