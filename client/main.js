const videoEl = document.getElementById('stream');
const statusEl = document.getElementById('status');
const fullscreenBtn = document.getElementById('fullscreen-btn');

let pc = null;
let ws = null;

function updateStatus(text, className) {
    statusEl.textContent = text;
    statusEl.className = className;
}

function connect() {
    updateStatus('Connecting...', 'connecting');
    
    // Connect to the WebSocket signaling server (assuming it's on port 8081 of the same host)
    const wsUrl = `ws://${window.location.hostname}:8081`;
    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
        console.log("WebSocket connected");
        updateStatus('Connected to Signalling', 'connecting');
        setupWebRTC();
    };

    ws.onmessage = async (event) => {
        const msg = JSON.parse(event.data);
        console.log("Received signaling message:", msg);

        if (msg.sdp) {
            await pc.setRemoteDescription(new RTCSessionDescription(msg.sdp));
            if (pc.remoteDescription.type === 'offer') {
                const answer = await pc.createAnswer();
                await pc.setLocalDescription(answer);
                ws.send(JSON.stringify({ sdp: pc.localDescription }));
            }
        } else if (msg.ice) {
            pc.addIceCandidate(new RTCIceCandidate(msg.ice)).catch(e => console.error("Error adding ICE", e));
        }
    };

    ws.onclose = () => {
        updateStatus('Disconnected', 'disconnected');
        if (pc) {
            pc.close();
            pc = null;
        }
        // Attempt to reconnect after a delay
        setTimeout(connect, 3000);
    };
    
    ws.onerror = (err) => {
        console.error("WebSocket error", err);
    };
}

function setupWebRTC() {
    // No STUN/TURN needed for LAN/Private network
    const configuration = {
        iceServers: []
    };
    
    pc = new RTCPeerConnection(configuration);

    pc.onicecandidate = (event) => {
        if (event.candidate) {
            ws.send(JSON.stringify({ ice: event.candidate }));
        }
    };

    pc.ontrack = (event) => {
        console.log("Received track", event.streams);
        if (videoEl.srcObject !== event.streams[0]) {
            videoEl.srcObject = event.streams[0];
            console.log("Attached video stream");
            // Force playback in case the browser blocks autoplay despite the attributes
            videoEl.play().catch(e => console.log("Auto-play prevented (needs user interaction):", e));
        }
    };

    pc.onconnectionstatechange = () => {
        console.log("Connection state:", pc.connectionState);
        if (pc.connectionState === 'connected') {
            updateStatus('Streaming', 'connected');
            // Try to unmute if the browser allows it (we stream without audio, so it doesn't strictly matter, but good practice)
            videoEl.muted = false; 
        } else if (pc.connectionState === 'disconnected' || pc.connectionState === 'failed') {
            updateStatus('Connection lost', 'disconnected');
        }
    };
    
    // We expect the server to initiate the offer, so we just wait for it.
    // However, sometimes it's good to add a transceiver to signal we want video.
    pc.addTransceiver('video', { direction: 'recvonly' });
}

fullscreenBtn.addEventListener('click', () => {
    if (videoEl.requestFullscreen) {
        videoEl.requestFullscreen();
    } else if (videoEl.webkitRequestFullscreen) { /* Safari */
        videoEl.webkitRequestFullscreen();
    } else if (videoEl.msRequestFullscreen) { /* IE11 */
        videoEl.msRequestFullscreen();
    }
});

// Start connection process
connect();
