import io
import asyncio
from openai import OpenAI
from fastapi import WebSocket
from dotenv import load_dotenv

from prompt import SYSTEM_PROMPT
from difflib import SequenceMatcher
import os

# Load environment variables from .env file
load_dotenv()

# Centralized OpenAI Client Setup here
key = os.getenv("OPEN_AI_KEY")
client = OpenAI(api_key=key)

async def llm_cleaning(context: str, current_text: str) -> str:
    """Clean transcript using LLM with context"""
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
            temperature=0.0,  # Temperature 0.0 for deterministic transcript correction
            timeout=8
        )

        if not response or not response.choices:
            print("   Empty LLM response, using original")
            return current_text

        cleaned = response.choices[0].message.content
        if cleaned:
            cleaned = cleaned.strip()
            
            # If the model returned [SILENCE], allow it to propagate so main.py can handle it
            if cleaned == "[SILENCE]":
                return cleaned
            
            # Normalize for similarity checking
            str1 = " ".join(current_text.lower().split())
            str2 = " ".join(cleaned.lower().split())
            
            if str1:
                ratio = SequenceMatcher(None, str1, str2).ratio()
                
                # Dynamic threshold: more permissive for short phrases (to allow corrections like "VM 25" -> "BM25")
                # and stricter for longer phrases (to prevent GPT from editing/paraphrasing)
                threshold = 0.5 if len(str1) < 15 else 0.7
                
                if ratio < threshold:
                    print(f"⚠️ Similarity/drift check failed (ratio: {ratio:.2f}, threshold: {threshold}). Falling back to raw transcript: '{current_text}' (GPT output: '{cleaned}')")
                    return current_text
            
            return cleaned
        return current_text

    except asyncio.TimeoutError:
        print("   LLM timeout, using original")
        return current_text
    except Exception as e:
        print(f"  LLM error: {e}, using original")
        return current_text
