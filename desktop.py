import socket
import sounddevice as sd
import threading
import keyboard  # pip install keyboard

SERVER_IP = '192.168.216.98'
SERVER_PORT = 41234
CHUNK_SIZE = 2048
SAMPLE_RATE = 16000
CHANNELS = 1

# Socket UDP
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.sendto(b'hello', (SERVER_IP, SERVER_PORT))  # Ping inițial

def receive_audio():
    """Ascultă constant audio de la server."""
    with sd.RawOutputStream(
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