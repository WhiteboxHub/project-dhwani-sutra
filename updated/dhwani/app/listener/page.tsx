"use client";

import { useState, useRef, useEffect } from "react";

export default function Listener() {
  const [sessionId, setSessionId] = useState("");
  const [isConnected, setIsConnected] = useState(false);
  const [status, setStatus] = useState("Disconnected");
  const [transcripts, setTranscripts] = useState<any[]>([]);
  
  const socketRef = useRef<WebSocket | null>(null);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (socketRef.current) {
        socketRef.current.close();
      }
    };
  }, []);

  const handleConnect = () => {
    if (!sessionId.trim()) {
      alert("Please enter a Session ID");
      return;
    }

    if (isConnected) {
      if (socketRef.current) {
        socketRef.current.close();
      }
      setIsConnected(false);
      setStatus("Disconnected");
      return;
    }

    setStatus("Connecting...");
    
    // Connect to the listener WebSocket endpoint
    // Adjust the URL if your backend endpoint differs
    const wsUrl = `ws://127.0.0.1:8000/ws/listen/${sessionId.trim()}`;
    const socket = new WebSocket(wsUrl);
    socketRef.current = socket;

    socket.onopen = () => {
      console.log(`📡 Connected to session: ${sessionId}`);
      setStatus("Connected - Listening...");
      setIsConnected(true);
      setTranscripts([]);
    };

    socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);

        if (data.type === "transcript_raw") {
          setTranscripts((prev) => [...prev, { id: data.id, text: data.text, isCleaned: false }]);
          setStatus("✅ Transcribed (Raw)");
          
          setTimeout(() => {
            setStatus((currentStatus) => 
              currentStatus.startsWith("✅ Transcribed") ? "Connected - Listening..." : currentStatus
            );
          }, 1000);

        } else if (data.type === "transcript_cleaned") {
           setTranscripts((prev) => 
             prev.map(t => t.id === data.id ? { ...t, text: data.text, isCleaned: true } : t)
           );
           setStatus("✨ Transcribed (Cleaned)");

           setTimeout(() => {
            setStatus((currentStatus) => 
              currentStatus.startsWith("✨ Transcribed") ? "Connected - Listening..." : currentStatus
            );
          }, 1000);

        } else if (data.type === "error") {
          console.error("❌ Backend error:", data.message);
          setStatus(`⚠️ Error: ${data.message || 'Check console'}`);
        }
      } catch (err) {
        console.error("❌ Invalid WebSocket message:", err);
      }
    };

    socket.onerror = (error) => {
      console.error("WebSocket error:", error);
      setStatus("Connection Error");
      setIsConnected(false);
    };

    socket.onclose = (event) => {
      console.log("🔌 WebSocket closed:", event.code, event.reason);
      setStatus("Disconnected");
      setIsConnected(false);
    };
  };

  const clearTranscript = () => {
    setTranscripts([]);
  };

  const copyToClipboard = () => {
    const fullText = transcripts.map(t => t.text).join(" ");
    navigator.clipboard.writeText(fullText);
    alert("Transcript copied to clipboard!");
  };

  const downloadTranscript = () => {
    const fullText = transcripts.map(t => t.text).join(" ");
    const blob = new Blob([fullText], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `session-${sessionId}-${new Date().toISOString().slice(0, 10)}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <main className="flex min-h-screen items-center justify-center bg-gray-900 text-white p-4">
      <div className="flex flex-col items-center gap-6 max-w-2xl w-full pt-16">
        
        <div className="text-center">
          <h1 className="text-3xl font-bold mb-2">🎧 Listen to Stream</h1>
          <p className="text-sm text-gray-400">Join a session to view real-time transcripts</p>
        </div>

        {/* Connection Setup */}
        <div className="flex flex-col sm:flex-row items-center gap-3 w-full justify-center bg-gray-800 p-4 rounded-xl border border-gray-700 shadow-lg">
          <div className="flex w-full max-w-sm flex-col">
            <label htmlFor="sessionId" className="text-xs text-gray-400 mb-1 ml-1 font-semibold uppercase tracking-wider">
              Session ID
            </label>
            <input
              id="sessionId"
              type="text"
              placeholder="Enter unique session ID"
              value={sessionId}
              onChange={(e) => setSessionId(e.target.value)}
              disabled={isConnected}
              className="bg-gray-900 text-white text-sm rounded-lg border border-gray-600 px-4 py-3 outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 disabled:opacity-50 transition-all font-mono"
            />
          </div>
          <button
            onClick={handleConnect}
            className={`mt-5 sm:mt-0 px-6 py-3 rounded-lg font-bold transition-all duration-300 shadow-lg flex-shrink-0 w-full sm:w-auto h-[46px] flex items-center justify-center mt-auto
              ${
                isConnected
                  ? "bg-red-500 hover:bg-red-600 shadow-red-500/30 text-white"
                  : "bg-blue-600 hover:bg-blue-500 shadow-blue-500/30 text-white"
              }`}
          >
            {isConnected ? "Disconnect" : "Join Session"}
          </button>
        </div>

        {/* Status Indicator */}
        <div className="flex items-center gap-3 bg-gray-800 px-5 py-3 rounded-full border border-gray-700 w-auto justify-center shadow-inner">
          <div className={`w-3 h-3 rounded-full ${
            isConnected ? 'bg-green-500 animate-pulse shadow-[0_0_8px_rgba(34,197,94,0.6)]' : 'bg-gray-600'
          }`}></div>
          <span className="text-sm text-gray-300 font-mono font-medium tracking-wide">
            {status}
          </span>
        </div>

        {/* Transcript Interface */}
        {transcripts.length > 0 && (
          <div className="bg-gray-800 p-6 rounded-xl w-full border border-gray-700 shadow-2xl animate-in fade-in slide-in-from-bottom-4 duration-500">
            <div className="flex flex-col sm:flex-row sm:justify-between sm:items-center gap-4 mb-4">
              <p className="text-sm text-gray-300 font-semibold uppercase tracking-wider">
                Live Transcript <span className="text-blue-400 bg-blue-900/30 px-2 py-0.5 rounded-full text-xs ml-2">{transcripts.length} segments</span>
              </p>

              <div className="flex gap-2 flex-wrap">
                <button
                  onClick={downloadTranscript}
                  className="text-sm text-blue-400 hover:text-blue-300 transition px-3 py-1.5 bg-blue-900/30 rounded-md border border-blue-700/30 flex items-center gap-1.5"
                  title="Download as text file"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>
                  Save
                </button>

                <button
                  onClick={copyToClipboard}
                  className="text-sm text-green-400 hover:text-green-300 transition px-3 py-1.5 bg-green-900/30 rounded-md border border-green-700/30 flex items-center gap-1.5"
                  title="Copy to clipboard"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
                  Copy
                </button>

                <button
                  onClick={clearTranscript}
                  className="text-sm text-red-400 hover:text-red-300 transition px-3 py-1.5 bg-red-900/30 rounded-md border border-red-700/30 flex items-center gap-1.5"
                  title="Clear transcript"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path><line x1="10" y1="11" x2="10" y2="17"></line><line x1="14" y1="11" x2="14" y2="17"></line></svg>
                  Clear
                </button>
              </div>
            </div>

            {/* Continuous text view */}
            <div className="bg-gray-900/80 p-5 rounded-lg max-h-[350px] overflow-y-auto border border-gray-700 shadow-inner scrollbar-thin scrollbar-thumb-gray-600 scrollbar-track-transparent">
              <p className="text-lg text-gray-100 leading-relaxed">
                {transcripts.map((t, idx) => (
                  <span key={t.id || idx} className={t.isCleaned ? "transition-colors duration-300" : "text-gray-400 italic font-light animate-pulse"}>
                    {t.text}{" "}
                  </span>
                ))}
              </p>
            </div>

            {/* Segmented view */}
            <details className="mt-4 group">
              <summary className="text-sm text-gray-400 cursor-pointer hover:text-gray-300 select-none flex items-center gap-2">
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="group-open:rotate-90 transition-transform"><polyline points="9 18 15 12 9 6"></polyline></svg>
                View segments individually
              </summary>

              <div className="mt-3 space-y-3 max-h-[250px] overflow-y-auto pr-2 scrollbar-thin scrollbar-thumb-gray-600 scrollbar-track-transparent">
                {transcripts.map((t, idx) => (
                  <div
                    key={t.id || idx}
                    className={`text-base p-4 rounded-lg border-l-4 leading-relaxed break-words whitespace-pre-wrap transition-all shadow-sm ${
                      t.isCleaned 
                        ? 'text-gray-200 bg-gray-700/40 border-blue-500/50 hover:bg-gray-700/60' 
                        : 'text-gray-400 bg-gray-800/60 border-gray-500/50 italic'
                    }`}
                  >
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-gray-500 font-mono text-xs bg-gray-800 px-1.5 py-0.5 rounded">
                        #{idx + 1}
                      </span>
                      {!t.isCleaned && (
                        <span className="inline-flex items-center gap-1 text-xs text-yellow-500 bg-yellow-500/10 px-1.5 py-0.5 rounded-full">
                          <svg className="animate-spin h-3 w-3" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>
                          Enhancing
                        </span>
                      )}
                    </div>
                    {t.text}
                  </div>
                ))}
              </div>
            </details>
          </div>
        )}

      </div>
    </main>
  );
}
