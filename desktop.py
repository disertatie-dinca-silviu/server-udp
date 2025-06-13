import socket
import sounddevice as sd
import threading
import keyboard  # pip install keyboard
import platform
import json
from dotenv import load_dotenv
import os
import struct
import time
import psutil

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


def guess_network_type():
    stats = psutil.net_if_stats()
    for iface, data in stats.items():
        if data.isup:
            name = iface.lower()
            if "wlan" in name or "wi-fi" in name or "wifi" in name:
                return "WiFi"
            elif "eth" in name or "en" in name:
                return "Ethernet"
            elif "wwan" in name or "cell" in name or "lte" in name:
                return "Mobile (4G/5G)"
    return "Unknown"

print("Tip conexiune activă:", guess_network_type())


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
    seq_number = 0
    with sd.RawInputStream(
        samplerate=SAMPLE_RATE,
        blocksize=CHUNK_SIZE,
        dtype='int16',
        channels=CHANNELS
    ) as stream:
        print("[🎙️] Transmitere activă...")
        while keyboard.is_pressed('t'):
            try:
                timestamp = int(time.time() * 1000)  # milisecunde
                seq_number += 1
                header = struct.pack('!QQ', seq_number, timestamp)
                data, _ = stream.read(CHUNK_SIZE // 2)
                packet = header + data
                sock.sendto(packet, (SERVER_IP, SERVER_PORT))
            except Exception as e:
                print("Eroare la transmitere:", e)
                break
        print("[🛑] Transmitere oprită.")

# Thread recepție audio
threading.Thread(target=receive_audio, daemon=True).start()

def send_disconnect_message():
    network_type = guess_network_type()
    message = 'DISCONNECT:'+network_type
    sock.sendto(message.encode('utf-8'), (SERVER_IP, SERVER_PORT))

print("Ține apăsat 't' pentru a vorbi (Push-to-Talk). Ctrl+C pentru a ieși.")

try:
    while True:
        if keyboard.is_pressed('t'):
            transmit_audio()  # Rulează cât e apăsat
except KeyboardInterrupt:
    print("Ieșire...")
    #trimitem mesaj de DISCONNECT
    send_disconnect_message()
    sock.close()
    exit(0)
# Închide socket-ul la ieșire           