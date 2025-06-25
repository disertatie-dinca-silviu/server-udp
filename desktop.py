import os
import socket
import numpy as np
import sounddevice as sd
import threading
import struct
import time
import tkinter as tk
from tkinter import messagebox
import platform
import psutil
import json
import dotenv
import compressor

# Load environment variables        

CHUNK_SIZE = 2048
CHANNELS = 1
SAMPLE_RATE = 16000

sock = None
connected = False
SERVER_IP = dotenv.get_key(key_to_get='SERVER_IP', dotenv_path='.env')
compres = compressor.Compressor()
print(f"SERVER_IP: {SERVER_IP}")

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
               data, _ = sock.recvfrom(65536)  # buffer mare să nu tai date
               if len(data) <= 16:
                    continue  # Pachet invalid sau doar header, ignoră
                
               audio_dataaudio_data_bytes = compres.decode(data)
               audio_data = np.frombuffer(audio_dataaudio_data_bytes, dtype=np.int16)
               stream.write(audio_data)
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
                print("Transmit loop running...")
                timestamp = int(time.time() * 1000)
                seq_number += 1
                header = struct.pack('!QQ', seq_number, timestamp)
                
                audio_chunk, overflowed = stream.read(CHUNK_SIZE)
                if overflowed:
                    print("⚠️ Buffer overflow!")
                    continue

                compressed_data = compres.encode(audio_chunk)
                print(f"Transmitting chunk of size {len(compressed_data)} bytes, seq: {seq_number}, timestamp: {timestamp}")
                packet = header + compressed_data
                sock.sendto(packet, (server_ip.get(), SERVER_PORT))
                time.sleep(0.020)  # limităm puțin viteza de trimitere
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

        # Start receiving thread
        threading.Thread(target=receive_audio, daemon=True).start()
    except Exception as e:
        update_status(f"❌ Conectare eșuată: {e}")
        connected = False


def disconnect_from_server(stars):
    global connected
    if connected and sock:
        message = 'DISCONNECT:' + guess_network_type() + ":" + str(stars)
        sock.sendto(message.encode('utf-8'), (server_ip.get(), SERVER_PORT))
        sock.close()
        update_status("🔌 Deconectat.")
        connected = False


def on_push_to_talk_press(event=None):
    global push_to_talk_btn_pressed
    push_to_talk_btn_pressed = True
    print("Push to Talk pressed")  # debug
    threading.Thread(target=transmit_audio, daemon=True).start()


def on_push_to_talk_release(event=None):
    global push_to_talk_btn_pressed
    push_to_talk_btn_pressed = False
    print("Pushed to talk: STOP")


def update_status(message):
    status_label.config(text=message)


def on_closing():
    if not connected:
        root.destroy()
        return
    
    rating_window = tk.Toplevel(root)
    rating_window.title("Feedback")
    rating_window.geometry("300x150")
    rating_window.grab_set()  # face fereastra modală
    tk.Label(rating_window, text="Cum ai evalua calitatea audio?", font=("Arial", 12)).pack(pady=10)
    selected_rating = tk.IntVar(value=0)


    def give_rating(stars):
        selected_rating.set(stars)
        print(f"Rating oferit: {stars} stele")
        disconnect_from_server(stars)
        rating_window.destroy()
        root.destroy()
    stars_frame = tk.Frame(rating_window)
    stars_frame.pack()
    for i in range(1, 6):
        btn = tk.Button(stars_frame, text="★", font=("Arial", 18),
                        command=lambda i=i: give_rating(i))
        btn.grid(row=0, column=i, padx=5)

    rating_window.protocol("WM_DELETE_WINDOW", lambda: None)  # prevenim închiderea fără rating


# GUI
SERVER_PORT = 41234
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
