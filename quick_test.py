#!/usr/bin/env python3
import os
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv('GEMINI_API_KEY')
print(f"API Key: {api_key}")

try:
    import google.generativeai as genai
    genai.configure(api_key=api_key)
    
    model = genai.GenerativeModel('gemini-1.5-flash')
    response = model.generate_content("Merhaba", 
        generation_config=genai.types.GenerationConfig(max_output_tokens=50))
    
    print(f"SUCCESS: {response.text}")
except Exception as e:
    print(f"ERROR: {e}")
    print(f"Type: {type(e).__name__}")
    
    if "403" in str(e):
        print("API Key invalid or region blocked")
    elif "400" in str(e):
        print("Bad request - check model name")
    elif "quota" in str(e).lower():
        print("Quota exceeded")
