"""API contract, validation, error-handling and persistence tests."""
from conftest import image_bytes, make_client


def post(client, data, name="photo.jpg", ctype="image/jpeg", params=None):
    return client.post("/api/analyze", files={"photo": (name, data, ctype)}, params=params or {})


def test_health_reports_loaded_model(client):
    for path in ("/health", "/api/health"):
        r = client.get(path)
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok" and body["model_loaded"] is True and body["mock_mode"] is False
        assert body["model_version"].startswith("tiny_test_fixture")


def test_models_lists_honest_statuses(client):
    models = {m["id"]: m for m in client.get("/api/models").json()["models"]}
    assert models["vit"]["status"] == "loaded"
    assert models["unet"]["status"] == "unavailable"
    assert models["shelf_life"]["status"] == "disabled"


def test_analyze_valid_jpeg_returns_real_inference_contract(client):
    r = post(client, image_bytes())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["source"] == "model" and body["mock"] is False
    assert body["disclaimer"].startswith("Visual estimate")
    assert len(body["items"]) == 1
    it = body["items"][0]
    assert it["produce_class"] in ["Banana", "Carrot", "Guava", "Indian_Gooseberry", "Mango", "Tomato"]
    assert 0 <= it["freshness"] <= 100 and it["tier"] in ("good", "warn", "bad")
    assert abs(sum(it["produce_probabilities"].values()) - 1) < 1e-3
    assert it["days"] is None and it["decayPct"] is None and it["decay_mask_available"] is False  # no optional models in fixture
    assert it["xai_overlay"] is None


def test_analyze_is_deterministic(client):
    a = post(client, image_bytes()).json()["items"][0]
    b = post(client, image_bytes()).json()["items"][0]
    assert a["produce_probabilities"] == b["produce_probabilities"] and a["p_spoiled"] == b["p_spoiled"]


def test_analyze_png_and_webp(client):
    assert post(client, image_bytes("PNG"), "a.png", "image/png").status_code == 200
    assert post(client, image_bytes("WEBP"), "a.webp", "image/webp").status_code == 200


def test_xai_overlay(client):
    it = post(client, image_bytes(), params={"xai": "true"}).json()["items"][0]
    assert it["xai_method"] == "attention_rollout"
    assert it["xai_overlay"].startswith("data:image/png;base64,")


def test_rejects_wrong_media_type(client):
    r = post(client, b"hello", "a.txt", "text/plain")
    assert r.status_code == 415 and r.json()["detail"]["code"] == "unsupported_media_type"


def test_rejects_corrupt_image(client):
    r = post(client, b"\xff\xd8\xff\xe0" + b"garbage" * 50)
    assert r.status_code == 400 and r.json()["detail"]["code"] == "invalid_image"


def test_rejects_empty_file(client):
    r = post(client, b"")
    assert r.status_code == 400 and r.json()["detail"]["code"] == "invalid_image"


def test_rejects_tiny_image(client):
    r = post(client, image_bytes(size=(8, 8)))
    assert r.status_code == 400


def test_rejects_unsupported_decoded_format(client):
    import io

    from PIL import Image
    buf = io.BytesIO(); Image.new("RGB", (64, 64)).save(buf, "GIF")
    r = post(client, buf.getvalue(), "a.gif", "application/octet-stream")
    assert r.status_code == 400 and "Unsupported image format" in r.json()["detail"]["message"]


def test_missing_field_is_422(client):
    r = client.post("/api/analyze")
    assert r.status_code == 422 and r.json()["detail"]["code"] == "invalid_request"


def test_oversized_upload_413(monkeypatch, tmp_path, tiny_ckpt):
    with make_client(monkeypatch, tmp_path, tiny_ckpt, max_mb=0.01) as c:
        r = post(c, b"\xff" * 20000)  # 20 KB > 0.01 MB limit
        assert r.status_code == 413 and r.json()["detail"]["code"] == "file_too_large"


def test_missing_checkpoint_fails_clearly(monkeypatch, tmp_path):
    with make_client(monkeypatch, tmp_path, tmp_path / "does_not_exist.pt") as c:
        h = c.get("/health").json()
        assert h["status"] == "degraded" and h["model_loaded"] is False
        assert "Checkpoint not found" in h["model_error"]
        r = post(c, image_bytes())
        assert r.status_code == 503 and r.json()["detail"]["code"] == "model_unavailable"
        assert c.get("/api/history").json() == []  # nothing fabricated or stored


def test_mock_mode_is_explicitly_labelled(monkeypatch, tmp_path):
    with make_client(monkeypatch, tmp_path, tmp_path / "none.pt", mock=True) as c:
        body = post(c, image_bytes()).json()
        assert body["mock"] is True and body["source"] == "mock"
        assert any("DEMO MOCK DATA" in w for w in body["warnings"])
        assert all(it["mock"] is True for it in body["items"])
        assert "DEMO MOCK DATA" in "\n".join(c.get("/api/report").json()["lines"])


def test_history_persists_and_is_queryable(monkeypatch, tmp_path, tiny_ckpt):
    with make_client(monkeypatch, tmp_path, tiny_ckpt) as c:
        s1 = post(c, image_bytes()).json()
        post(c, image_bytes(color=(30, 160, 60)))
        hist = c.get("/api/history").json()
        assert len(hist) == 2 and hist[0]["ts"] >= hist[1]["ts"]
        assert all(h["source"] == "model" for h in hist)
        assert "xai_overlay" not in hist[0]["items"][0]
        one = c.get(f"/api/history/{s1['scan_id']}").json()
        assert one["scan_id"] == s1["scan_id"] and one["items"][0]["name"] == s1["items"][0]["name"]
        assert c.get("/api/history/nope").status_code == 404
        assert c.get("/api/stats").json()["totalInspections"] == 2
    # new app instance, same DB file -> history survives restart
    with make_client(monkeypatch, tmp_path, tiny_ckpt, fresh=False) as c2:
        assert len(c2.get("/api/inspections").json()) == 2
        assert c2.delete("/api/inspections").json() == {"cleared": True}
        assert c2.get("/api/history").json() == []


def test_report_text_and_pdf(client):
    post(client, image_bytes())
    lines = client.get("/api/report").json()["lines"]
    assert any("not a food-safety guarantee" in l for l in lines)
    r = client.get("/api/report/pdf")
    assert r.status_code == 200 and r.content[:4] == b"%PDF"


def test_nutrition_and_tips(client):
    assert client.get("/api/nutrition/Mango").json()["name"] == "Mango"
    assert client.get("/api/nutrition/Kiwi").status_code == 404
    assert isinstance(client.get("/api/tips").json(), list)


def test_cors_allows_dev_origin_only(client):
    ok = client.get("/health", headers={"Origin": "http://localhost:5173"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:5173"
    bad = client.get("/health", headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in bad.headers


def test_visible_decay_unavailable_without_probe(client):
    it = post(client, image_bytes()).json()["items"][0]
    assert it["visible_decay_status"] == "unavailable" and it["visible_decay_probability"] is None
    models = {m["id"]: m for m in client.get("/api/models").json()["models"]}
    assert models["visible_decay"]["status"] == "unavailable" and models["unet"]["status"] == "unavailable"
