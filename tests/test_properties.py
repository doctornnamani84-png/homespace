from pathlib import Path


def test_upload_video_form_is_connected_to_frontend_submit_handler():
    script = Path(__file__).resolve().parents[1] / "frontend" / "script.js"
    source = script.read_text(encoding="utf-8")

    assert 'document.getElementById("upload-video-form")' in source
    assert 'formData.append("video", file);' in source
