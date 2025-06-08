const dgram = require('dgram');
const fs = require('fs');

const server = dgram.createSocket('udp4');
const file = fs.createWriteStream('output.pcm', { flags: 'a' });

const clients = new Map();

server.on('message', (msg, rinfo) => {
  //const clientKey = `${rinfo.address}:${rinfo.port}`;
  const clientId = `${rinfo.address}:${rinfo.port}`; // identificare unică per client

  // Înregistrăm clientul dacă nu există
  if (!clients.has(clientId)) {
    clients.set(clientId, { address: rinfo.address, port: rinfo.port });
    console.log(`Client nou: ${rinfo.address}:${rinfo.port}`);
  }

  console.log(`Received ${msg.length} bytes from ${rinfo.address}:${rinfo.port}`);
  file.write(msg);
  // Relay către toți ceilalți clienți
  for (const [key, client] of clients.entries()) {
    if (key !== clientId) {
      server.send(msg, client.port, client.address, err => {
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
