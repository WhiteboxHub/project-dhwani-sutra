import logging
import os
import time
import math
from typing import Dict, Any, List

# Configure logger
logger = logging.getLogger("latency_tracker")
logger.setLevel(logging.INFO)

# Create stream handler
if not logger.handlers:
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    logger.addHandler(ch)

ENABLE_LATENCY_LOGGING = os.getenv("ENABLE_LATENCY_LOGGING", "true").lower() in ("true", "1", "yes")

class SessionMetrics:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.chunks_processed = 0
        
        self.deepgram_latencies: List[float] = []
        self.gpt_latencies: List[float] = []
        self.network_latencies: List[float] = []
        self.rendering_latencies: List[float] = []
        self.e2e_latencies: List[float] = []

    def add_chunk_metrics(self, dg: float, gpt: float, net: float, rend: float, e2e: float):
        self.chunks_processed += 1
        self.deepgram_latencies.append(dg)
        if gpt > 0:
            self.gpt_latencies.append(gpt)
        self.network_latencies.append(net)
        self.rendering_latencies.append(rend)
        self.e2e_latencies.append(e2e)

def calculate_percentile(data: List[float], pct: float) -> float:
    if not data:
        return 0.0
    sorted_data = sorted(data)
    k = (len(sorted_data) - 1) * pct
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_data[int(k)]
    d0 = sorted_data[int(f)] * (c - k)
    d1 = sorted_data[int(c)] * (k - f)
    return d0 + d1

class LatencyTracker:
    def __init__(self):
        self.sessions: Dict[str, SessionMetrics] = {}
        self.segments: Dict[str, Dict[str, Any]] = {}
        self.epoch_offset = time.time() - time.perf_counter()

    def get_timestamp_ms(self) -> float:
        return (time.perf_counter() + self.epoch_offset) * 1000.0

    def format_ms_time(self, ts_ms: float) -> str:
        if not ts_ms:
            return "N/A"
        seconds = ts_ms / 1000.0
        local_t = time.localtime(seconds)
        milliseconds = int((seconds - int(seconds)) * 1000)
        return f"{time.strftime('%H:%M:%S', local_t)}.{milliseconds:03d}"

    def start_session(self, session_id: str):
        if ENABLE_LATENCY_LOGGING:
            self.sessions[session_id] = SessionMetrics(session_id)
            logger.info(f"⏱️ Started latency tracking session: {session_id}")

    def end_session(self, session_id: str):
        if not ENABLE_LATENCY_LOGGING or session_id not in self.sessions:
            return
        
        metrics = self.sessions[session_id]
        if metrics.chunks_processed == 0:
            logger.info(f"⏱️ Session {session_id} completed with no chunks processed.")
            del self.sessions[session_id]
            return

        avg_dg = sum(metrics.deepgram_latencies) / len(metrics.deepgram_latencies) if metrics.deepgram_latencies else 0.0
        max_dg = max(metrics.deepgram_latencies) if metrics.deepgram_latencies else 0.0
        min_dg = min(metrics.deepgram_latencies) if metrics.deepgram_latencies else 0.0

        avg_gpt = sum(metrics.gpt_latencies) / len(metrics.gpt_latencies) if metrics.gpt_latencies else 0.0
        max_gpt = max(metrics.gpt_latencies) if metrics.gpt_latencies else 0.0

        avg_net = sum(metrics.network_latencies) / len(metrics.network_latencies) if metrics.network_latencies else 0.0
        avg_rend = sum(metrics.rendering_latencies) / len(metrics.rendering_latencies) if metrics.rendering_latencies else 0.0
        avg_e2e = sum(metrics.e2e_latencies) / len(metrics.e2e_latencies) if metrics.e2e_latencies else 0.0
        pct_95 = calculate_percentile(metrics.e2e_latencies, 0.95)

        summary = f"""
====================================
Session Summary

Session ID:
{session_id}

Chunks Processed:
{metrics.chunks_processed}

Average Deepgram Latency:
{avg_dg:.0f} ms

Maximum Deepgram Latency:
{max_dg:.0f} ms

Minimum Deepgram Latency:
{min_dg:.0f} ms

Average GPT Latency:
{avg_gpt:.0f} ms

Maximum GPT Latency:
{max_gpt:.0f} ms

Average Network Latency:
{avg_net:.0f} ms

Average Rendering Latency:
{avg_rend:.0f} ms

Average End-to-End Latency:
{avg_e2e:.0f} ms

95th Percentile Latency:
{pct_95:.0f} ms
====================================
"""
        logger.info(summary)
        del self.sessions[session_id]

    def log_error(self, session_id: str, stage: str, error: str, chunk_number: int = 0):
        ts = self.get_timestamp_ms()
        logger.error(
            f"❌ LATENCY ERROR | {self.format_ms_time(ts)} | "
            f"Session: {session_id} | Stage: {stage} | Chunk: {chunk_number} | Error: {error}"
        )

    def record_segment_start(self, segment_id: str, chunk_info: Dict[str, Any], deepgram_response: float):
        if not ENABLE_LATENCY_LOGGING:
            return
        
        self.segments[segment_id] = {
            "chunk_index": chunk_info.get("chunk_index", 0),
            "audio_created": chunk_info.get("audio_created_time"),
            "audio_sent": chunk_info.get("audio_sent_time"),
            "backend_received": chunk_info.get("backend_received_time"),
            "deepgram_forwarded": chunk_info.get("deepgram_forwarded_time"),
            "deepgram_response": deepgram_response,
            "dict_start": 0.0,
            "dict_end": 0.0,
            "val_start": 0.0,
            "val_end": 0.0,
            "gpt_started": 0.0,
            "gpt_completed": 0.0,
            "broadcast_sent": 0.0,
            "gpt_invoked": False
        }

    def record_pipeline_metrics(self, segment_id: str, dict_start: float, dict_end: float, val_start: float, val_end: float, gpt_started: float, gpt_completed: float, gpt_invoked: bool, broadcast_sent: float):
        if not ENABLE_LATENCY_LOGGING or segment_id not in self.segments:
            return
        
        self.segments[segment_id].update({
            "dict_start": dict_start,
            "dict_end": dict_end,
            "val_start": val_start,
            "val_end": val_end,
            "gpt_started": gpt_started,
            "gpt_completed": gpt_completed,
            "gpt_invoked": gpt_invoked,
            "broadcast_sent": broadcast_sent
        })

    def process_listener_telemetry(self, session_id: str, segment_id: str, listener_received: float, rendered: float):
        if not ENABLE_LATENCY_LOGGING or segment_id not in self.segments:
            return

        seg = self.segments.pop(segment_id)
        
        chunk_idx = seg["chunk_index"]
        t_audio_created = seg["audio_created"]
        t_audio_sent = seg["audio_sent"]
        t_backend_received = seg["backend_received"]
        t_dg_forwarded = seg["deepgram_forwarded"]
        t_dg_response = seg["deepgram_response"]
        
        t_dict_start = seg.get("dict_start", 0.0)
        t_dict_end = seg.get("dict_end", 0.0)
        t_val_start = seg.get("val_start", 0.0)
        t_val_end = seg.get("val_end", 0.0)
        
        t_gpt_started = seg.get("gpt_started", 0.0)
        t_gpt_completed = seg.get("gpt_completed", 0.0)
        t_broadcast_sent = seg.get("broadcast_sent", 0.0)
        gpt_invoked = seg.get("gpt_invoked", False)

        if not t_broadcast_sent:
            t_broadcast_sent = t_dg_response

        # Calculate latencies
        dg_latency = t_dg_response - t_dg_forwarded
        gpt_latency = (t_gpt_completed - t_gpt_started) if gpt_invoked and t_gpt_started else 0.0
        
        net_send = max(0.0, t_backend_received - t_audio_sent) if t_audio_sent else 0.0
        net_recv = max(0.0, listener_received - t_broadcast_sent)
        network_latency = net_send + net_recv
        
        rendering_latency = rendered - listener_received
        
        e2e_latency = rendered - t_audio_created if t_audio_created else (rendered - t_backend_received)

        # Add to session metrics
        if session_id in self.sessions:
            self.sessions[session_id].add_chunk_metrics(
                dg_latency, gpt_latency, network_latency, rendering_latency, e2e_latency
            )

        # Log detailed chunk statistics
        invoked_str = "Yes" if gpt_invoked else "No"
        chunk_log = f"""
==================================================
Session ID: {session_id}
Chunk #{chunk_idx}

Audio Created:     {self.format_ms_time(t_audio_created)}
Audio Sent:        {self.format_ms_time(t_audio_sent)}
Backend Received:  {self.format_ms_time(t_backend_received)}
Deepgram Response: {self.format_ms_time(t_dg_response)}
Dict Normalize:    {int(t_dict_end - t_dict_start) if t_dict_start else 0} ms
Validation Layer:  {int(t_val_end - t_val_start) if t_val_start else 0} ms
GPT Invoked:       {invoked_str}
GPT Started:       {self.format_ms_time(t_gpt_started) if gpt_invoked else 'N/A'}
GPT Completed:     {self.format_ms_time(t_gpt_completed) if gpt_invoked else 'N/A'}
Broadcast Sent:    {self.format_ms_time(t_broadcast_sent)}
Listener Received: {self.format_ms_time(listener_received)}
Rendered:          {self.format_ms_time(rendered)}
----------------------------------
Deepgram:  {dg_latency:.0f} ms
GPT:       {gpt_latency:.0f} ms
Network:   {network_latency:.0f} ms
Rendering: {rendering_latency:.0f} ms
Total:     {e2e_latency:.0f} ms
==================================================
"""
        logger.info(chunk_log)

# Global tracker instance
latency_tracker = LatencyTracker()
