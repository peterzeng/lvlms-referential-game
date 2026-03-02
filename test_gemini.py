#!/usr/bin/env python3
"""Quick test script to verify Gemini API is working."""

import os
import sys

# Check for API key
api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
if not api_key:
    print("ERROR: No GEMINI_API_KEY or GOOGLE_API_KEY set in environment")
    sys.exit(1)

print(f"API key found: {api_key[:8]}...")

try:
    from google import genai
    from google.genai import types
    print("✓ google-genai SDK imported successfully")
except ImportError as e:
    print(f"✗ Failed to import google-genai: {e}")
    sys.exit(1)

# Create client
print("\nCreating client...")
client = genai.Client(api_key=api_key)
print("✓ Client created")

# Test 1: Simple call without thinking config
print("\n--- Test 1: Simple call (no thinking config) ---")
try:
    response = client.models.generate_content(
        model="gemini-3-flash-preview",
        contents="Say 'hello world' and nothing else.",
    )
    print(f"✓ Response: {response.text[:100] if response.text else 'EMPTY'}")
except Exception as e:
    print(f"✗ Error: {type(e).__name__}: {e}")

# Test 2: Call with thinking_level="low"
print("\n--- Test 2: With thinking_level='low' ---")
try:
    response = client.models.generate_content(
        model="gemini-3-flash-preview",
        contents="Say 'hello world' and nothing else.",
        config=types.GenerateContentConfig(
            thinking_config=types.ThinkingConfig(thinking_level="low")
        ),
    )
    print(f"✓ Response: {response.text[:100] if response.text else 'EMPTY'}")
except Exception as e:
    print(f"✗ Error: {type(e).__name__}: {e}")

# Test 3: Call with thinking_level="minimal" (Flash only)
print("\n--- Test 3: With thinking_level='minimal' (Flash only) ---")
try:
    response = client.models.generate_content(
        model="gemini-3-flash-preview",
        contents="Say 'hello world' and nothing else.",
        config=types.GenerateContentConfig(
            thinking_config=types.ThinkingConfig(thinking_level="minimal")
        ),
    )
    print(f"✓ Response: {response.text[:100] if response.text else 'EMPTY'}")
except Exception as e:
    print(f"✗ Error: {type(e).__name__}: {e}")

print("\n--- Tests complete ---")

