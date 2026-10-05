"""Public, crawlable property pages and search-engine discovery routes."""
import re
import unicodedata
import xml.etree.ElementTree as ET

from flask import Blueprint, Response, abort, current_app, redirect, render_template

from app.extensions import db
from app.models import Property, PropertyReview

seo_bp = Blueprint("seo", __name__)
SITEMAP_NAMESPACE = "http://www.sitemaps.org/schemas/sitemap/0.9"


def slugify(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_value.lower()).strip("-") or "property"


def property_page_url(property_id: int, title: str) -> str:
    base_url = current_app.config["PUBLIC_BASE_URL"].rstrip("/")
    return f"{base_url}/property/{property_id}/{slugify(title)}"


@seo_bp.route("/property/<int:property_id>/<slug>")
def property_detail(property_id: int, slug: str):
    listing = db.session.get(Property, property_id)
    if listing is None:
        abort(404)

    expected_slug = slugify(listing.title)
    if slug != expected_slug:
        return redirect(property_page_url(listing.id, listing.title), code=301)

    canonical_url = property_page_url(listing.id, listing.title)
    if listing.listing_type == "sale":
        price_text = f"Asking price: NGN {listing.monthly_rent:,.2f}"
        property_type = "Property for sale"
    elif listing.is_short_let:
        price_text = f"NGN {listing.price_per_night:,.2f} per night"
        property_type = "Short-let stay"
    else:
        price_text = f"NGN {listing.monthly_rent:,.2f} per month"
        property_type = "Monthly rental"

    description = " ".join((listing.description or "").split())
    if description:
        description = description[:155].rsplit(" ", 1)[0]
    else:
        description = f"Explore {listing.title} in {listing.location} on HomeSpace."

    average_rating, review_count = db.session.query(
        db.func.avg(PropertyReview.rating), db.func.count(PropertyReview.id)
    ).filter(PropertyReview.property_id == listing.id).one()

    return render_template(
        "property_detail.html",
        listing=listing,
        title=f"{listing.title} in {listing.location} | HomeSpace",
        description=description,
        canonical_url=canonical_url,
        price_text=price_text,
        property_type=property_type,
        average_rating=round(float(average_rating), 1) if average_rating is not None else None,
        review_count=review_count,
    )


@seo_bp.route("/sitemap.xml")
def sitemap():
    namespace = f"{{{SITEMAP_NAMESPACE}}}"
    root = ET.Element(f"{namespace}urlset")
    base_url = current_app.config["PUBLIC_BASE_URL"].rstrip("/")
    urls = [f"{base_url}/", f"{base_url}/terms.html", f"{base_url}/privacy.html"]
    urls.extend(
        property_page_url(listing.id, listing.title)
        for listing in Property.query.order_by(Property.id).all()
    )

    for page_url in urls:
        url_node = ET.SubElement(root, f"{namespace}url")
        ET.SubElement(url_node, f"{namespace}loc").text = page_url

    xml = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    return Response(xml, content_type="application/xml; charset=utf-8")


@seo_bp.route("/robots.txt")
def robots_txt():
    base_url = current_app.config["PUBLIC_BASE_URL"].rstrip("/")
    body = f"User-agent: *\nAllow: /\nDisallow: /api/\nSitemap: {base_url}/sitemap.xml\n"
    return Response(body, content_type="text/plain; charset=utf-8")