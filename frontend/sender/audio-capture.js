/**
 * Audio capture and streaming module
 */

class AudioCapture {
    constructor() {
        this.mediaStream = null;
        this.mediaRecorder = null;
        this.audioContext = null;
        this.analyser = null;
        this.onAudioChunk = null;
        this.onAudioLevel = null;
        this.isRecording = false;
    }

    /**
     * Initialize audio capture
     */
    async initialize() {
        try {
            // Request microphone access
            this.mediaStream = await navigator.mediaDevices.getUserMedia({
                audio: {
                    echoCancellation: true,
                    noiseSuppression: true,
                    autoGainControl: true,
                    sampleRate: 16000,
                },
            });

            console.log('Microphone access granted');

            // Create audio context for level monitoring
            this.audioContext = new (window.AudioContext || window.webkitAudioContext)({
                sampleRate: 16000,
            });

            const source = this.audioContext.createMediaStreamSource(this.mediaStream);
            this.analyser = this.audioContext.createAnalyser();
            this.analyser.fftSize = 256;
            source.connect(this.analyser);

            // Start level monitoring
            this.startLevelMonitoring();

            return true;
        } catch (error) {
            console.error('Failed to initialize audio capture:', error);
            throw error;
        }
    }

    /**
     * Start recording and streaming
     */
    startRecording() {
        if (!this.mediaStream) {
            throw new Error('Audio not initialized');
        }

        if (this.isRecording) {
            console.warn('Already recording');
            return;
        }

        // Create MediaRecorder with appropriate format
        const options = {
            mimeType: this.getSupportedMimeType(),
            audioBitsPerSecond: 128000,
        };

        this.mediaRecorder = new MediaRecorder(this.mediaStream, options);

        // Handle data available (audio chunks)
        this.mediaRecorder.ondataavailable = (event) => {
            if (event.data.size > 0 && this.onAudioChunk) {
                this.onAudioChunk(event.data);
            }
        };

        // Handle errors
        this.mediaRecorder.onerror = (event) => {
            console.error('MediaRecorder error:', event.error);
        };

        // Start recording with 250ms chunks
        this.mediaRecorder.start(250);
        this.isRecording = true;

        console.log('Recording started', options);
    }

    /**
     * Stop recording
     */
    stopRecording() {
        if (this.mediaRecorder && this.isRecording) {
            this.mediaRecorder.stop();
            this.isRecording = false;
            console.log('Recording stopped');
        }
    }

    /**
     * Release all resources
     */
    release() {
        this.stopRecording();

        if (this.mediaStream) {
            this.mediaStream.getTracks().forEach(track => track.stop());
            this.mediaStream = null;
        }

        if (this.audioContext) {
            this.audioContext.close();
            this.audioContext = null;
        }

        this.analyser = null;
        console.log('Audio capture released');
    }

    /**
     * Monitor audio levels
     */
    startLevelMonitoring() {
        if (!this.analyser) return;

        const bufferLength = this.analyser.frequencyBinCount;
        const dataArray = new Uint8Array(bufferLength);

        const updateLevel = () => {
            if (!this.analyser) return;

            this.analyser.getByteFrequencyData(dataArray);

            // Calculate average level
            let sum = 0;
            for (let i = 0; i < bufferLength; i++) {
                sum += dataArray[i];
            }
            const average = sum / bufferLength;
            const normalized = average / 255; // Normalize to 0-1

            if (this.onAudioLevel) {
                this.onAudioLevel(normalized);
            }

            requestAnimationFrame(updateLevel);
        };

        updateLevel();
    }

    /**
     * Get supported MIME type for recording
     */
    getSupportedMimeType() {
        const types = [
            'audio/webm;codecs=opus',
            'audio/webm',
            'audio/ogg;codecs=opus',
            'audio/mp4',
        ];

        for (const type of types) {
            if (MediaRecorder.isTypeSupported(type)) {
                console.log('Using MIME type:', type);
                return type;
            }
        }

        console.warn('No preferred MIME type supported, using default');
        return '';
    }

    /**
     * Check if audio capture is supported
     */
    static isSupported() {
        return !!(
            navigator.mediaDevices &&
            navigator.mediaDevices.getUserMedia &&
            window.MediaRecorder
        );
    }
}

// Export for use in other scripts
window.AudioCapture = AudioCapture;
