"""AI chatbot endpoint for answering guest questions about a property."""
import os

from flask import Blueprint, current_app, jsonify, request

from app.models import Property

chatbot_bp = Blueprint("chatbot", __name__)


@chatbot_bp.route("", methods=["POST"])
def chat():
    """Answer a guest's question about a specific property using an LLM.

    Expects JSON body:
        property_id (int, required)
        question (str, required)
    """
    data = request.get_json(silent=True) or {}

    property_id = data.get("property_id")
    question = (data.get("question") or "").strip()

    if not property_id or not question:
        return jsonify({"error": "property_id and question are required"}), 400

    target_property = Property.query.get(property_id)
    if target_property is None:
        return jsonify({"error": "property not found"}), 404

    prompt = _build_prompt(target_property, question)
    answer = _query_llm(prompt)

    return jsonify({
        "property_id": property_id,
        "question": question,
        "answer": answer,
    }), 200


def _build_prompt(prop: Property, question: str) -> str:
    """Format a grounded prompt combining property details and the user's question."""
    price_line = (
        f"₦{prop.price_per_night}/night" if prop.is_short_let and prop.price_per_night
        else f"₦{prop.monthly_rent}/month" if prop.monthly_rent
        else "price not set"
    )

    return (
        "You are a helpful assistant answering a guest's question about a "
        "rental property listing. Only use the details provided below — "
        "if the answer isn't in these details, say you don't have that "
        "information rather than guessing.\n\n"
        f"Property: {prop.title}\n"
        f"Location: {prop.location}\n"
        f"Type: {'Short-let' if prop.is_short_let else 'Long-term rental'}\n"
        f"Price: {price_line}\n"
        f"Description: {prop.description or 'No description provided.'}\n\n"
        f"Guest question: {question}"
    )


def _query_llm(prompt: str) -> str:
    """Send the prompt to an LLM API and return its text response.

    PLACEHOLDER: replace with a real anthropic API call once you have a key.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")

    if not api_key:
        return (
            "[Chatbot not yet configured — this is a placeholder response. "
            "Add ANTHROPIC_API_KEY to enable real answers.]"
        )

    return "[LLM integration not yet implemented]"