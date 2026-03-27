"""Tests for VoiceProfileStore — SQLite + filesystem persistence."""

from __future__ import annotations

import pytest

from dolores_tts.voice_profiles import VoiceProfileStore

pytestmark = pytest.mark.anyio


class TestVoiceProfileStore:
    """Tests for CRUD operations on VoiceProfileStore."""

    @pytest.fixture(autouse=True)
    async def _setup_store(self, tmp_path):
        voices_dir = str(tmp_path / "voices")
        db_path = str(tmp_path / "tts.db")
        self.store = VoiceProfileStore(voices_dir, db_path)
        self._tmp_path = tmp_path
        await self.store.init()
        yield
        await self.store.close()

    async def test_create_and_get(self):
        result = await self.store.create(
            name="TestVoice",
            audio_data=b"fake_wav_data",
            engine="coqui_xtts",
            description="A test voice",
        )

        assert result["name"] == "TestVoice"
        assert result["engine"] == "coqui_xtts"
        assert "id" in result

        profile = await self.store.get_profile(result["id"])
        assert profile is not None
        assert profile["name"] == "TestVoice"
        assert profile["description"] == "A test voice"
        assert profile["engine"] == "coqui_xtts"
        assert profile["ref_text"] is None

    async def test_create_with_ref_text(self):
        result = await self.store.create(
            name="F5Voice",
            audio_data=b"fake_wav_data",
            engine="f5_tts",
            ref_text="Hello world this is a test",
        )

        profile = await self.store.get_profile(result["id"])
        assert profile["ref_text"] == "Hello world this is a test"

    async def test_create_saves_audio_to_disk(self):
        from pathlib import Path

        audio_bytes = b"RIFF_fake_wav_content"
        result = await self.store.create(
            name="DiskVoice",
            audio_data=audio_bytes,
            engine="coqui_xtts",
        )

        ref_path = Path(self._tmp_path / "voices" / result["id"] / "reference.wav")
        assert ref_path.exists()
        assert ref_path.read_bytes() == audio_bytes

    async def test_list_profiles_empty(self):
        profiles = await self.store.list_profiles()
        assert profiles == []

    async def test_list_profiles_multiple(self):
        await self.store.create(name="VoiceA", audio_data=b"data_a", engine="coqui_xtts")
        await self.store.create(name="VoiceB", audio_data=b"data_b", engine="f5_tts")

        profiles = await self.store.list_profiles()
        assert len(profiles) == 2
        names = {p["name"] for p in profiles}
        assert names == {"VoiceA", "VoiceB"}

    async def test_list_profiles_ordered_newest_first(self):
        import asyncio
        await self.store.create(name="First", audio_data=b"d", engine="coqui_xtts")
        await asyncio.sleep(0.001)  # ensure distinct created_at timestamps
        await self.store.create(name="Second", audio_data=b"d", engine="coqui_xtts")

        profiles = await self.store.list_profiles()
        assert profiles[0]["name"] == "Second"
        assert profiles[1]["name"] == "First"

    async def test_get_nonexistent_profile(self):
        profile = await self.store.get_profile("nonexistent-id")
        assert profile is None

    async def test_delete_profile(self):
        from pathlib import Path

        result = await self.store.create(
            name="ToDelete",
            audio_data=b"fake_data",
            engine="coqui_xtts",
        )
        profile_id = result["id"]

        voice_dir = Path(self._tmp_path / "voices" / profile_id)
        assert voice_dir.exists()

        deleted = await self.store.delete(profile_id)
        assert deleted is True
        assert not voice_dir.exists()
        assert await self.store.get_profile(profile_id) is None

    async def test_delete_nonexistent_returns_false(self):
        deleted = await self.store.delete("nonexistent-id")
        assert deleted is False

    async def test_delete_removes_from_list(self):
        result = await self.store.create(name="Temp", audio_data=b"d", engine="coqui_xtts")
        await self.store.delete(result["id"])

        profiles = await self.store.list_profiles()
        assert profiles == []

    async def test_profile_id_is_short_uuid(self):
        result = await self.store.create(name="ShortID", audio_data=b"d", engine="coqui_xtts")
        assert len(result["id"]) == 8

    async def test_profile_has_created_at(self):
        result = await self.store.create(name="Timestamped", audio_data=b"d", engine="coqui_xtts")
        profile = await self.store.get_profile(result["id"])
        assert profile["created_at"] is not None
        assert "T" in profile["created_at"]
