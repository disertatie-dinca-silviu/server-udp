# import socket
# import threading

# UDP_IP = "192.168.216.98"  # IP-ul serverului tău
# UDP_PORT = 41234           # Portul pe care ascultă serverul

# # Creează socket UDP
# sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
# sock.bind(("", 0))  # Port aleator local, ascultă pe orice IP disponibil

# # Salvăm portul alocat automat
# local_port = sock.getsockname()[1]
# print(f"Client ascultă pe portul local {local_port}")

# def receive_messages():
#     while True:
#         try:
#             data, addr = sock.recvfrom(4096)
#             print(f"Mesaj primit de la {addr}: {data[:50]!r}")
#         except Exception as e:
#             print("Eroare la primire:", e)
#             break

# # Pornim fir de execuție pentru recepție
# recv_thread = threading.Thread(target=receive_messages, daemon=True)
# recv_thread.start()

# # Trimitem un mesaj de test către server
# message = b"Hello from Python UDP client"
# sock.sendto(message, (UDP_IP, UDP_PORT))
# print(f"Trimis: {message!r} către {UDP_IP}:{UDP_PORT}")

# # Ținem clientul activ ca să poată primi mesaje
# try:
#     while True:
#         pass
# except KeyboardInterrupt:
#     print("Ieșire...")
#     sock.close()

import socket
import sounddevice as sd

SERVER_IP = '192.168.216.98'  # IP-ul serverului Node.js
SERVER_PORT = 41234        # Portul serverului Node.js
CHUNK_SIZE = 8192
SAMPLE_RATE = 16000
CHANNELS = 1

# Creează socket UDP și trimite un mesaj inițial către server pentru a se "înregistra"
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.sendto(b'hello', (SERVER_IP, SERVER_PORT))  # Ping inițial

# Nu facem bind — doar ascultăm pe socketul creat
with sd.RawOutputStream(
    samplerate=SAMPLE_RATE,
    blocksize=CHUNK_SIZE // 2,
    dtype='int16',
    channels=CHANNELS
) as stream:
    print("Ascultă audio de la server...")
    while True:
        data, _ = sock.recvfrom(CHUNK_SIZE)
        stream.write(data)
        print(f"Am primit {len(data)} bytes de la server.")