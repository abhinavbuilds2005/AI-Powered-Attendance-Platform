from resemblyzer import VoiceEncoder, preprocess_wav
import numpy as np
import io
import librosa
from typing import Dict, Optional, Tuple, Any

_VOICE_ENCODER = None

def load_voice_encoder():
    """Lazy load VoiceEncoder model."""
    global _VOICE_ENCODER
    if _VOICE_ENCODER is None:
        _VOICE_ENCODER = VoiceEncoder()
    return _VOICE_ENCODER

def get_voice_embedding(audio_bytes: bytes) -> Optional[list]:
    """Generate 256-D voice embedding from audio bytes."""
    try:
        encoder = load_voice_encoder()
        audio, sr = librosa.load(io.BytesIO(audio_bytes), sr=16000)
        wav = preprocess_wav(audio)
        embedding = encoder.embed_utterance(wav)
        return embedding.tolist()
    except Exception as e:
        print('Voice recognition error:', e)
        return None

def identify_speaker(
    new_embedding: np.ndarray,
    candidates_dict: Dict[int, np.ndarray],
    threshold: float = 0.65
) -> Tuple[Optional[int], float]:
    """Match voice embedding against candidate stored embeddings using cosine similarity."""
    if new_embedding is None or not candidates_dict:
        return None, 0.0

    best_sid = None
    best_score = -1.0

    try:
        new_embedding = np.asarray(new_embedding, dtype=np.float64)
    except (TypeError, ValueError):
        return None, 0.0

    if new_embedding.ndim != 1 or not np.isfinite(new_embedding).all():
        return None, 0.0

    new_norm = np.linalg.norm(new_embedding)
    if new_norm == 0:
        return None, 0.0

    for sid, stored_embedding in candidates_dict.items():
        try:
            stored = np.asarray(stored_embedding, dtype=np.float64)
        except (TypeError, ValueError):
            continue
        stored_norm = np.linalg.norm(stored)
        if stored.shape != new_embedding.shape or stored_norm == 0 or not np.isfinite(stored).all():
            continue
        similarity = float(np.dot(new_embedding, stored) / (new_norm * stored_norm))
        if similarity > best_score:
            best_score = similarity
            best_sid = sid

    if best_score >= threshold:
        return best_sid, best_score

    return None, best_score

def process_bulk_audio(
    audio_bytes: bytes,
    candidates_dict: Dict[int, np.ndarray],
    threshold: float = 0.65
) -> Dict[int, float]:
    """Segment a classroom wide audio and detect all present voices."""
    try:
        encoder = load_voice_encoder()
        audio, sr = librosa.load(io.BytesIO(audio_bytes), sr=16000)
        
        # Split audio based on silence detection
        segments = librosa.effects.split(audio, top_db=30)
        identified_results = {}

        for start, end in segments:
            # Skip short segments (under 0.5s) to reduce noise
            if (end - start) < sr * 0.5:
                continue
            
            segment_audio = audio[start:end]
            wav = preprocess_wav(segment_audio)
            embedding = encoder.embed_utterance(wav)

            sid, score = identify_speaker(embedding, candidates_dict, threshold)
            if sid is not None:
                if sid not in identified_results or score > identified_results[sid]:
                    identified_results[sid] = score

        return identified_results
    except Exception as e:
        print('Bulk voice processing error:', e)
        return {}
