import io
import threading
import wave
import numpy as np
import librosa
import soundfile as sf
from scipy.io import wavfile
from resemblyzer import VoiceEncoder, preprocess_wav
from typing import Dict, Optional, Tuple, Any, List

_VOICE_LOCK = threading.Lock()
_VOICE_ENCODER = None

def load_voice_encoder() -> VoiceEncoder:
    """Lazy load VoiceEncoder model with thread safety."""
    global _VOICE_ENCODER
    if _VOICE_ENCODER is not None:
        return _VOICE_ENCODER

    with _VOICE_LOCK:
        if _VOICE_ENCODER is not None:
            return _VOICE_ENCODER
        _VOICE_ENCODER = VoiceEncoder()
        return _VOICE_ENCODER


def load_audio_array(audio_bytes: bytes, target_sr: int = 16000) -> Tuple[np.ndarray, int]:
    """
    Robustly decodes audio bytes (WAV, PCM, OGG, FLAC, WebM, etc.) into a 16kHz mono float32 numpy array.
    """
    if not audio_bytes:
        raise ValueError("Audio byte buffer is empty.")

    # Fast resample helper
    def _resample(data: np.ndarray, orig_sr: int) -> np.ndarray:
        if orig_sr == target_sr:
            return data
        try:
            return librosa.resample(data, orig_sr=orig_sr, target_sr=target_sr, res_type="soxr_qq")
        except Exception:
            return librosa.resample(data, orig_sr=orig_sr, target_sr=target_sr)

    # 1. Try SoundFile reader
    try:
        data, sr = sf.read(io.BytesIO(audio_bytes), dtype='float32')
        if data.ndim > 1:
            data = np.mean(data, axis=1)
        data = _resample(data, sr)
        return data.astype(np.float32), target_sr
    except Exception:
        pass

    # 2. Try standard wave library for raw WAV
    try:
        with wave.open(io.BytesIO(audio_bytes), 'rb') as wf:
            n_channels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            framerate = wf.getframerate()
            n_frames = wf.getnframes()
            raw_frames = wf.readframes(n_frames)
            
            if sampwidth == 2:
                data = np.frombuffer(raw_frames, dtype=np.int16).astype(np.float32) / 32768.0
            elif sampwidth == 4:
                data = np.frombuffer(raw_frames, dtype=np.int32).astype(np.float32) / 2147483648.0
            elif sampwidth == 1:
                data = (np.frombuffer(raw_frames, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
            else:
                data = np.frombuffer(raw_frames, dtype=np.float32)

            if n_channels > 1:
                data = data.reshape(-1, n_channels).mean(axis=1)

            data = _resample(data, framerate)
            return data.astype(np.float32), target_sr
    except Exception:
        pass

    # 3. Try scipy.io.wavfile
    try:
        sr, data = wavfile.read(io.BytesIO(audio_bytes))
        if data.dtype == np.int16:
            data = data.astype(np.float32) / 32768.0
        elif data.dtype == np.int32:
            data = data.astype(np.float32) / 2147483648.0
        elif data.dtype == np.uint8:
            data = (data.astype(np.float32) - 128.0) / 128.0
        elif data.dtype != np.float32:
            data = data.astype(np.float32)

        if data.ndim > 1:
            data = np.mean(data, axis=1)
        data = _resample(data, sr)
        return data.astype(np.float32), target_sr
    except Exception:
        pass

    # 4. Try librosa direct
    try:
        data, sr = librosa.load(io.BytesIO(audio_bytes), sr=target_sr, mono=True)
        return data.astype(np.float32), sr
    except Exception as e:
        raise ValueError(f"Could not decode audio in any known format: {e}")


def get_voice_embedding(audio_bytes: bytes) -> Optional[List[float]]:
    """Generate 256-D voice embedding from audio bytes."""
    try:
        if not audio_bytes:
            return None
        encoder = load_voice_encoder()
        audio, sr = load_audio_array(audio_bytes, target_sr=16000)
        
        # Audio length & silence check (~0.1s minimum)
        if len(audio) < 1600:
            return None
        
        max_amp = float(np.max(np.abs(audio)))
        if max_amp < 0.0005:
            return None

        # Preprocess with VAD, but fallback gracefully if VAD trimmed everything
        wav = np.array([], dtype=np.float32)
        try:
            wav = preprocess_wav(audio)
        except Exception:
            pass

        # If silence trimming removed the entire utterance, use normalized raw audio
        if len(wav) < 1600:
            from resemblyzer.audio import normalize_volume, audio_norm_target_dBFS
            try:
                wav = normalize_volume(audio, audio_norm_target_dBFS, increase_only=True)
            except Exception:
                wav = audio

        if len(wav) == 0:
            return None

        embedding = encoder.embed_utterance(wav)
        if embedding is not None and len(embedding) > 0:
            return embedding.tolist()
        return None
    except Exception as e:
        print('Voice recognition error:', e)
        return None


def identify_speaker(
    new_embedding: np.ndarray,
    candidates_dict: Dict[int, Any],
    threshold: float = 0.45
) -> Tuple[Optional[int], float]:
    """Match voice embedding against candidate stored embeddings using cosine similarity."""
    if new_embedding is None or not candidates_dict:
        return None, 0.0

    best_sid = None
    best_score = -1.0

    try:
        new_vec = np.asarray(new_embedding, dtype=np.float64)
    except (TypeError, ValueError):
        return None, 0.0

    if new_vec.ndim != 1 or not np.isfinite(new_vec).all():
        return None, 0.0

    new_norm = np.linalg.norm(new_vec)
    if new_norm == 0:
        return None, 0.0

    for sid, stored_embedding in candidates_dict.items():
        if stored_embedding is None:
            continue
        try:
            stored_vec = np.asarray(stored_embedding, dtype=np.float64)
        except (TypeError, ValueError):
            continue
        
        stored_norm = np.linalg.norm(stored_vec)
        if stored_vec.shape != new_vec.shape or stored_norm == 0 or not np.isfinite(stored_vec).all():
            continue
            
        similarity = float(np.dot(new_vec, stored_vec) / (new_norm * stored_norm))
        if similarity > best_score:
            best_score = similarity
            best_sid = sid

    if best_score >= threshold:
        return best_sid, best_score

    return None, best_score


def process_bulk_audio(
    audio_bytes: bytes,
    candidates_dict: Dict[int, Any],
    threshold: float = 0.45
) -> Dict[int, float]:
    """Segment a classroom wide audio and detect all present voices."""
    try:
        if not audio_bytes or not candidates_dict:
            return {}
            
        encoder = load_voice_encoder()
        audio, sr = load_audio_array(audio_bytes, target_sr=16000)
        
        if len(audio) < 1600:
            return {}

        identified_results = {}

        # 1. Whole clip match first (if short or single speaker)
        try:
            wav_full = preprocess_wav(audio)
            if len(wav_full) > 0:
                emb_full = encoder.embed_utterance(wav_full)
                sid, score = identify_speaker(emb_full, candidates_dict, threshold)
                if sid is not None:
                    identified_results[sid] = round(score, 3)
        except Exception:
            pass

        # 2. Split audio based on silence detection for multiple speakers
        try:
            segments = librosa.effects.split(audio, top_db=25)
        except Exception:
            segments = []

        for start, end in segments:
            # Skip segments under 0.4s to reduce noise
            if (end - start) < sr * 0.4:
                continue
            
            segment_audio = audio[start:end]
            try:
                wav = preprocess_wav(segment_audio)
                if len(wav) == 0:
                    continue
                embedding = encoder.embed_utterance(wav)
                sid, score = identify_speaker(embedding, candidates_dict, threshold)
                if sid is not None:
                    if sid not in identified_results or score > identified_results[sid]:
                        identified_results[sid] = round(score, 3)
            except Exception:
                continue

        return identified_results
    except Exception as e:
        print('Bulk voice processing error:', e)
        return {}

