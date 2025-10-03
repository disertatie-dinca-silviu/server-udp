import dgram from 'dgram';
import fs from 'fs';
import path from 'path';
import { v4 as uuidv4 } from 'uuid';
import { WebSocketServer } from 'ws';
import { parse as uuidParse, stringify as uuidStringify } from 'uuid';

const server = dgram.createSocket('udp4');
const file = fs.createWriteStream('output.pcm', { flags: 'a' });

const clients = new Map();
const latencyStats = new Map(); // clientId => [valori recente]
const jitterStats = new Map();
const lastPacket = new Map();
const clientData = {}
const clientOffset = new Map(); // clientId => offset
const clientUdpToWebSocket = new Map()

function writeStatsToCSV(stats) {
  const filePath = 'client_stats.csv';

  // Verificăm dacă fișierul există, altfel scriem headerul
  const writeHeader = !fs.existsSync(filePath);

  //calculam numar clienti
  const clientCount = clients.size;
  const line = `${stats.packetLoss},${stats.averageJitter},${stats.avgLatency},${stats.networkType},${clientCount},${stats.stars}\n`;

  const header = 'PacketLoss(%),Jitter(ms),Latency(ms),NetworkType\n';

  fs.appendFile(filePath, writeHeader ? header + line : line, (err) => {
    if (err) {
      console.error('Eroare la scrierea în CSV:', err);
    } else {
      console.log(`Statistici salvate`);
    }
  });
}

server.on('message', (msg, rinfo) => {
  //const clientKey = `${rinfo.address}:${rinfo.port}`;
  const clientId = `${rinfo.address}:${rinfo.port}`; // identificare unică per client
  
  if (msg.toString().includes('DISCONNECT:')) {
    // Dacă clientul trimite un mesaj de deconectare, îl eliminăm
    if (clients.has(clientId)) {

      console.log(`Client ${clientId} deconectat:`);

      const disconnectMessage = msg.toString().split(':')

      const networkType = disconnectMessage.at(1)
      const stars = disconnectMessage.at(2) || 0;

      const jitters = jitterStats.get(clientId) || [];
      const averageJitter = jitters.reduce((a, b) => a + b, 0) / jitters.length;

      const latencies = latencyStats.get(clientId) || [];
      const avgLatency = latencies.reduce((a, b) => a + b, 0) / latencies.length;

      
      const packetLoss =  (clientData.lostPackets ?? 0 / clientData.receivedPackets) * 100;
//calculam numar clienti
const clientCount = clients.size;
      console.log(` - Packet Loss: ${packetLoss.toFixed(2)}%`);
      console.log(` - Avg Jitter: ${averageJitter.toFixed(2)} ms`);
      console.log(` - Avg Latency: ${avgLatency.toFixed(2)} ms`);
      console.log(` - Network: ${networkType}`);
      console.log(` - clients: ${clientCount}`);
      console.log(` - stars: ${stars}`);

      writeStatsToCSV({
        packetLoss: packetLoss.toFixed(2),
        averageJitter: averageJitter.toFixed(2),
        avgLatency: avgLatency.toFixed(2),
        networkType,
        stars,
      })
      clients.delete(clientId);
    }
    return;
  }


   // Verificăm dacă e un pachet valid cu header de 16 bytes
   if (msg.length < 16) {
    console.warn(`Pachet prea mic primit de la ${clientId}: ${msg.toString()}`);
    return;
  }
  
  // buffer are 16 bytes
  const wsIdBuffer = msg.slice(16, 32);
  const webSocketClientId = uuidStringify(wsIdBuffer);  // devine string normal UUID

   // Înregistrăm clientul dacă nu există
   if (!clients.has(clientId)) {
    clients.set(clientId, { address: rinfo.address, port: rinfo.port });
    clientUdpToWebSocket.set(clientId, webSocketClientId)
    console.log(`Client nou: ${rinfo.address}:${rinfo.port} si websocket id : ${webSocketClientId}`);
  }


 
  const seqNumber = msg.readBigUInt64BE(0);    // de la byte 0 la 7
  const timestamp = msg.readBigUInt64BE(8);    // de la byte 8 la 15
  const audioBuffer = msg.slice(32);            // restul e audio raw

  clientData.receivedPackets = (clientData.receivedPackets || 0) + 1;

  const now = Date.now(); // în milisecunde

  if (!clientOffset.has(clientId)) {
    // Setăm offset-ul pentru client dacă nu există
    clientOffset.set(clientId, Math.abs(now - Number(timestamp)));
  }

  const latency = now - Number(timestamp) + clientOffset.get(clientId); // calculăm latența 

  let latencies = latencyStats.get(clientId) || [];
  if (latency > 0) latencies.push(latency);
  if (latencies.length > 50) latencies.shift(); // menținem ultimele 50
  latencyStats.set(clientId, latencies);

  if (latencies.length > 2) {
    const previousLatency = latencies.at(-2)
    const jitter = Math.abs(latency - previousLatency)


    let jitters = jitterStats.get(clientId) || [];
    jitters.push(jitter);
    if (jitters.length > 50) jitters.shift(); // păstrează doar ultimele 50 valori
    jitterStats.set(clientId, jitters);

    const avgJitter = jitters.reduce((a, b) => a + b, 0) / jitters.length;
    //console.log(`Jitter mediu pentru ${clientId}: ${avgJitter.toFixed(2)} ms`);
  }
 
  const lastPacketOfThis = lastPacket.get(clientId)
  if (!lastPacketOfThis) {
    lastPacket.set(seqNumber);
  } else {
    if (seqNumber != lastPacketOfThis+1) {
      if (clientData.lostPackets)
        clientData.lostPackets += 1;
      else 
        clientData.lostPackets = 0;
    }
  }

  lastPacket.set(seqNumber)
  
  file.write(audioBuffer);
  for (const [key, client] of clients.entries()) {
    if (key !== clientId) {
      server.send(audioBuffer, client.port, client.address, err => {
        if (err) {
          console.error(`Eroare la trimiterea către ${client.address}:${client.port}:`, err);
        }
      });
    }
  }
});

server.on('listening', () => {
  const address = server.address();
  console.log(`Server UDP ascultă pe ${address.address}:${address.port}`);
});



// Create a WebSocket server on port 8080
const wss = new WebSocketServer({ port: 8080 });


// Connection event handler
wss.on('connection', (ws) => {
  console.log('New client connected');
  
  // Send a welcome message to the client


  // Message event handler
  ws.on('message', (message) => {
    console.log(`Received: ${message}`);
    const messageObject = JSON.parse(message)
    if (messageObject.type === 'CONN') {
        // Echo the message back to the client
        const newUserId = generateUserId()
        ws.send(JSON.stringify({
          id: newUserId.toString()
        }));
    }
   
  });

  // Close event handler
  ws.on('close', () => {
    console.log('Client disconnected');
  });
});

function  generateUserId() {
  return uuidv4()
}

server.bind(41234); // port implicit, îl poți schimba
