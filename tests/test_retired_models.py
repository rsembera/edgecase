"""Retired AI model files left behind by an earlier release.

A 1.0 install that upgrades keeps Hermes on disk. Nothing references it, and
"Delete Model" only targets the current filename, so it would sit there
silently. Settings must surface it and offer to delete it — and the delete
path must touch nothing but the known retired filenames.
"""
import pytest

from ai import assistant


@pytest.fixture
def models_dir(tmp_path, monkeypatch):
    d = tmp_path / "models"
    d.mkdir()
    monkeypatch.setattr(assistant, "MODEL_DIR", d)
    return d


def _plant(models_dir, filename, size=1024):
    (models_dir / filename).write_bytes(b"\0" * size)


class TestRetiredModels:
    def test_status_lists_retired_model_present_on_disk(self, models_dir, client):
        _plant(models_dir, "Hermes-3-Llama-3.1-8B.Q4_K_M.gguf")
        data = client.get("/api/ai/status").get_json()
        assert "retired" in data
        assert [m["filename"] for m in data["retired"]] == ["Hermes-3-Llama-3.1-8B.Q4_K_M.gguf"]
        assert "1.0" in data["retired"][0]["label"]

    def test_status_empty_when_nothing_retired(self, models_dir, client):
        _plant(models_dir, assistant.MODEL_FILENAME)
        data = client.get("/api/ai/status").get_json()
        assert data["retired"] == []

    def test_delete_retired_removes_only_known_files(self, models_dir, client):
        _plant(models_dir, "Hermes-3-Llama-3.1-8B.Q4_K_M.gguf")
        _plant(models_dir, assistant.MODEL_FILENAME)
        _plant(models_dir, "something-else.gguf")
        resp = client.post("/api/ai/delete-retired")
        assert resp.status_code == 200
        assert resp.get_json()["removed"] == ["Hermes-3-Llama-3.1-8B.Q4_K_M.gguf"]
        assert not (models_dir / "Hermes-3-Llama-3.1-8B.Q4_K_M.gguf").exists()
        assert (models_dir / assistant.MODEL_FILENAME).exists()
        assert (models_dir / "something-else.gguf").exists()

    def test_delete_retired_is_idempotent(self, models_dir, client):
        resp = client.post("/api/ai/delete-retired")
        assert resp.status_code == 200
        assert resp.get_json()["removed"] == []
