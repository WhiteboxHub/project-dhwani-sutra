import io
import asyncio
from openai import OpenAI
from dotenv import load_dotenv
import os
import re
from difflib import SequenceMatcher

# Load environment variables
load_dotenv()

# Centralized OpenAI Client
key = os.getenv("OPEN_AI_KEY")
client = OpenAI(api_key=key)

# Technical Dictionary Configuration
TECHNICAL_DICTIONARY = {
    "fast api": "FastAPI",
    "fastapi": "FastAPI",
    "lang chain": "LangChain",
    "langchain": "LangChain",
    "lang graph": "LangGraph",
    "langgraph": "LangGraph",
    "lang smith": "LangSmith",
    "langsmith": "LangSmith",
    "milvis db": "MilvusDB",
    "milvus db": "MilvusDB",
    "milvusdb": "MilvusDB",
    "bm twenty five": "BM25",
    "bm25": "BM25",
    "h n s w": "HNSW",
    "hnsw": "HNSW",
    "r a g": "RAG",
    "rag": "RAG",
    "agentic ai": "Agentic AI",
    "whisper": "Whisper",
    "deep gram": "Deepgram",
    "deepgram": "Deepgram",
    "nova three": "Nova-3",
    "nova 3": "Nova-3",
    "chroma db": "ChromaDB",
    "chromadb": "ChromaDB"
}

def normalize_text(text: str) -> (str, bool):
    """Normalize common technical terms case-insensitively using dictionary."""
    if not text:
        return "", False
    
    normalized = text
    modified = False
    
    # Sort terms by length descending to match longer phrases first
    sorted_terms = sorted(TECHNICAL_DICTIONARY.keys(), key=len, reverse=True)
    for term in sorted_terms:
        pattern = re.compile(rf'\b{re.escape(term)}\b', re.IGNORECASE)
        new_text, count = pattern.subn(TECHNICAL_DICTIONARY[term], normalized)
        if count > 0:
            normalized = new_text
            modified = True
            
    return normalized, modified

def should_invoke_gpt(original_text: str, normalized_text: str, confidence: float = 1.0) -> bool:
    """Decision engine: Determine whether LLM correction is needed."""
    if not normalized_text:
        return False

    # Rule 1: Confidence score below threshold
    if confidence < 0.85:
        return True

    # Rule 2: Broken/incomplete sentences (ends in conjunction or preposition)
    broken_ends = {"and", "or", "but", "with", "of", "the", "a", "an", "to", "for", "in", "on", "at"}
    words = normalized_text.strip().lower().split()
    if words and words[-1] in broken_ends:
        return True

    # Rule 3: Suspicious repetitions (common STT stutter / hallucination)
    if len(words) > 2:
        for i in range(len(words) - 2):
            if words[i] == words[i+1] == words[i+2]:
                return True

    # Rule 4: Search for known uncorrected misspellings
    suspect_phrases = ["land graph", "landra", "vm 25", "vm25", "milvis", "hnsw", "rag"]
    normalized_lower = normalized_text.lower()
    for phrase in suspect_phrases:
        if phrase in normalized_lower:
            return True

    return False

async def llm_cleaning(context: str, current_text: str) -> str:
    """Clean transcript using OpenAI GPT-4o-mini with context."""
    from prompt import SYSTEM_PROMPT
    prompt = SYSTEM_PROMPT.format(
        recent_transcript=context if context else "(no prior context)",
        incoming_text=current_text
    )

    try:
        response = await asyncio.to_thread(
            client.chat.completions.create,
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=100,
            temperature=0.0,
            timeout=8
        )

        if not response or not response.choices:
            return current_text

        cleaned = response.choices[0].message.content
        if cleaned:
            return cleaned.strip()
        return current_text

    except Exception as e:
        err_msg = str(e).lower()
        if "api_key" in err_msg or "unauthorized" in err_msg or "401" in err_msg or "quota" in err_msg or "rate limit" in err_msg:
            raise e
        return current_text

def validate_similarity(original: str, corrected: str) -> bool:
    """Similarity validation: check if semantic drift is within acceptable bounds."""
    if not original or not corrected:
        return False
    
    str1 = " ".join(original.lower().split())
    str2 = " ".join(corrected.lower().split())
    
    ratio = SequenceMatcher(None, str1, str2).ratio()
    threshold = 0.5 if len(str1) < 15 else 0.7
    
    return ratio >= threshold
