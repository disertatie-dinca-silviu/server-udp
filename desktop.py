import socket
import sounddevice as sd
import threading
import keyboard  # pip install keyboard
import platform
import json
from dotenv import load_dotenv
import os

load_dotenv()

SERVER_IP = os.getenv('SERVER_IP')
SERVER_PORT = 41234
CHUNK_SIZE = 2048
CHANNELS = 1

print(sd.query_devices())
print(sd.default.device)
SOUND_INFORMATION = sd.query_devices(sd.default.device[1], 'output'),
print(json.dumps(SOUND_INFORMATION, indent=2))

if SOUND_INFORMATION is not None:
    SAMPLE_RATE = SOUND_INFORMATION[0]['default_samplerate']
else:
    SAMPLE_RATE = 44100 if  platform.system() == "Linux" else 16000

# Socket UDP
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.sendto(b'hello', (SERVER_IP, SERVER_PORT))  # Ping inițial

def receive_audio():
    """Ascultă constant audio de la server."""
    with sd.OutputStream(
        samplerate=SAMPLE_RATE,
        blocksize=CHUNK_SIZE,
        dtype='int16',
        channels=CHANNELS
    ) as stream:
        print("[🔊] Ascultare activă...")
        while True:
            try:
                data, _ = sock.recvfrom(CHUNK_SIZE)
                stream.write(data)
            except Exception as e:
                print("Eroare la recepție:", e)
                break

def transmit_audio():
    """Transmite audio cât timp este apăsată tasta 't'."""
    with sd.RawInputStream(
        samplerate=SAMPLE_RATE,
        blocksize=CHUNK_SIZE,
        dtype='int16',
        channels=CHANNELS
    ) as stream:
        print("[🎙️] Transmitere activă...")
        while keyboard.is_pressed('t'):
            try:
                data, _ = stream.read(CHUNK_SIZE // 2)
                sock.sendto(data, (SERVER_IP, SERVER_PORT))
            except Exception as e:
                print("Eroare la transmitere:", e)
                break
        print("[🛑] Transmitere oprită.")

# Thread recepție audio
threading.Thread(target=receive_audio, daemon=True).start()

print("Ține apăsat 't' pentru a vorbi (Push-to-Talk). Ctrl+C pentru a ieși.")

try:
    while True:
        if keyboard.is_pressed('t'):
            transmit_audio()  # Rulează cât e apăsat
except KeyboardInterrupt:
    print("Ieșire...")
    sock.close()
    exit(0)
# Închide socket-ul la ieșire           