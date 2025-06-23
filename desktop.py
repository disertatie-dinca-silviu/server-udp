import os
import socket
import sounddevice as sd
import threading
import struct
import time
import tkinter as tk
import platform
import psutil
import dotenv
import ctypes
import opuslib  # <--- opuslib, nu pyogg!

# Încarcă DLL-ul Opus dacă e pe Windows
if platform.system() == "Windows":
    opus_dll_path = os.path.abspath("opus.dll")
    ctypes.cdll.LoadLibrary(opus_dll_path)

# Încarcă variabile din .env
dotenv.load_dotenv()
SERVER_IP = dotenv.get_key(key_to_get='SERVER_IP', dotenv_path='.env')
print(f"SERVER_IP: {SERVER_IP}")

# Configurații
CHUNK_SIZE = 2048
CHANNELS = 1
SAMPLE_RATE = 16000 if platform.system() == "Windows" else 44100
SERVER_PORT = 41234
connected = False
sock = None

# Init encoder/decoder
encoder = opuslib.Encoder(SAMPLE_RATE, CHANNELS, opuslib.APPLICATION_AUDIO)
encoder.bitrate = 32000
decoder = opuslib.Decoder(SAMPLE_RATE, CHANNELS)


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


def receive_audio():
    global connected
    try:
        with sd.OutputStream(samplerate=SAMPLE_RATE, blocksize=CHUNK_SIZE, dtype='int16', channels=CHANNELS) as stream:
            update_status("[🔊] Ascultare activă...")
            while connected:
                data, _ = sock.recvfrom(8192)
                header_size = struct.calcsize('!QQ')
                payload = data[header_size:]
                decoded_data = decoder.decode(payload, CHUNK_SIZE // 2)
                stream.write(decoded_data)
    except Exception as e:
        update_status(f"Eroare la recepție: {e}")


def transmit_audio():
    global connected
    if not connected:
        update_status("❌ Nu ești conectat la un server!")
        return

    seq_number = 0
    try:
        with sd.RawInputStream(samplerate=SAMPLE_RATE, blocksize=CHUNK_SIZE, dtype='int16', channels=CHANNELS) as stream:
            update_status("[🎙️] Transmitere activă...")
            while push_to_talk_btn_pressed:
                timestamp = int(time.time() * 1000)
                seq_number += 1
                header = struct.pack('!QQ', seq_number, timestamp)
                data, _ = stream.read(CHUNK_SIZE // 2)
                encoded_data = encoder.encode(data, CHUNK_SIZE // 2)
                packet = header + encoded_data
                sock.sendto(packet, (server_ip.get(), SERVER_PORT))
    except Exception as e:
        update_status(f"Eroare la transmitere: {e}")
    finally:
        update_status("[🛑] Transmitere oprită.")


def connect_to_server():
    global sock, connected
    ip = server_ip.get()
    if not ip:
        update_status("❗ Introdu un IP valid.")
        return

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.sendto(b'hello', (ip, SERVER_PORT))
        connected = True
        update_status(f"✅ Conectat la {ip} ({guess_network_type()})")
        threading.Thread(target=receive_audio, daemon=True).start()
    except Exception as e:
        update_status(f"❌ Conectare eșuată: {e}")
        connected = False


def disconnect_from_server():
    global connected
    if connected and sock:
        try:
            message = 'DISCONNECT:' + guess_network_type()
            sock.sendto(message.encode('utf-8'), (server_ip.get(), SERVER_PORT))
            sock.close()
        except:
            pass
        update_status("🔌 Deconectat.")
        connected = False


def on_push_to_talk_press(event=None):
    global push_to_talk_btn_pressed
    push_to_talk_btn_pressed = True
    threading.Thread(target=transmit_audio, daemon=True).start()


def on_push_to_talk_release(event=None):
    global push_to_talk_btn_pressed
    push_to_talk_btn_pressed = False


def update_status(message):
    status_label.config(text=message)


def on_closing():
    disconnect_from_server()
    root.destroy()


# Interfață grafică
push_to_talk_btn_pressed = False
root = tk.Tk()
root.title("VoIP Client")
root.geometry("400x250")
root.resizable(False, False)

tk.Label(root, text="Server IP:").pack(pady=(20, 5))
server_ip = tk.StringVar()
server_ip.set(SERVER_IP if SERVER_IP else "")
ip_entry = tk.Entry(root, textvariable=server_ip, font=("Arial", 12), width=25)
ip_entry.pack()

tk.Button(root, text="Conectează-te", command=connect_to_server, bg="lightgreen").pack(pady=10)

push_to_talk_btn = tk.Button(root, text="Push to Talk", width=20, bg="lightblue")
push_to_talk_btn.pack(pady=10)
push_to_talk_btn.bind("<ButtonPress>", on_push_to_talk_press)
push_to_talk_btn.bind("<ButtonRelease>", on_push_to_talk_release)

status_label = tk.Label(root, text="Neconectat.", fg="gray")
status_label.pack(pady=20)

root.protocol("WM_DELETE_WINDOW", on_closing)
root.mainloop()
