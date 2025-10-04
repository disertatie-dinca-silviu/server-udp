#!/usr/bin/env python3
"""
UDP + WebSocket server for VoIP moderation prototype.

UDP packet format (bytes):
  0..7   : seq_number (unsigned long long, big-endian)
  8..15  : timestamp (unsigned long long, big-endian)  <-- ms epoch from client
 16..31  : websocket_id (16 bytes raw UUID)
 32..end : audio payload (binary)

WebSocket: simple JSON handshake
  client -> {"type":"CONN"}
  server -> {"type":"ID", "id": "<uuid4>"}
"""

import asyncio
import struct
import uuid
import json
import csv
from pathlib import Path
from typing import Dict, Tuple, List
from collections import defaultdict
from pprint import pprint
import websockets  # pip install websockets

# -------------------- Config --------------------
UDP_HOST = "0.0.0.0"
UDP_PORT = 41234
WS_HOST = "0.0.0.0"
WS_PORT = 8080

OUTPUT_FILE = Path("output.pcm")
STATS_FILE = Path("client_stats.csv")

# -------------------- State --------------------
# clients: key = "ip:port" -> (ip, port)
clients: Dict[str, Tuple[str, int]] = {}

# mapare UDP client (ip:port) -> websocket UUID string
client_udp_to_ws: Dict[str, str] = {}

# latencies/jitters: ipport -> list of samples
latency_stats: Dict[str, List[float]] = defaultdict(list)
jitter_stats: Dict[str, List[float]] = defaultdict(list)

# last sequence number seen per client
last_packet: Dict[str, int] = {}

# client offset correction (ms)
client_offset: Dict[str, float] = {}

# client packet counters for packet loss
client_data: Dict[str, Dict[str, int]] = defaultdict(lambda: {"receivedPackets": 0, "lostPackets": 0})


# -------------------- Utilities --------------------
def generate_user_id() -> str:
    return str(uuid.uuid4())


def write_stats_to_csv(packet_loss: float, avg_jitter: float, avg_latency: float, network_type: str, stars: int):
    header = ["PacketLoss(%)", "Jitter(ms)", "Latency(ms)", "NetworkType", "Clients", "Stars"]
    write_header = not STATS_FILE.exists()
    line = [f"{packet_loss:.2f}", f"{avg_jitter:.2f}", f"{avg_latency:.2f}", network_type, str(len(clients)), str(stars)]

    mode = "a"
    with STATS_FILE.open(mode, newline="") as csvfile:
        writer = csv.writer(csvfile)
        if write_header:
            writer.writerow(header)
        writer.writerow(line)
    print("Statistici salvate în", STATS_FILE)


# -------------------- UDP Protocol (asyncio DatagramProtocol) --------------------
class VoipUdpProtocol(asyncio.DatagramProtocol):
    def __init__(self):
        super().__init__()
        # Ensure output file exists
        OUTPUT_FILE.touch(exist_ok=True)

    def connection_made(self, transport):
        self.transport = transport
        print(f"UDP server started on {UDP_HOST}:{UDP_PORT}")

    def datagram_received(self, data: bytes, addr):
        """
        Called when UDP packet is received.
        addr is (ip, port)
        """
        ip, port = addr
        client_key = f"{ip}:{port}"

        # Quick checks
        if len(data) < 32:
            # We allow for some control messages that might be ascii; handle DISCONNECT specially
            try:
                text = data.decode("utf-8", errors="ignore")
                if text.startswith("DISCONNECT:"):
                    self.handle_disconnect_msg(client_key, text)
                    return
            except Exception:
                pass

            print(f"⚠️  Pachet prea mic de la {client_key}, length={len(data)}")
            return

        # parse header
        try:
            seq_number = struct.unpack_from("!Q", data, 0)[0]           # 0..7
            timestamp = struct.unpack_from("!Q", data, 8)[0]            # 8..15
            ws_id_bytes = data[16:32]                                   # 16..31 (16 bytes)
            audio_buffer = data[32:]                                    # rest
        except Exception as e:
            print("Eroare parsare header:", e)
            return

        # convert uuid bytes to string
        try:
            ws_uuid = str(uuid.UUID(bytes=bytes(ws_id_bytes)))
        except Exception:
            # fallback: hex representation
            ws_uuid = ws_id_bytes.hex()

        # register client if new
        if client_key not in clients:
            clients[client_key] = (ip, port)
            client_udp_to_ws[client_key] = ws_uuid
            print(f"Client nou: {client_key} -> WS_ID {ws_uuid}")

        # increment received packets
        client_data[client_key]["receivedPackets"] = client_data[client_key].get("receivedPackets", 0) + 1

        # latency & jitter
        self._handle_latency_and_jitter(client_key, timestamp)

        # packet loss
        self._handle_packet_loss(client_key, seq_number)

        # write audio to file (append raw bytes)
        try:
            with OUTPUT_FILE.open("ab") as f:
                f.write(audio_buffer)
        except Exception as e:
            print("Eroare la scrierea audio:", e)

        # broadcast to other clients
        self._broadcast_audio(client_key, audio_buffer)

    def _handle_latency_and_jitter(self, client_key: str, timestamp_ms: int):
        now = int(round(asyncio.get_event_loop().time() * 1000))  # monotonic-ish ms via loop time
        # Note: clients may send timestamp using time.time()*1000 on their side. We'll approximate.
        if client_key not in client_offset:
            # rough offset (absolute difference)
            client_offset[client_key] = abs(now - timestamp_ms)

        latency = (now - timestamp_ms) + client_offset[client_key]
        if latency > 0:
            lst = latency_stats[client_key]
            lst.append(latency)
            if len(lst) > 50:
                lst.pop(0)

        # jitter = |latency - prev_latency|
        lst = latency_stats[client_key]
        if len(lst) > 1:
            prev = lst[-2]
            jitter = abs(latency - prev)
            jlst = jitter_stats[client_key]
            jlst.append(jitter)
            if len(jlst) > 50:
                jlst.pop(0)

    def _handle_packet_loss(self, client_key: str, seq_number: int):
        last = last_packet.get(client_key)
        if last is not None:
            if seq_number != last + 1:
                client_data[client_key]["lostPackets"] = client_data[client_key].get("lostPackets", 0) + 1
        last_packet[client_key] = seq_number

    def _broadcast_audio(self, sender_key: str, audio_buffer: bytes):
        for other_key, (ip, port) in list(clients.items()):
            if other_key == sender_key:
                continue
            try:
                self.transport.sendto(audio_buffer, (ip, port))
            except Exception as e:
                print(f"Eroare trimitere la {other_key}: {e}")

    def handle_disconnect_msg(self, client_key: str, text: str):
        # text format: DISCONNECT:<networkType>:<stars>
        if client_key not in clients:
            return
        parts = text.split(":")
        network_type = parts[1] if len(parts) > 1 else "unknown"
        stars = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0

        jitters = jitter_stats.get(client_key, [])
        avg_jitter = sum(jitters) / len(jitters) if jitters else 0

        latencies = latency_stats.get(client_key, [])
        avg_latency = sum(latencies) / len(latencies) if latencies else 0

        received = client_data[client_key].get("receivedPackets", 1)
        lost = client_data[client_key].get("lostPackets", 0)
        packet_loss = (lost / received) * 100 if received > 0 else 0.0

        print(f"Client {client_key} deconectat:")
        print(f" - Packet Loss: {packet_loss:.2f}%")
        print(f" - Avg Jitter: {avg_jitter:.2f} ms")
        print(f" - Avg Latency: {avg_latency:.2f} ms")
        print(f" - Network: {network_type}")
        print(f" - Clients: {len(clients)}")
        print(f" - Stars: {stars}")

        write_stats_to_csv(packet_loss, avg_jitter, avg_latency, network_type, stars)

        # cleanup
        clients.pop(client_key, None)
        client_udp_to_ws.pop(client_key, None)
        latency_stats.pop(client_key, None)
        jitter_stats.pop(client_key, None)
        last_packet.pop(client_key, None)
        client_offset.pop(client_key, None)
        client_data.pop(client_key, None)


# -------------------- WebSocket server --------------------
# Simple handler: on CONN -> send {type: "ID", id: "<uuid>"}
# We don't store WS->UDP mapping here; UDP packets include the uuid in header.
async def ws_handler(websocket):
    """
    websocket is a websockets.server.WebSocketServerProtocol
    """
    peer = websocket.remote_address
    print("New WS connection from", peer)
    try:
        async for raw in websocket:
            try:
                msg = json.loads(raw)
            except Exception:
                # If a plain string arrives, ignore or echo
                print("WS received non-JSON:", raw)
                continue

            if msg.get("type") == "CONN":
                new_id = generate_user_id()
                resp = {"type": "ID", "id": new_id}
                await websocket.send(json.dumps(resp))
                print(f"Assigned WS id {new_id} to {peer}")
            
            if msg.get("type") == "MSG":
                print(f"Client ${msg.get("sender_id")} sent message ${msg.get("data")}. Check toxicity")
                await checkWordsToxicity(msg.get('sender_id'), msg.get('data'))


    except websockets.ConnectionClosed:
        print("WS connection closed:", peer)
    except Exception as e:
        print("WS handler error:", e)

#--------------------- Chreck word toxicity----------------------#

async def checkWordsToxicity(sender_id, data):
    toxicity_score = await check_toxicity(data)
    pprint(f'toxicity score is : {toxicity_score}')

import aiohttp
import asyncio
import time

TOXICITY_API_URL = "http://localhost:8000"  # schimbă cu URL-ul tău

async def check_toxicity(text: str, timeout=3.0, max_retries=3, backoff_base=0.5):
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    payload = {
        "text": text,
        "threshold": 0.5
    }

    attempt = 0
    while attempt < max_retries:
        attempt += 1
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(TOXICITY_API_URL+'/check', json=payload, headers=headers, timeout=timeout) as resp:
                    # status handling
                    if resp.status == 200:
                        data = await resp.json()
                        return data
                    elif resp.status in (429, 503):
                        # rate limit / service busy -> backoff and retry
                        await asyncio.sleep(backoff_base * (2 ** (attempt-1)))
                        continue
                    else:
                        # unexpected status -> read body for debug
                        text_body = await resp.text()
                        print(f"[TOXIC] Unexpected status {resp.status}: {text_body}")
                        return None
        except asyncio.TimeoutError:
            print(f"[TOXIC] Timeout on attempt {attempt}")
            await asyncio.sleep(backoff_base * (2 ** (attempt-1)))
        except Exception as e:
            print(f"[TOXIC] Network error: {e}")
            await asyncio.sleep(backoff_base * (2 ** (attempt-1)))

    print("[TOXIC] All retries failed")
    return None


# -------------------- Bootstrap --------------------
async def main():
    print("Starting servers...")
    loop = asyncio.get_running_loop()

    # Start UDP
    transport, protocol = await loop.create_datagram_endpoint(
        lambda: VoipUdpProtocol(),
        local_addr=(UDP_HOST, UDP_PORT),
    )

    # Start WebSocket server
    ws_server = await websockets.serve(ws_handler, WS_HOST, WS_PORT)
    print(f"WebSocket server listening on ws://{WS_HOST}:{WS_PORT}")

    # Run until cancelled
    try:
        await asyncio.Future()  # run forever
    finally:
        ws_server.close()
        await ws_server.wait_closed()
        transport.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Server oprit manual.")
