import pytest
from unittest.mock import MagicMock, patch
from dolores_stt.engine import STTEngine

class MockSegment:
    def __init__(self, text, start, end):
        self.text = text
        self.start = start
        self.end = end
        self.avg_logprob = -0.1
        self.no_speech_prob = 0.01

def test_transcribe_stream_yields_segments():
    engine = STTEngine()
    engine._model = MagicMock()
    
    mock_segments = [
        MockSegment("Hello", 0.0, 1.0),
        MockSegment("world", 1.0, 2.0)
    ]
    mock_info = MagicMock()
    mock_info.language = "en"
    
    engine._model.transcribe.return_value = (iter(mock_segments), mock_info)
    
    # We need to mock NamedTemporaryFile to avoid actual file I/O if we want
    with patch("tempfile.NamedTemporaryFile") as mock_tmp:
        mock_tmp.return_value.__enter__.return_value.name = "fake.wav"
        
        results = list(engine.transcribe_stream(b"fake-audio"))
        
        assert len(results) == 3
        assert results[0] == {"type": "partial", "text": "Hello", "language": "en"}
        assert results[1] == {"type": "partial", "text": "world", "language": "en"}
        assert results[2] == {"type": "final", "text": "Hello world", "language": "en"}
