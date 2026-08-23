import numpy as np
import io
import librosa
import soundfile as sf
from resemblyzer import VoiceEncoder, preprocess_wav

_VOICE_ENCODER = None

def load_voice_encoder():
    global _VOICE_ENCODER
    if _VOICE_ENCODER is None:
        _VOICE_ENCODER = VoiceEncoder()
    return _VOICE_ENCODER


def load_audio_array(audio_bytes, target_sr=16000):
    """
    Robustly loads audio bytes into a 16kHz mono float32 numpy array.
    Supports standard WAV, FLAC, OGG, or raw PCM.
    """
    # Attempt 1: soundfile
    try:
        data, sr = sf.read(io.BytesIO(audio_bytes), dtype='float32')
        if data.ndim > 1:
            data = np.mean(data, axis=1)
        if sr != target_sr:
            data = librosa.resample(data, orig_sr=sr, target_sr=target_sr)
        return data, target_sr
    except Exception:
        pass

    # Attempt 2: librosa default
    try:
        data, sr = librosa.load(io.BytesIO(audio_bytes), sr=target_sr, mono=True)
        return data, sr
    except Exception:
        pass

    # Attempt 3: scipy wavfile fallback
    try:
        from scipy.io import wavfile
        sr, data = wavfile.read(io.BytesIO(audio_bytes))
        if data.dtype == np.int16:
            data = data.astype(np.float32) / 32768.0
        elif data.dtype == np.int32:
            data = data.astype(np.float32) / 2147483648.0
        elif data.dtype == np.uint8:
            data = (data.astype(np.float32) - 128.0) / 128.0
        if data.ndim > 1:
            data = np.mean(data, axis=1)
        if sr != target_sr:
            data = librosa.resample(data, orig_sr=sr, target_sr=target_sr)
        return data, target_sr
    except Exception as e:
        raise ValueError(f"Unable to decode audio format: {e}")


def get_voice_embedding(audio_bytes):
    """
    Extracts 256-dimensional acoustic embedding from raw audio bytes.
    """
    try:
        encoder = load_voice_encoder()
        audio, sr = load_audio_array(audio_bytes, target_sr=16000)
        if len(audio) < 800:  # Minimum length (~0.05s)
            return None
        wav = preprocess_wav(audio)
        embedding = encoder.embed_utterance(wav)
        return embedding.tolist()
    except Exception as e:
        print(f"Voice embedding error: {e}")
        return None


def identify_speaker(new_embedding, candidates_dict, threshold=0.65):
    """
    Compares a new embedding against candidate voice profiles using cosine similarity.
    """
    if new_embedding is None or not candidates_dict:
        return None, 0.0

    best_sid = None
    best_score = -1.0

    norm_new = np.linalg.norm(new_embedding)
    if norm_new == 0:
        return None, 0.0

    for sid, stored_embedding in candidates_dict.items():
        if stored_embedding:
            stored_arr = np.array(stored_embedding)
            norm_stored = np.linalg.norm(stored_arr)
            if norm_stored == 0:
                continue
            similarity = float(np.dot(new_embedding, stored_arr) / (norm_new * norm_stored))
            if similarity > best_score:
                best_score = similarity
                best_sid = sid

    if best_score >= threshold:
        return best_sid, best_score

    return None, best_score


def process_bulk_audio(audio_bytes, candidates_dict, threshold=0.65):
    """
    Splits long classroom audio into speech segments and matches each against candidates.
    """
    try:
        encoder = load_voice_encoder()
        audio, sr = load_audio_array(audio_bytes, target_sr=16000)
        
        # Split speech segments
        try:
            segments = librosa.effects.split(audio, top_db=25)
        except Exception:
            segments = []

        identified_results = {}

        if len(segments) == 0:
            # Fallback to analyzing entire audio if no silence splits detected
            wav = preprocess_wav(audio)
            embedding = encoder.embed_utterance(wav)
            sid, score = identify_speaker(embedding, candidates_dict, threshold)
            if sid:
                identified_results[sid] = round(score, 3)
            return identified_results

        for start, end in segments:
            if (end - start) < sr * 0.4:  # Ignore very short noises < 400ms
                continue
            segment_audio = audio[start:end]
            wav = preprocess_wav(segment_audio)
            embedding = encoder.embed_utterance(wav)

            sid, score = identify_speaker(embedding, candidates_dict, threshold)
            if sid:
                if sid not in identified_results or score > identified_results[sid]:
                    identified_results[sid] = round(score, 3)

        return identified_results
    except Exception as e:
        print(f"Bulk audio processing error: {e}")
        return {}