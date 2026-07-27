"""Property image upload and management using Cloudinary."""
import os

import cloudinary
import cloudinary.uploader
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt

from app.extensions import db
from app.models import Property, PropertyImage, PropertyVideo

images_bp = Blueprint("images", __name__)

# Cloudinary reads CLOUDINARY_URL from the environment automatically,
# but calling config() explicitly makes that dependency visible here.
cloudinary.config(cloudinary_url=os.environ.get("CLOUDINARY_URL"))


@images_bp.route("/<int:property_id>/images", methods=["POST"])
@jwt_required()
def upload_image(property_id: int):
    """Upload a photo for a property. Landlord (owner) or admin only.

    Expects a multipart/form-data request with a file field named 'image'
    (not JSON — file uploads use a different content type).
    """
    target_property = Property.query.get(property_id)
    if target_property is None:
        return jsonify({"error": "property not found"}), 404

    claims = get_jwt()
    current_user_id = int(get_jwt_identity())
    is_admin = claims.get("role") == "admin"

    if not is_admin and target_property.landlord_id != current_user_id:
        return jsonify({"error": "you can only add images to your own properties"}), 403

    if "image" not in request.files:
        return jsonify({"error": "no image file provided (field name must be 'image')"}), 400

    file = request.files["image"]
    if file.filename == "":
        return jsonify({"error": "no file selected"}), 400

    try:
        upload_result = cloudinary.uploader.upload(file, folder="homespace/properties")
    except Exception as exc:
        return jsonify({"error": f"upload failed: {exc}"}), 502

    image = PropertyImage(
        property_id=property_id,
        image_url=upload_result["secure_url"],
    )
    db.session.add(image)
    db.session.commit()

    return jsonify({
        "message": "image uploaded successfully",
        "image": {"id": image.id, "image_url": image.image_url},
    }), 201


@images_bp.route("/<int:property_id>/images", methods=["GET"])
def list_images(property_id: int):
    """List all images for a property. Public."""
    images = PropertyImage.query.filter_by(property_id=property_id).all()

    return jsonify({
        "count": len(images),
        "images": [{"id": img.id, "image_url": img.image_url} for img in images],
    }), 200


@images_bp.route("/images/<int:image_id>", methods=["DELETE"])
@jwt_required()
def delete_image(image_id: int):
    """Delete a property image. Owner landlord or admin only."""
    image = PropertyImage.query.get(image_id)
    if image is None:
        return jsonify({"error": "image not found"}), 404

    claims = get_jwt()
    current_user_id = int(get_jwt_identity())
    is_admin = claims.get("role") == "admin"

    if not is_admin and image.property.landlord_id != current_user_id:
        return jsonify({"error": "you can only delete images from your own properties"}), 403

    db.session.delete(image)
    db.session.commit()

    return jsonify({"message": "image deleted successfully"}), 200


@images_bp.route("/<int:property_id>/videos", methods=["POST"])
@jwt_required()
def upload_video(property_id: int):
    """Upload a short video tour for a property. Landlord (owner) or admin only.

    Same pattern as image upload, but tells Cloudinary this is a video
    file (resource_type='video') so it's processed/stored correctly.
    """
    target_property = Property.query.get(property_id)
    if target_property is None:
        return jsonify({"error": "property not found"}), 404

    claims = get_jwt()
    current_user_id = int(get_jwt_identity())
    is_admin = claims.get("role") == "admin"

    if not is_admin and target_property.landlord_id != current_user_id:
        return jsonify({"error": "you can only add videos to your own properties"}), 403

    if "video" not in request.files:
        return jsonify({"error": "no video file provided (field name must be 'video')"}), 400

    file = request.files["video"]
    if file.filename == "":
        return jsonify({"error": "no file selected"}), 400

    try:
        upload_result = cloudinary.uploader.upload(
            file,
            folder="homespace/properties/videos",
            resource_type="video",
        )
    except Exception as exc:
        return jsonify({"error": f"upload failed: {exc}"}), 502

    video = PropertyVideo(
        property_id=property_id,
        video_url=upload_result["secure_url"],
    )
    db.session.add(video)
    db.session.commit()

    return jsonify({
        "message": "video uploaded successfully",
        "video": {"id": video.id, "video_url": video.video_url},
    }), 201


@images_bp.route("/<int:property_id>/videos", methods=["GET"])
def list_videos(property_id: int):
    """List all videos for a property. Public."""
    videos = PropertyVideo.query.filter_by(property_id=property_id).all()

    return jsonify({
        "count": len(videos),
        "videos": [{"id": v.id, "video_url": v.video_url} for v in videos],
    }), 200