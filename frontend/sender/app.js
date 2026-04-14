/**
 * Sender application logic
 */

class SenderApp {
    constructor() {
        this.audioCapture = null;
        this.websocket = null;
        this.sessionId = null;
        this.isConnected = false;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;

        // UI elements
        this.statusEl = document.getElementById('status');
        this.sessionIdEl = document.getElementById('sessionId');
        this.sessionInfoEl = document.getElementById('sessionInfo');
        this.providerEl = document.getElementById('provider');
        this.startBtn = document.getElementById('startBtn');
        this.stopBtn = document.getElementById('stopBtn');
        this.serverUrlInput = document.getElementById('serverUrl');
        this.audioLevelFill = document.getElementById('audioLevelFill');
        this.receiverUrlEl = document.getElementById('receiverUrl');

        this.bindEvents();
    }

    bindEvents() {
        this.startBtn.addEventListener('click', () => this.start());
        this.stopBtn.addEventListener('click', () => this.stop());
    }

    async start() {
        try {
            this.updateStatus('connecting', 'Initializing...');
            this.startBtn.disabled = true;

            // Check browser support
            if (!AudioCapture.isSupported()) {
                throw new Error('Your browser does not support audio capture');
            }

            // Initialize audio capture
            this.audioCapture = new AudioCapture();
            await this.audioCapture.initialize();

            // Set up audio chunk callback
            this.audioCapture.onAudioChunk = (blob) => this.handleAudioChunk(blob);

            // Set up audio level callback
            this.audioCapture.onAudioLevel = (level) => this.updateAudioLevel(level);

            // Connect to WebSocket
            await this.connectWebSocket();

            // Start recording
            this.audioCapture.startRecording();
            this.updateStatus('streaming', 'Streaming audio...');
            this.stopBtn.disabled = false;

        } catch (error) {
            console.error('Failed to start:', error);
            this.updateStatus('disconnected', `Error: ${error.message}`);
            this.startBtn.disabled = false;
            this.cleanup();
        }
    }

    async stop() {
        this.updateStatus('disconnected', 'Stopping...');
        this.stopBtn.disabled = true;

        // Send end message
        if (this.websocket && this.websocket.readyState === WebSocket.OPEN) {
            this.websocket.send(JSON.stringify({ type: 'end' }));
        }

        this.cleanup();
        this.updateStatus('disconnected', 'Disconnected');
        this.startBtn.disabled = false;
    }

    cleanup() {
        if (this.audioCapture) {
            this.audioCapture.release();
            this.audioCapture = null;
        }

        if (this.websocket) {
            this.websocket.close();
            this.websocket = null;
        }

        this.isConnected = false;
        this.sessionId = null;
        this.sessionInfoEl.style.display = 'none';
        this.receiverUrlEl.textContent = '-';
    }

    async connectWebSocket() {
        return new Promise((resolve, reject) => {
            const serverUrl = this.serverUrlInput.value.trim();

            this.updateStatus('connecting', 'Connecting to server...');

            this.websocket = new WebSocket(serverUrl);

            this.websocket.onopen = () => {
                console.log('WebSocket connected');
                this.isConnected = true;
                this.reconnectAttempts = 0;

                // Send initialization message
                this.websocket.send(JSON.stringify({ type: 'init' }));
            };

            this.websocket.onmessage = (event) => {
                try {
                    const message = JSON.parse(event.data);
                    this.handleServerMessage(message);

                    // Resolve promise on session created
                    if (message.type === 'session_created') {
                        resolve();
                    }
                } catch (error) {
                    console.error('Failed to parse message:', error);
                }
            };

            this.websocket.onerror = (error) => {
                console.error('WebSocket error:', error);
                reject(new Error('WebSocket connection failed'));
            };

            this.websocket.onclose = () => {
                console.log('WebSocket closed');
                this.isConnected = false;

                if (this.audioCapture && this.audioCapture.isRecording) {
                    this.handleDisconnect();
                }
            };

            // Timeout after 10 seconds
            setTimeout(() => {
                if (!this.isConnected) {
                    reject(new Error('Connection timeout'));
                }
            }, 10000);
        });
    }

    handleServerMessage(message) {
        console.log('Server message:', message);

        switch (message.type) {
            case 'session_created':
                this.sessionId = message.session_id;
                this.sessionIdEl.textContent = this.sessionId;
                this.providerEl.textContent = message.provider;
                this.sessionInfoEl.style.display = 'block';
                this.updateReceiverUrl();
                this.updateStatus('connected', 'Connected! Ready to stream.');
                break;

            case 'error':
                console.error('Server error:', message.message);
                this.updateStatus('disconnected', `Error: ${message.message}`);
                this.stop();
                break;

            case 'status':
                console.log('Status update:', message.status);
                break;

            default:
                console.log('Unknown message type:', message.type);
        }
    }

    async handleAudioChunk(blob) {
        if (!this.websocket || this.websocket.readyState !== WebSocket.OPEN) {
            console.warn('WebSocket not ready, dropping audio chunk');
            return;
        }

        try {
            // Convert blob to array buffer and send
            const arrayBuffer = await blob.arrayBuffer();
            this.websocket.send(arrayBuffer);
        } catch (error) {
            console.error('Failed to send audio chunk:', error);
        }
    }

    updateAudioLevel(level) {
        // Update visual audio level indicator
        const percentage = Math.min(100, level * 200); // Amplify for better visibility
        this.audioLevelFill.style.width = `${percentage}%`;
    }

    updateStatus(state, message) {
        this.statusEl.className = `status ${state}`;
        this.statusEl.textContent = message;
    }

    updateReceiverUrl() {
        if (!this.sessionId) {
            this.receiverUrlEl.textContent = '-';
            return;
        }

        const protocol = window.location.protocol === 'https:' ? 'https:' : 'http:';
        const host = this.serverUrlInput.value.replace('ws://', '').replace('wss://', '').split('/')[0];
        const receiverUrl = `${protocol}//${host.replace(':8000', ':8081')}/index.html?session=${this.sessionId}`;

        this.receiverUrlEl.innerHTML = `<a href="${receiverUrl}" target="_blank">${receiverUrl}</a>`;
    }

    handleDisconnect() {
        console.log('Handling disconnect...');
        this.updateStatus('disconnected', 'Connection lost');

        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            console.log(`Reconnect attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts}`);

            setTimeout(() => {
                if (!this.isConnected && this.audioCapture) {
                    this.connectWebSocket().catch(console.error);
                }
            }, 2000 * this.reconnectAttempts);
        } else {
            this.stop();
        }
    }
}

// Initialize app when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.app = new SenderApp();
    console.log('Sender app initialized');
});
