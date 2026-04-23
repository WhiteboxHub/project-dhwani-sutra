"use client";

import { useRef, useState, useCallback, useEffect } from "react";

export default function PushToTalk() {
  const mediaRecorderRef = useRef(null);
  const socketRef = useRef(null);
  const streamRef = useRef(null);
  const recordingIntervalRef = useRef(null);

  const [isRecording, setIsRecording] = useState(false);
  const [transcripts, setTranscripts] = useState([]);
  const [latestText, setLatestText] = useState("");
  const [status, setStatus] = useState("Ready");
  const [provider, setProvider] = useState("openai");
  const [sessionId, setSessionId] = useState("");

  const CHUNK_DURATION = 1000; // 3 seconds per chunk

  //  Initialization & Cleanup
  useEffect(() => {
    // Generate a random 6-character alphanumeric session ID
    setSessionId(Math.random().toString(36).substring(2, 8).toUpperCase());

    return () => {
      // Cleanup when component unmounts
      if (recordingIntervalRef.current) {
        clearInterval(recordingIntervalRef.current);
      }
      if (mediaRecorderRef.current?.state === "recording") {
        mediaRecorderRef.current.stop();
      }
      if (streamRef.current) {
        streamRef.current.getTracks().forEach(track => track.stop());
      }
      if (socketRef.current) {
        socketRef.current.close();
      }
    };
  }, []);

  //  Remove isRecording from dependency array (not needed)
  const startRecordingChunk = useCallback(() => {
    if (!streamRef.current || !socketRef.current) {
      console.warn("  Stream or socket not ready");
      return;
    }

    //  FIX 3: Check socket state before creating recorder
    if (socketRef.current.readyState !== WebSocket.OPEN) {
      console.warn("  WebSocket not open, skipping chunk");
      return;
    }

    const mediaRecorder = new MediaRecorder(streamRef.current, {
      mimeType: "audio/webm;codecs=opus",
    });

    const chunks = [];

    mediaRecorder.ondataavailable = (event) => {
      if (event.data.size > 0) {
        chunks.push(event.data);
      }
    };

    mediaRecorder.onstop = async () => {
      if (chunks.length > 0 && socketRef.current?.readyState === WebSocket.OPEN) {
        const blob = new Blob(chunks, { type: "audio/webm;codecs=opus" });
        const arrayBuffer = await blob.arrayBuffer();
        
        console.log(`📦 Sending complete WebM file: ${arrayBuffer.byteLength} bytes`);
        socketRef.current.send(arrayBuffer);
      }
    };

    mediaRecorder.onerror = (event) => {
      console.error(" MediaRecorder error:", event.error);
      setStatus("Recording Error");
    };

    mediaRecorder.start();
    mediaRecorderRef.current = mediaRecorder;

    setTimeout(() => {
      if (mediaRecorder.state === "recording") {
        mediaRecorder.stop();
      }
    }, CHUNK_DURATION);

  }, [CHUNK_DURATION]); // Only CHUNK_DURATION needed

  const startRecording = async () => {
    if (isRecording) return;

    try {
      // Get microphone access
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          sampleRate: 16000,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        }
      });

      streamRef.current = stream;

      // Connect WebSocket
      const socket = new WebSocket(`ws://127.0.0.1:8000/ws/stt/${sessionId}?provider=${provider}`);
      socketRef.current = socket;

      socket.onopen = () => {
        console.log(` WebSocket connected (${provider})`);
        setStatus("Connected - Recording...");
        
        if (provider === "openai") {
          // Start the first chunk immediately
          startRecordingChunk();
          
          // Then start new chunks every CHUNK_DURATION
          recordingIntervalRef.current = setInterval(() => {
            startRecordingChunk();
          }, CHUNK_DURATION);
        } else if (provider === "deepgram") {
          const mediaRecorder = new MediaRecorder(stream, {
            mimeType: "audio/webm;codecs=opus",
          });
          mediaRecorder.ondataavailable = async (event) => {
            if (event.data.size > 0 && socket.readyState === WebSocket.OPEN) {
              const arrayBuffer = await event.data.arrayBuffer();
              socket.send(arrayBuffer);
            }
          };
          // Start the recorder with a "timeslice" of 250ms
          mediaRecorder.start(250);
          mediaRecorderRef.current = mediaRecorder;
        }
      };

      socket.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);

          if (data.type === "transcript_raw") {
            console.log("📝 Raw transcript:", data.text);
            
            setTranscripts((prev) => [...prev, { id: data.id, text: data.text, isCleaned: false }]);
            setLatestText(data.text);
            setStatus("✅ Transcribed (Raw)");
            
            setTimeout(() => {
              setStatus((currentStatus) => 
                currentStatus.startsWith("✅ Transcribed") ? "Recording..." : currentStatus
              );
            }, 1000);

          } else if (data.type === "transcript_cleaned") {
             console.log("✨ Cleaned transcript:", data.text);
             setTranscripts((prev) => prev.map(t => t.id === data.id ? { ...t, text: data.text, isCleaned: true } : t));
             setLatestText(data.text);
             setStatus("✅ Transcribed (Cleaned)");

             setTimeout(() => {
              setStatus((currentStatus) => 
                currentStatus.startsWith("✅ Transcribed") ? "Recording..." : currentStatus
              );
            }, 1000);

          } else if (data.type === "error") {
            console.error("❌ Backend error:", data.message);
            setStatus("⚠️  Error - check console");
          }
        } catch (err) {
          console.error("❌ Invalid WebSocket message:", err);
        }
      };

      socket.onerror = (error) => {
        console.error(" WebSocket error:", error);
        setStatus("Connection Error");
      };

      socket.onclose = (event) => {
        console.log("🔌 WebSocket closed:", event.code, event.reason);
        setStatus("Disconnected");
        
        //  FIX 5: Auto-cleanup on unexpected disconnect
        if (isRecording) {
          console.log("  Unexpected disconnect - cleaning up");
          stopRecording();
        }
      };

      // socketRef.current = socket; (Already set when created)
      setTranscripts([]);
      setLatestText("");
      setIsRecording(true);

    } catch (err) {
      console.error("🎤 Microphone error:", err);
      
      //  FIX 6: Better error messages
      if (err.name === "NotAllowedError") {
        alert(" Microphone access denied. Please allow microphone permissions.");
      } else if (err.name === "NotFoundError") {
        alert(" No microphone found. Please connect a microphone.");
      } else {
        alert(` Could not access microphone: ${err.message}`);
      }
      
      setStatus("Microphone Error");
    }
  };

  const stopRecording = () => {
    console.log(" Stopping recording...");

    // Stop the interval
    if (recordingIntervalRef.current) {
      clearInterval(recordingIntervalRef.current);
      recordingIntervalRef.current = null;
    }

    // Stop current recorder
    if (mediaRecorderRef.current) {
      if (mediaRecorderRef.current.state === "recording") {
        mediaRecorderRef.current.stop();
      }
      mediaRecorderRef.current = null;
    }

    // Stop media stream
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(track => {
        track.stop();
        console.log("🎤 Microphone track stopped");
      });
      streamRef.current = null;
    }

    // Close WebSocket
    if (socketRef.current) {
      if (socketRef.current.readyState === WebSocket.OPEN) {
        socketRef.current.close();
        console.log("🔌 WebSocket closed");
      }
      socketRef.current = null;
    }

    setIsRecording(false);
    setStatus("Stopped");
  };

  const handleToggle = () => {
    if (isRecording) {
      stopRecording();
    } else {
      startRecording();
    }
  };

  const clearTranscript = () => {
    setTranscripts([]);
    setLatestText("");
  };

  const copyToClipboard = () => {
    const fullText = transcripts.map(t => t.text).join(" ");
    navigator.clipboard.writeText(fullText);
    alert(" Transcript copied to clipboard!");
  };

  const downloadTranscript = () => {
    const fullText = transcripts.map(t => t.text).join(" ");
    const blob = new Blob([fullText], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `transcript-${new Date().toISOString().slice(0, 10)}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <main className="flex min-h-screen items-center justify-center bg-gray-900 text-white p-4">
      <div className="flex flex-col items-center gap-6 max-w-2xl w-full">

        {/* <div className="text-center">
          <h1 className="text-3xl font-bold mb-2">🎙️  Speech to Text Streaming</h1>
          <p className="text-sm text-gray-400">with AI-powered transcript cleaning</p>
        </div> */}

        {/* Provider Selection */}
        <div className="flex items-center gap-3 bg-gray-800 px-4 py-2 rounded-lg border border-gray-700 w-full max-w-sm justify-center">
          <label htmlFor="provider" className="text-sm text-gray-400 font-semibold">Provider:</label>
          <select 
            id="provider" 
            value={provider} 
            onChange={(e) => setProvider(e.target.value)}
            disabled={isRecording}
            className="bg-gray-900 text-white text-sm rounded border border-gray-600 px-2 py-1 outline-none focus:border-blue-500 disabled:opacity-50"
          >
            <option value="openai">OpenAI (Chunked)</option>
            <option value="deepgram">Deepgram (Live Stream)</option>
          </select>
        </div>

        {/* Session ID Display */}
        <div className="flex items-center gap-3 bg-gray-800 px-4 py-2 rounded-lg border border-indigo-700 w-full max-w-sm justify-between">
          <div className="flex flex-col">
            <span className="text-xs text-indigo-400 font-bold uppercase tracking-wide">Session ID</span>
            <span className="text-lg text-white font-mono tracking-widest">{sessionId || "------"}</span>
          </div>
          <button 
            onClick={() => {
              navigator.clipboard.writeText(sessionId);
              alert("Session ID copied!");
            }}
            className="text-xs bg-indigo-600 hover:bg-indigo-500 text-white px-3 py-1.5 rounded transition shadow"
          >
            Copy Code
          </button>
        </div>

        {/* Status */}
        <div className="flex items-center gap-3 bg-gray-800 px-4 py-2 rounded-lg border border-gray-700 min-w-[250px] justify-center">
          <div className={`w-3 h-3 rounded-full ${
            isRecording ? 'bg-red-500 animate-pulse' : 'bg-gray-600'
          }`}></div>
          <span className="text-sm text-gray-300 font-mono">
            {status}
          </span>
        </div>

        {/* Record Button */}
        <button
          onClick={handleToggle}
          className={`w-10 h-10 rounded-full flex flex-col items-center justify-center text-lg font-bold transition-all duration-200 shadow-2xl
            ${
              isRecording
                ? "bg-red-500 scale-110 shadow-red-500/50 hover:bg-red-600"
                : "bg-green-500 hover:bg-green-600 shadow-green-500/30"
            }`}
        >
          <span className="text-4xl mb-2">{isRecording ? "" : "🎤"}</span>
          <span className="text-sm">{isRecording ? "Stop" : "Start"}</span>
        </button>

        {/* Info */}
        <div className="text-center text-xs text-gray-400 bg-gray-800/50 px-4 py-2 rounded-lg">
          <p>
            {provider === "openai" ? `Records in ${CHUNK_DURATION / 1000}s segments` : "Real-time continuous streaming"}
            {" "}• AI-cleaned transcripts
          </p>
        </div>

        {/* Latest Segment */}
        {/* <div className="bg-gradient-to-br from-blue-900/50 to-purple-900/50 p-5 rounded-xl w-full border border-blue-500/30">
          <div className="flex justify-between items-center mb-2">
            <p className="text-xs text-blue-300 font-semibold uppercase tracking-wide">
              Latest Segment (AI-cleaned)
            </p>
            {isRecording && (
              <span className="text-xs text-blue-400 flex items-center gap-1">
                <span className="animate-pulse">●</span> REC
              </span>
            )}
          </div>
          <p className="text-lg text-white whitespace-pre-wrap min-h-[60px]">
            {latestText || "...waiting for speech"}
          </p>
        </div> */}

        {/* Full Transcript */}
       {transcripts.length > 0 && (
  <div className="bg-gray-800 p-5 rounded-xl w-full border border-gray-700">
    <div className="flex justify-between items-center mb-3">
      <p className="text-sm text-gray-300 font-semibold uppercase tracking-wide">
        Full Transcript ({transcripts.length} segments)
      </p>

      <div className="flex gap-2">
        <button
          onClick={downloadTranscript}
          className="text-sm text-blue-400 hover:text-blue-300 transition px-3 py-1 bg-blue-900/30 rounded-md border border-blue-700/30"
          title="Download as text file"
        >
          💾 Save
        </button>

        <button
          onClick={copyToClipboard}
          className="text-sm text-green-400 hover:text-green-300 transition px-3 py-1 bg-green-900/30 rounded-md border border-green-700/30"
          title="Copy to clipboard"
        >
          📋 Copy
        </button>

        <button
          onClick={clearTranscript}
          className="text-sm text-red-400 hover:text-red-300 transition px-3 py-1 bg-red-900/30 rounded-md border border-red-700/30"
          title="Clear transcript"
        >
          🗑️ Clear
        </button>
      </div>
    </div>

    {/* Continuous text view */}
    <div className="bg-gray-900/50 p-4 rounded-lg max-h-[300px] overflow-y-auto">
      <p className="text-lg text-gray-100 leading-relaxed">
        {transcripts.map((t, idx) => (
          <span key={t.id || idx} className={t.isCleaned ? "" : "text-gray-400 italic font-light animate-pulse"}>
            {t.text}{" "}
          </span>
        ))}
      </p>
    </div>

    {/* Segmented view */}
    <details className="mt-3">
      <summary className="text-sm text-gray-400 cursor-pointer hover:text-gray-300 select-none">
        📋 View segments individually
      </summary>

     <div className="mt-2 space-y-3 max-h-[200px] overflow-y-auto pr-1">
  {transcripts.map((t, idx) => (
    <div
      key={t.id || idx}
      className={`text-base p-3 rounded border-l-2 leading-relaxed break-words whitespace-pre-wrap ${
        t.isCleaned ? 'text-gray-200 bg-gray-700/50 border-blue-500/30' : 'text-gray-400 bg-gray-800/50 border-gray-600/50 italic'
      }`}
    >
      <span className="text-gray-400 mr-2 font-mono text-sm inline-flex items-center gap-1">
        [{idx + 1}] {!t.isCleaned && <span className="animate-spin text-xs">⏳</span>}
      </span>
      {t.text}
    </div>
  ))}
</div>
    </details>
  </div>
)}

        {/* <div className="text-xs text-gray-500 text-center max-w-md space-y-1 bg-gray-800/30 p-4 rounded-lg">
          <p className="font-semibold text-gray-400">💡 How it works:</p>
          <p>
            {provider === "openai" 
              ? `• Automatically records ${CHUNK_DURATION / 1000}s segments (each is a complete audio file)` 
              : "• Continuously streams microphone data in 250ms timeslices for real-time transcription"}
          </p>
          <p>• AI cleans transcripts for technical accuracy</p>
          <p>• Corrects domain-specific terms (LangChain, RAG, etc.)</p>
        </div> */}
      </div>
    </main>
  );
}