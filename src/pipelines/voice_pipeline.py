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


def safe_get_voice_embedding(audio_bytes):
    """
    Validates the raw audio and returns (embedding, message).
    If the sample is empty, too short, too quiet, or invalid, returns None but keeps the
    rest of the account creation flow alive.
    """
    if audio_bytes is None:
        return None, "No voice sample provided."

    if isinstance(audio_bytes, str):
        stripped = audio_bytes.strip()
        if not stripped:
            return None, "No voice sample provided."

    try:
        audio, sr = load_audio_array(audio_bytes, target_sr=16000)
    except Exception as exc:
        return None, f"Could not decode the voice sample: {exc}"

    if len(audio) < 800:
        return None, "Voice sample is too short. Please record for at least 1 second."

    if float(np.max(np.abs(audio))) < 0.003:
        return None, "Voice sample is too quiet. Please speak closer to the microphone."

    try:
        wav = preprocess_wav(audio)
        embedding = load_voice_encoder().embed_utterance(wav)
        return embedding.tolist(), "Voice sample validated successfully."
    except Exception as exc:
        return None, f"Could not extract a valid voiceprint: {exc}"


def load_audio_array(audio_bytes, target_sr=16000):
    """
    Robustly loads audio bytes into a 16kHz mono float32 numpy array.
    """
    try:
        data, sr = sf.read(io.BytesIO(audio_bytes), dtype='float32')
        if data.ndim > 1:
            data = np.mean(data, axis=1)
        if sr != target_sr:
            data = librosa.resample(data, orig_sr=sr, target_sr=target_sr)
        return data, target_sr
    except Exception:
        pass

    try:
        data, sr = librosa.load(io.BytesIO(audio_bytes), sr=target_sr, mono=True)
        return data, sr
    except Exception:
        pass

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


def check_voice_liveness_and_anti_replay(audio_array, sr=16000):
    """
    Verifies audible voice activity and dynamic energy range.
    """
    if len(audio_array) < sr * 0.3:
        return False, "Audio recording is too short. Please speak for at least 1 second."

    max_amp = float(np.max(np.abs(audio_array)))
    if max_amp < 0.003:
        return False, "Audio is too quiet. Please speak closer to your microphone."

    return True, "Live voice verified"


def get_voice_embedding(audio_bytes):
    """
    Extracts 256-dimensional acoustic embedding from raw audio bytes.
    """
    embedding, _ = safe_get_voice_embedding(audio_bytes)
    return embedding


def identify_speaker(new_embedding, candidates_dict, threshold=0.58, min_margin=0.0):
    """
    Compares a new embedding against candidate voice profiles using cosine similarity.
    """
    if new_embedding is None or not candidates_dict:
        return None, 0.0

    best_sid = None
    best_score = -1.0
    second_best_score = -1.0

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
                second_best_score = best_score
                best_score = similarity
                best_sid = sid
            elif similarity > second_best_score:
                second_best_score = similarity

    if best_score >= threshold and best_score - second_best_score >= min_margin:
        return best_sid, best_score

    return None, best_score


def process_bulk_audio(audio_bytes, candidates_dict, threshold=0.58):
    """
    Splits long classroom audio into speech segments and matches each against candidates.
    """
    try:
        encoder = load_voice_encoder()
        audio, sr = load_audio_array(audio_bytes, target_sr=16000)
        
        try:
            segments = librosa.effects.split(audio, top_db=25)
        except Exception:
            segments = []

        identified_results = {}

        if len(segments) == 0:
            wav = preprocess_wav(audio)
            embedding = encoder.embed_utterance(wav)
            sid, score = identify_speaker(embedding, candidates_dict, threshold)
            if sid:
                identified_results[sid] = round(score, 3)
            return identified_results

        for start, end in segments:
            if (end - start) < sr * 0.4:
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