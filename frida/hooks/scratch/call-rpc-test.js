const http = require('http');

function request(options, postData) {
    return new Promise((resolve, reject) => {
        const req = http.request(options, (res) => {
            let data = '';
            res.on('data', (chunk) => data += chunk);
            res.on('end', () => {
                try { resolve(JSON.parse(data)); }
                catch (e) { resolve(data); }
            });
        });
        req.on('error', (err) => reject(err));
        if (postData) {
            req.write(JSON.stringify(postData));
        }
        req.end();
    });
}

async function main() {
    try {
        console.log("Fetching active Frida sessions...");
        const sessions = await request({
            host: '127.0.0.1',
            port: 8765,
            path: '/api/sessions',
            method: 'GET'
        });

        console.log("Sessions found:", sessions);
        const runningSession = sessions.find(s => s.status === 'running');
        if (!runningSession) {
            console.error("No active running Frida session found!");
            return;
        }

        const sessionId = runningSession.id;
        console.log(`Calling testUnityFind RPC on Session ID ${sessionId}...`);
        
        const response = await request({
            host: '127.0.0.1',
            port: 8765,
            path: `/api/scripts/${sessionId}/rpc`,
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        }, {
            method: 'testUnityFind',
            args: []
        });

        console.log("RPC Response:", response);
    } catch (e) {
        console.error("Error calling RPC:", e);
    }
}

main();
