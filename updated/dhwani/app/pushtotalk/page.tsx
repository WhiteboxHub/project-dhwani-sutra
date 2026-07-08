"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import toast, { Toaster } from "react-hot-toast";

type TranscriptItem = {
  id: string | number;
  text: string;
  isCleaned: boolean;
  isFinal: boolean;
};

export default function PushToTalk() {
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const socketRef = useRef<WebSocket | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const recordingIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const chunkIndexRef = useRef(0);
  const heartbeatIntervalRef = useRef<NodeJS.Timeout | null>(null);

  const [isRecording, setIsRecording] = useState(false);
  const [transcripts, setTranscripts] = useState<TranscriptItem[]>([]);
  const [latestText, setLatestText] = useState("");
  const [status, setStatus] = useState("Ready");
  const [provider, setProvider] = useState<"openai" | "deepgram">("deepgram");
  const [sessionId, setSessionId] = useState("");

  const [openAiKey, setOpenAiKey] = useState("");
  const [deepgramKey, setDeepgramKey] = useState("");
  const [isKeysInserted, setIsKeysInserted] = useState(false);
  const [savedOpenAiKey, setSavedOpenAiKey] = useState("");
  const [savedDeepgramKey, setSavedDeepgramKey] = useState("");
  const CHUNK_DURATION = 2000; // 2s — good balance for Deepgram streaming

  useEffect(() => {
    setSessionId(Math.random().toString(36).substring(2, 8).toUpperCase());

    const savedOpenAI = localStorage.getItem("openai_key") || "";
    const savedDeepgram = localStorage.getItem("deepgram_key") || "";

    setSavedOpenAiKey(savedOpenAI);
    setSavedDeepgramKey(savedDeepgram);

    if (savedOpenAI && savedDeepgram) {
      setIsKeysInserted(true);
      toast.success("Keys Loaded");
    }

    return () => {
      cleanupAll();
    };
  }, []);

  const Insert_key = () => {
    if (!openAiKey && !deepgramKey) {
      toast.error("Please enter at least one key");
      return;
    }
    setSavedOpenAiKey(openAiKey);
    setSavedDeepgramKey(deepgramKey);
    localStorage.setItem("openai_key", openAiKey);
    localStorage.setItem("deepgram_key", deepgramKey);
    setIsKeysInserted(true);
    setOpenAiKey("");
    setDeepgramKey("");
    toast.success("Keys Inserted");
  };

  const cleanupAll = () => {
    if (recordingIntervalRef.current) {
      clearInterval(recordingIntervalRef.current);
      recordingIntervalRef.current = null;
    }

    if (heartbeatIntervalRef.current) {
      clearInterval(heartbeatIntervalRef.current);
      heartbeatIntervalRef.current = null;
    }

    if (
      mediaRecorderRef.current &&
      mediaRecorderRef.current.state === "recording"
    ) {
      mediaRecorderRef.current.stop();
    }

    mediaRecorderRef.current = null;

    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }

    if (socketRef.current) {
      if (
        socketRef.current.readyState === WebSocket.OPEN ||
        socketRef.current.readyState === WebSocket.CONNECTING
      ) {
        socketRef.current.close();
      }

      socketRef.current = null;
    }
  };

  const clearKeys = () => {
    localStorage.removeItem("openai_key");
    localStorage.removeItem("deepgram_key");

    setOpenAiKey("");
    setDeepgramKey("");
    setSavedDeepgramKey("");
    setSavedOpenAiKey("");
    setIsKeysInserted(false);
    alert("Stored keys cleared.");
    toast.success("Keys Cleared");
  };

  const startRecordingChunk = useCallback(() => {
    if (!streamRef.current || !socketRef.current) return;

    if (socketRef.current.readyState !== WebSocket.OPEN) return;

    const tracks = streamRef.current.getTracks();
    if (tracks.length === 0 || tracks.some((t) => t.readyState === "ended")) return;

    const recorder = new MediaRecorder(streamRef.current, {
      mimeType: "audio/webm;codecs=opus",
    });

    const chunks: BlobPart[] = [];

    recorder.ondataavailable = (event) => {
      if (event.data.size > 0) chunks.push(event.data);
    };

    recorder.onstop = async () => {
      if (
        chunks.length > 0 &&
        socketRef.current?.readyState === WebSocket.OPEN
      ) {
        chunkIndexRef.current += 1;
        const audioCreated = performance.timeOrigin + performance.now();
        const blob = new Blob(chunks, {
          type: "audio/webm;codecs=opus",
        });

        const buffer = await blob.arrayBuffer();
        const audioSent = performance.timeOrigin + performance.now();

        socketRef.current.send(JSON.stringify({
          type: "chunk_metadata",
          chunk_index: chunkIndexRef.current,
          audio_created_time: audioCreated,
          audio_sent_time: audioSent
        }));
        
        socketRef.current.send(buffer);
      }
    };

    recorder.start();
    mediaRecorderRef.current = recorder;

    setTimeout(() => {
      if (recorder.state === "recording") recorder.stop();
    }, CHUNK_DURATION);
  }, []);

  const startRecording = async () => {
    if (isRecording) return;

    if (!savedDeepgramKey.trim() || !savedOpenAiKey.trim()) {
      alert("Please enter both OpenAI key and Deepgram key");
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          sampleRate: 16000,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });

      streamRef.current = stream;

      const backendBase = process.env.NEXT_PUBLIC_BACKEND_URL || "127.0.0.1:8000";
      const protocol = backendBase.includes("://") ? (backendBase.startsWith("https") ? "wss" : "ws") : "ws";
      const rawHost = backendBase.replace(/^https?:\/\//, "").replace(/^wss?:\/\//, "");

      const socket = new WebSocket(
        `${protocol}://${rawHost}/ws/stt/${sessionId}?provider=${provider}&openai_key=${encodeURIComponent(
          savedOpenAiKey.trim()
        )}&deepgram_key=${encodeURIComponent(savedDeepgramKey.trim())}`
      );

      socketRef.current = socket;

      socket.onopen = () => {
        setStatus("Connected - Recording...");

        heartbeatIntervalRef.current = setInterval(() => {
          if (socket.readyState === WebSocket.OPEN) {
            socket.send(JSON.stringify({ type: "ping" }));
          }
        }, 30000);

        if (provider === "openai") {
          chunkIndexRef.current = 0;
          startRecordingChunk();

          recordingIntervalRef.current = setInterval(() => {
            startRecordingChunk();
          }, CHUNK_DURATION);
        } else {
          chunkIndexRef.current = 0;
          let localChunkIndex = 0;
          const recorder = new MediaRecorder(stream, {
            mimeType: "audio/webm;codecs=opus",
          });

          recorder.ondataavailable = async (event) => {
            if (
              event.data.size > 0 &&
              socket.readyState === WebSocket.OPEN
            ) {
              const audioCreated = performance.timeOrigin + performance.now();
              localChunkIndex++;
              chunkIndexRef.current = localChunkIndex;
              const buffer = await event.data.arrayBuffer();
              const audioSent = performance.timeOrigin + performance.now();

              socket.send(JSON.stringify({
                type: "chunk_metadata",
                chunk_index: localChunkIndex,
                audio_created_time: audioCreated,
                audio_sent_time: audioSent
              }));
              
              socket.send(buffer);
            }
          };

          recorder.start(250);
          mediaRecorderRef.current = recorder;
        }
      };

      socket.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);

          if (data.type === "transcript_raw") {
            setTranscripts((prev) => {
              const existingIdx = prev.findIndex((item) => item.id === data.id);
              if (existingIdx !== -1) {
                const updated = [...prev];
                updated[existingIdx] = {
                  ...updated[existingIdx],
                  text: data.text,
                  isFinal: data.is_final
                };
                return updated;
              } else {
                return [
                  ...prev,
                  {
                    id: data.id,
                    text: data.text,
                    isCleaned: false,
                    isFinal: data.is_final
                  }
                ];
              }
            });

            setLatestText(data.text);
            setStatus(data.is_final ? "Transcript Finalized" : "Streaming...");
          }

          if (data.type === "transcript_cleaned") {
            setTranscripts((prev) =>
              prev.map((item) =>
                item.id === data.id
                  ? {
                      ...item,
                      text: data.text,
                      isCleaned: true
                    }
                  : item
              )
            );

            if (data.text) setLatestText(data.text);
            setStatus("Transcript Cleaned");
          }

          if (data.type === "error") {
            setStatus(`⚠️ Error: ${data.message || 'Server Error'}`);
            toast.error(data.message || "An error occurred on the server");
          }
        } catch {
          // Ignore parsing errors for control frames
        }
      };

      socket.onerror = () => {
        setStatus("Connection Error");
      };

      socket.onclose = () => {
        setStatus("Disconnected");
        stopRecording();
      };

      setTranscripts([]);
      setLatestText("");
      setIsRecording(true);
    } catch (error) {
      console.error(error);
      setStatus("Microphone Error");
      alert("Unable to access microphone.");
    }
  };

  const stopRecording = () => {
    cleanupAll();
    setIsRecording(false);
    setStatus("Stopped");
  };

  const handleToggle = () => {
    if (isRecording) stopRecording();
    else startRecording();
  };

  const clearTranscript = () => {
    setTranscripts([]);
    setLatestText("");
  };

  const copyTranscript = async () => {
    const fullText = transcripts.map((item) => item.text).join(" ");
    await navigator.clipboard.writeText(fullText);
    alert("Transcript copied.");
  };

  return (
    <main className="min-h-screen bg-gray-900 text-white flex justify-center items-center p-6">
      <div className="w-full max-w-2xl space-y-5">
        <div className="bg-gray-800 p-5 rounded-xl space-y-3 border border-gray-700">
          {isKeysInserted ? <div></div> : <div>
            <h2 className="text-lg font-semibold">API Keys</h2>

            <input
              type="password"
              placeholder="OpenAI Key"
              value={openAiKey}
              onChange={(e) => setOpenAiKey(e.target.value)}
              className="w-full bg-gray-900 border border-gray-600 rounded px-3 py-2 mb-2"
            />

            <input
              type="password"
              placeholder="Deepgram Key"
              value={deepgramKey}
              onChange={(e) => setDeepgramKey(e.target.value)}
              className="w-full bg-gray-900 border border-gray-600 rounded px-3 py-2"
            />
          </div>}
          <button
            onClick={Insert_key}
            className="bg-blue-600 hover:bg-green-500 disabled:opacity-50 px-4 py-2 rounded mr-2"
            disabled={isRecording || openAiKey == "" && deepgramKey == ""}
          >
            Insert Keys
          </button>
          <button
            onClick={clearKeys}
            className="bg-red-600 hover:bg-red-500 disabled:opacity-50 px-4 py-2 rounded"
            disabled={isRecording || savedDeepgramKey == "" || savedOpenAiKey == ""}
          >
            Clear Keys
          </button>
        </div>

        <div className="bg-gray-800 p-5 rounded-xl border border-gray-700 space-y-4">
          <div>
            <label className="block mb-2 text-sm">Provider</label>

            <select
              value={provider}
              onChange={(e) =>
                setProvider(e.target.value as "openai" | "deepgram")
              }
              disabled={isRecording}
              className="w-full bg-gray-900 border border-gray-600 rounded px-3 py-2"
            >
              <option value="openai">OpenAI</option>
              <option value="deepgram">Deepgram</option>
            </select>
          </div>

          <div className="text-sm text-gray-300">
            Session ID:{" "}
            <span className="font-mono text-white">{sessionId}</span>
          </div>

          <div className="text-sm text-green-400">{status}</div>

          <button
            onClick={handleToggle}
            className={`w-full py-3 rounded font-semibold ${isRecording
              ? "bg-red-600 hover:bg-red-500"
              : "bg-green-600 hover:bg-green-500"
              }`}
          >
            {isRecording ? "Stop Recording" : "Start Recording"}
          </button>
        </div>

        {latestText && (
          <div className="bg-gray-800 p-5 rounded-xl border border-gray-700">
            <h3 className="font-semibold mb-2">Latest Transcript</h3>
            <p>{latestText}</p>
          </div>
        )}

        {transcripts.length > 0 && (
          <div className="bg-gray-800 p-5 rounded-xl border border-gray-700 space-y-4">
            <div className="flex gap-2">
              <button
                onClick={copyTranscript}
                className="bg-blue-600 hover:bg-blue-500 px-4 py-2 rounded"
              >
                Copy
              </button>

              <button
                onClick={clearTranscript}
                className="bg-red-600 hover:bg-red-500 px-4 py-2 rounded"
              >
                Clear
              </button>
            </div>

            <div className="space-y-3 max-h-80 overflow-y-auto">
              {transcripts.map((item, index) => (
                <div
                  key={`${item.id}-${index}`}
                  className="bg-gray-900 rounded p-3 border border-gray-700"
                >
                  <div className="text-xs text-gray-400 mb-1">
                    Segment {index + 1}
                  </div>

                  <div
                    className={
                      item.isCleaned
                        ? "text-white font-normal"
                        : item.isFinal
                        ? "text-gray-300 font-medium"
                        : "text-gray-500 italic animate-pulse"
                    }
                  >
                    {item.text}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
      <Toaster position="bottom-right" />
    </main>
  );
}