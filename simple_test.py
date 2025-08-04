#!/usr/bin/env python3
import os
import sys
sys.path.append('.')

from dotenv import load_dotenv
load_dotenv()

try:
    import google.generativeai as genai
    
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        print("API key bulunamadi")
        sys.exit(1)
    
    print(f"API Key: {api_key[:10]}...{api_key[-4:]}")
    
    genai.configure(api_key=api_key)
    print("API configured")
    
    # Test basit model
    model = genai.GenerativeModel('gemini-1.5-flash')
    print("Model created")
    
    # Basit test
    response = model.generate_content("Merhaba, nasılsın?")
    
    if response.text:
        print(f"SUCCESS: {response.text}")
    else:
        print("EMPTY RESPONSE")
        if response.candidates:
            candidate = response.candidates[0]
            print(f"Finish reason: {candidate.finish_reason}")
            
except Exception as e:
    print(f"ERROR: {e}")
    print(f"Type: {type(e).__name__}")
