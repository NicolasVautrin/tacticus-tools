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
        console.log("Triggering re-injection...");
        const response = await request({
            host: '127.0.0.1',
            port: 8765,
            path: '/api/admin/inject',
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        }, {});

        console.log("Injection Response:", response);
    } catch (e) {
        console.error("Error triggering injection:", e);
    }
}

main();
