const dgram = require('dgram');
const fs = require('fs');

const path = require('path')
const server = dgram.createSocket('udp4');
const file = fs.createWriteStream('output.pcm', { flags: 'a' });

const clients = new Map();
const latencyStats = new Map(); // clientId => [valori recente]
const jitterStats = new Map();
const lastPacket = new Map();
const clientData = {}
const clientOffset = new Map(); // clientId => offset

function writeStatsToCSV(stats) {
  const filePath = path.join(__dirname, 'client_stats.csv');

  // Verificăm dacă fișierul există, altfel scriem headerul
  const writeHeader = !fs.existsSync(filePath);
  const line = `${stats.packetLoss},${stats.averageJitter},${stats.avgLatency},${stats.networkType}\n`;

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
      const jitters = jitterStats.get(clientId) || [];
      const averageJitter = jitters.reduce((a, b) => a + b, 0) / jitters.length;

      const latencies = latencyStats.get(clientId) || [];
      const avgLatency = latencies.reduce((a, b) => a + b, 0) / latencies.length;

      
      const packetLoss =  (clientData.lostPackets ?? 0 / clientData.receivedPackets) * 100;

      console.log(` - Packet Loss: ${packetLoss.toFixed(2)}%`);
      console.log(` - Avg Jitter: ${averageJitter.toFixed(2)} ms`);
      console.log(` - Avg Latency: ${avgLatency.toFixed(2)} ms`);
      console.log(` - Network: ${networkType}`);

      writeStatsToCSV({
        packetLoss: packetLoss.toFixed(2),
        averageJitter: averageJitter.toFixed(2),
        avgLatency: avgLatency.toFixed(2),
        networkType
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
 
  const seqNumber = msg.readBigUInt64BE(0);    // de la byte 0 la 7
  const timestamp = msg.readBigUInt64BE(8);    // de la byte 8 la 15
  const audioBuffer = msg.slice(16);            // restul e audio raw

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
  
  // Înregistrăm clientul dacă nu există
  if (!clients.has(clientId)) {
    clients.set(clientId, { address: rinfo.address, port: rinfo.port });
    console.log(`Client nou: ${rinfo.address}:${rinfo.port}`);
  }
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

server.bind(41234); // port implicit, îl poți schimba
