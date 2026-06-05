/**
 * Receiver application logic
 */

class ReceiverApp {
    constructor() {
        this.websocket = null;
        this.sessionId = null;
        this.isConnected = false;
        this.transcripts = [];
        this.currentPartial = null;
        this.startTime = null;
        this.timerInterval = null;

        // Stats
        this.stats = {
            totalWords: 0,
            finalTranscripts: 0,
        };

        // UI elements
        this.statusEl = document.getElementById('status');
        this.sessionIdEl = document.getElementById('sessionId');
        this.sessionInfoEl = document.getElementById('sessionInfo');
        this.sessionIdInput = document.getElementById('sessionIdInput');
        this.transcriptContent = document.getElementById('transcriptContent');
        this.copyBtn = document.getElementById('copyBtn');
        this.clearBtn = document.getElementById('clearBtn');
        this.totalWordsEl = document.getElementById('totalWords');
        this.finalTranscriptsEl = document.getElementById('finalTranscripts');
        this.connectionTimeEl = document.getElementById('connectionTime');

        this.bindEvents();
        this.init();
    }

    bindEvents() {
        this.copyBtn.addEventListener('click', () => this.copyTranscript());
        this.clearBtn.addEventListener('click', () => this.clearTranscript());
        this.sessionIdInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                this.connect();
            }
        });
    }

    init() {
        // Check for session ID in URL parameters
        const urlParams = new URLSearchParams(window.location.search);
        const sessionId = urlParams.get('session');

        if (sessionId) {
            this.sessionIdInput.value = sessionId;
            this.connect();
        }
    }

    async connect() {
        const sessionId = this.sessionIdInput.value.trim();

        if (!sessionId) {
            alert('Please enter a session ID');
            return;
        }

        this.sessionId = sessionId;
        this.updateStatus('connecting', 'Connecting...');

        try {
            await this.connectWebSocket();
        } catch (error) {
            console.error('Connection failed:', error);
            this.updateStatus('disconnected', `Connection failed: ${error.message}`);
        }
    }

    async connectWebSocket() {
        return new Promise((resolve, reject) => {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const host = window.location.hostname || 'localhost';
            const port = '8000'; // Backend port
            const url = `${protocol}//${host}:${port}/ws/receiver/${this.sessionId}`;

            console.log('Connecting to:', url);

            this.websocket = new WebSocket(url);

            this.websocket.onopen = () => {
                console.log('WebSocket connected');
                this.isConnected = true;
                this.startTime = Date.now();
                this.startTimer();
                resolve();
            };

            this.websocket.onmessage = (event) => {
                try {
                    const message = JSON.parse(event.data);
                    this.handleServerMessage(message);
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
                this.stopTimer();
                this.updateStatus('disconnected', 'Disconnected');
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
            case 'receiver_connected':
                this.updateStatus('connected', 'Connected - Receiving transcripts');
                this.sessionIdEl.textContent = message.session_id;
                this.sessionInfoEl.style.display = 'block';
                break;

            case 'transcript_partial':
                this.handlePartialTranscript(message);
                break;

            case 'transcript_final':
                this.handleFinalTranscript(message);
                break;

            case 'status':
                console.log('Status:', message.status);
                break;

            case 'error':
                console.error('Server error:', message.message);
                this.updateStatus('disconnected', `Error: ${message.message}`);
                break;

            case 'ping':
                // Keepalive ping
                this.websocket.send(JSON.stringify({ type: 'pong' }));
                break;

            default:
                console.log('Unknown message type:', message.type);
        }
    }

    handlePartialTranscript(message) {
        const text = message.text;

        if (!text || !text.trim()) {
            return;
        }

        // Update or create partial transcript element
        if (!this.currentPartial) {
            this.currentPartial = this.createTranscriptElement(text, false, message.confidence);
            this.appendTranscript(this.currentPartial);
        } else {
            this.updateTranscriptElement(this.currentPartial, text, message.confidence);
        }

        this.scrollToBottom();
    }

    handleFinalTranscript(message) {
        const text = message.text;

        if (!text || !text.trim()) {
            return;
        }

        // Convert partial to final or create new final
        if (this.currentPartial) {
            this.currentPartial.remove();
            this.currentPartial = null;
        }

        const finalElement = this.createTranscriptElement(text, true, message.confidence);
        this.appendTranscript(finalElement);
        this.transcripts.push(text);

        // Update stats
        this.stats.totalWords += text.split(/\s+/).length;
        this.stats.finalTranscripts++;
        this.updateStats();

        this.scrollToBottom();
    }

    createTranscriptElement(text, isFinal, confidence) {
        const div = document.createElement('div');
        div.className = `transcript-line ${isFinal ? 'final' : 'partial'} new`;

        const textSpan = document.createElement('span');
        textSpan.textContent = text;
        div.appendChild(textSpan);

        if (confidence !== null && confidence !== undefined) {
            const confidenceSpan = document.createElement('span');
            confidenceSpan.className = 'confidence';
            confidenceSpan.textContent = `(${(confidence * 100).toFixed(0)}%)`;
            div.appendChild(confidenceSpan);
        }

        // Remove 'new' class after animation
        setTimeout(() => {
            div.classList.remove('new');
        }, 300);

        return div;
    }

    updateTranscriptElement(element, text, confidence) {
        const textSpan = element.querySelector('span:first-child');
        if (textSpan) {
            textSpan.textContent = text;
        }

        if (confidence !== null && confidence !== undefined) {
            let confidenceSpan = element.querySelector('.confidence');
            if (!confidenceSpan) {
                confidenceSpan = document.createElement('span');
                confidenceSpan.className = 'confidence';
                element.appendChild(confidenceSpan);
            }
            confidenceSpan.textContent = `(${(confidence * 100).toFixed(0)}%)`;
        }
    }

    appendTranscript(element) {
        // Remove empty state if present
        const emptyState = this.transcriptContent.querySelector('.empty-state');
        if (emptyState) {
            emptyState.remove();
        }

        this.transcriptContent.appendChild(element);
    }

    scrollToBottom() {
        this.transcriptContent.scrollTop = this.transcriptContent.scrollHeight;
    }

    copyTranscript() {
        const text = this.transcripts.join(' ');

        if (!text) {
            alert('No transcript to copy');
            return;
        }

        navigator.clipboard.writeText(text).then(() => {
            this.copyBtn.textContent = '✓ Copied!';
            setTimeout(() => {
                this.copyBtn.textContent = '📋 Copy';
            }, 2000);
        }).catch(err => {
            console.error('Failed to copy:', err);
            alert('Failed to copy transcript');
        });
    }

    clearTranscript() {
        if (!confirm('Clear all transcripts?')) {
            return;
        }

        this.transcripts = [];
        this.currentPartial = null;
        this.stats.totalWords = 0;
        this.stats.finalTranscripts = 0;

        this.transcriptContent.innerHTML = `
            <div class="empty-state">
                <svg viewBox="0 0 24 24" fill="currentColor">
                    <path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3z"/>
                    <path d="M17 11c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c3.39-.49 6-3.39 6-6.92h-2z"/>
                </svg>
                <p>Waiting for audio stream...</p>
            </div>
        `;

        this.updateStats();
    }

    updateStatus(state, message) {
        this.statusEl.className = `status ${state}`;
        this.statusEl.innerHTML = `
            <span class="status-dot"></span>
            ${message}
        `;
    }

    updateStats() {
        this.totalWordsEl.textContent = this.stats.totalWords;
        this.finalTranscriptsEl.textContent = this.stats.finalTranscripts;
    }

    startTimer() {
        this.timerInterval = setInterval(() => {
            if (!this.startTime) return;

            const elapsed = Date.now() - this.startTime;
            const minutes = Math.floor(elapsed / 60000);
            const seconds = Math.floor((elapsed % 60000) / 1000);

            this.connectionTimeEl.textContent =
                `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
        }, 1000);
    }

    stopTimer() {
        if (this.timerInterval) {
            clearInterval(this.timerInterval);
            this.timerInterval = null;
        }
    }
}

// Initialize app when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.app = new ReceiverApp();
    console.log('Receiver app initialized');
});
