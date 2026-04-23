import io
import asyncio
from openai import OpenAI
from fastapi import WebSocket

from prompt import SYSTEM_PROMPT
import os
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
            max_tokens=200,
            temperature=0.3,  # Lower temp for more consistent corrections
            timeout=8
        )

        if not response or not response.choices:
            print("   Empty LLM response, using original")
            return current_text

        cleaned = response.choices[0].message.content
        return cleaned.strip() if cleaned else current_text

    except asyncio.TimeoutError:
        print("   LLM timeout, using original")
        return current_text
    except Exception as e:
        print(f"  LLM error: {e}, using original")
        return current_text
