# stt_pcm.py
import whisper
import numpy as np

# Încarcă modelul o singură dată
model = whisper.load_model("small")  # sau "small", "medium", "large"

def pcm_to_text(pcm_bytes: bytes, sample_rate: int = 16000) -> str:
    """
    Convertește PCM raw 16bit mono în text.
    
    Args:
        pcm_bytes: bytes PCM (int16)
        sample_rate: sample rate al PCM (ex: 16000)
    Returns:
        transcribed text
    """
    # 1. Convertim bytes -> int16 -> float32 (-1..1)
    audio = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0

    # 2. Transcriem cu Whisper
    result = model.transcribe(audio, fp16=False, language="en")  # poți schimba limba

    return result["text"]

if __name__ == "__main__":
    # citim PCM-ul de test
    with open("output.pcm", "rb") as f:
        pcm_data = f.read()

    text = pcm_to_text(pcm_data)
    print("Transcribed text:", text)
