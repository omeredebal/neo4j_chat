#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
from dotenv import load_dotenv

print("=== GEMINI API TEST ===")

# Load environment
load_dotenv()
print("[OK] Environment loaded")

# Check API key
api_key = os.getenv('GEMINI_API_KEY')
if api_key:
    print(f"[OK] API Key found: {api_key[:10]}...{api_key[-4:]}")
else:
    print("[ERROR] API Key not found")
    sys.exit(1)

# Try import
try:
    import google.generativeai as genai
    print("[OK] Gemini library imported")
except Exception as e:
    print(f"[ERROR] Import failed: {e}")
    sys.exit(1)

# Configure
try:
    genai.configure(api_key=api_key)
    print("[OK] API configured")
except Exception as e:
    print(f"[ERROR] Configuration failed: {e}")
    sys.exit(1)

# List available models
try:
    models = list(genai.list_models())
    print(f"[OK] Found {len(models)} available models")
    for model in models[:3]:
        print(f"  - {model.name}")
except Exception as e:
    print(f"[ERROR] Model listing failed: {e}")
    if "403" in str(e):
        print("[INFO] API key might be invalid or restricted")
    elif "quota" in str(e).lower():
        print("[INFO] API quota exceeded")
    sys.exit(1)

# Test simple generation
try:
    model = genai.GenerativeModel('gemini-1.5-flash')
    print("[OK] Model created")
    
    response = model.generate_content(
        "Merhaba, test mesajı",
        generation_config=genai.types.GenerationConfig(
            temperature=0.1,
            max_output_tokens=50
        )
    )
    
    if response.text:
        print("[OK] Generation successful")
        print(f"Response: {response.text}")
    else:
        print("[ERROR] Empty response")
        if response.candidates:
            candidate = response.candidates[0]
            print(f"Finish reason: {candidate.finish_reason}")
        
except Exception as e:
    print(f"[ERROR] Generation failed: {e}")
    print(f"Error type: {type(e).__name__}")
    if "403" in str(e):
        print("[INFO] Check your API key permissions")
    elif "429" in str(e):
        print("[INFO] Rate limit exceeded")

print("=== TEST COMPLETE ===")
