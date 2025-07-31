import os
import sys
from dotenv import load_dotenv

print("=== GEMINI API DEBUG ===")

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

# Test simple generation
try:
    model = genai.GenerativeModel('gemini-1.5-flash')
    print("[OK] Model created")
    
    response = model.generate_content("Hello")
    print("[OK] Generation successful")
    print(f"Response: {response.text[:100]}...")
    
except Exception as e:
    print(f"[ERROR] Generation failed: {e}")
    print(f"Error type: {type(e).__name__}")

print("=== DEBUG COMPLETE ===")
