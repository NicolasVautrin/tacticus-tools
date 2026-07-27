/**
 * Proxy HTTP CONNECT qui COMPTE les octets par tunnel — sans dechiffrer quoi que ce soit.
 *
 * Pourquoi CONNECT et pas un MITM TLS : on veut mesurer le VOLUME reellement emis sur le
 * fil, pas lire le contenu. Le tunnel reste chiffre de bout en bout ; on ne fait que
 * compter les octets qui transitent dans chaque sens. Aucun certificat a installer.
 *
 * POURQUOI cet outil plutot qu'un compteur systeme (les deux voies ont ete testees et
 * ECARTEES le 2026-07-27, ne pas les retenter sans droits admin) :
 *   - ETW `Microsoft-Windows-Kernel-Network` (la methode canonique, octets par PID) :
 *     `logman create trace ... -ets` rend "Acces refuse" meme en etant membre de
 *     "Utilisateurs du journal de performances" — ce groupe donne les compteurs de perf,
 *     PAS la creation de session ETW. Il faut une elevation.
 *   - Compteurs d'E/S par processus (`Get-Process | Write/Other/ReadTransferCount`) :
 *     mesure faite, ZERO octet sur tous les processus claude pendant que l'adaptateur
 *     Wi-Fi envoyait 2,8 Mo. Sous Windows les envois sur SOCKET n'y sont pas comptes.
 *
 * GRANULARITE — c'est du PAR SESSION, pas du par agent. Un sous-agent ne cree pas de
 * processus : il tourne dans le processus de sa session parente (mesure : 5 processus CLI
 * pour 5 sessions, alors que 6 agents tournaient). Le proxy voit donc "session + tous ses
 * agents" agrege, et les tunnels TLS vers un hote unique n'offrent rien pour discriminer.
 * Pour du PAR AGENT, passer par les tokens (transcripts + `subagent_tokens`), pas le reseau.
 *
 * Usage :
 *   node scripts/node/count_proxy.js [port]        # defaut 8899
 *   HTTPS_PROXY=http://127.0.0.1:8899 claude       # la session a isoler
 *   curl http://127.0.0.1:8899/stats               # lire sans tuer le proxy
 *   curl http://127.0.0.1:8899/reset               # repartir de zero
 *
 * Le endpoint /stats est indispensable sous Windows : les signaux gracieux (SIGTERM) n'y
 * sont pas fiables, un rapport declenche uniquement sur signal se perdrait.
 *
 * Ordre de grandeur mesure : un `claude -p` d'un mot = 1,71 Mo MONTANTS vers
 * api.anthropic.com (le contexte complet est reexpedie a chaque tour) + 122 Ko de
 * telemetrie Datadog, que ni l'adaptateur ni `Get-NetTCPConnection` ne distinguaient.
 */
'use strict';

const http = require('http');
const net = require('net');

const PORT = parseInt(process.argv[2] || '8899', 10);

/** @type {Map<string, {up: number, down: number, tunnels: number}>} */
const byHost = new Map();
let totalUp = 0;
let totalDown = 0;
let openTunnels = 0;
const startedAt = Date.now();

function bump(host, up, down) {
  const e = byHost.get(host) || { up: 0, down: 0, tunnels: 0 };
  e.up += up;
  e.down += down;
  byHost.set(host, e);
}

const server = http.createServer((req, res) => {
  // `curl http://127.0.0.1:<port>/stats` rend le compteur SANS tuer le proxy.
  // Necessaire sous Windows, ou les signaux gracieux (SIGTERM) ne sont pas fiables :
  // compter sur un handler de signal pour obtenir le rapport perdrait la mesure.
  if (req.url === '/stats' || req.url === '/') {
    res.writeHead(200, { 'content-type': 'text/plain; charset=utf-8' });
    res.end(reportText());
    return;
  }
  if (req.url === '/reset') {
    byHost.clear();
    totalUp = 0;
    totalDown = 0;
    res.writeHead(200, { 'content-type': 'text/plain' });
    res.end('compteurs remis a zero\n');
    return;
  }
  // Trafic HTTP en clair : non attendu ici (l'API est en HTTPS), on refuse proprement.
  res.writeHead(405, { 'content-type': 'text/plain' });
  res.end('proxy CONNECT uniquement — voir /stats\n');
});

server.on('connect', (req, clientSocket, head) => {
  const [host, portStr] = req.url.split(':');
  const port = parseInt(portStr || '443', 10);

  const upstream = net.connect(port, host, () => {
    openTunnels++;
    const e = byHost.get(host) || { up: 0, down: 0, tunnels: 0 };
    e.tunnels++;
    byHost.set(host, e);

    clientSocket.write('HTTP/1.1 200 Connection Established\r\n\r\n');
    if (head && head.length) {
      upstream.write(head);
      totalUp += head.length;
      bump(host, head.length, 0);
    }

    // client -> serveur = MONTANT (ce qu'on cherche a mesurer)
    clientSocket.on('data', (chunk) => {
      totalUp += chunk.length;
      bump(host, chunk.length, 0);
    });
    // serveur -> client = DESCENDANT
    upstream.on('data', (chunk) => {
      totalDown += chunk.length;
      bump(host, 0, chunk.length);
    });

    clientSocket.pipe(upstream);
    upstream.pipe(clientSocket);
  });

  const close = () => {
    openTunnels = Math.max(0, openTunnels - 1);
    clientSocket.destroy();
    upstream.destroy();
  };
  upstream.on('error', close);
  clientSocket.on('error', close);
  upstream.on('end', close);
  clientSocket.on('end', close);
});

function human(n) {
  if (n >= 1024 * 1024) return (n / 1024 / 1024).toFixed(2) + ' Mo';
  if (n >= 1024) return (n / 1024).toFixed(1) + ' Ko';
  return n + ' o';
}

function reportText() {
  const secs = Math.max(1, (Date.now() - startedAt) / 1000);
  const lines = [];
  lines.push('=== octets par destination ===');
  const rows = [...byHost.entries()].sort((a, b) => b[1].up - a[1].up);
  for (const [host, e] of rows) {
    lines.push(
      `  ${host.padEnd(34)} UP ${human(e.up).padStart(10)}   DOWN ${human(e.down).padStart(10)}   ${e.tunnels} tunnels`,
    );
  }
  lines.push('');
  lines.push(`TOTAL   UP ${human(totalUp)}   DOWN ${human(totalDown)}   ratio ${(totalUp / Math.max(1, totalDown)).toFixed(1)}x`);
  lines.push(`DUREE   ${secs.toFixed(1)} s   =>  ${human(totalUp / secs)}/s en montee`);
  lines.push(`TUNNELS ouverts actuellement : ${openTunnels}`);
  return lines.join('\n') + '\n';
}

function report() {
  console.log('');
  console.log(reportText());
}

process.on('SIGINT', () => {
  report();
  process.exit(0);
});
process.on('SIGTERM', () => {
  report();
  process.exit(0);
});

server.listen(PORT, '127.0.0.1', () => {
  console.log(`proxy compteur sur 127.0.0.1:${PORT} — HTTPS_PROXY=http://127.0.0.1:${PORT}`);
});
