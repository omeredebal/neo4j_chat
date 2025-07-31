#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import requests
from dotenv import load_dotenv

print("=== OPENROUTER API TEST ===")

# Load environment
load_dotenv()
api_key = os.getenv('OPENROUTER_API_KEY')

if not api_key:
    print("[ERROR] OpenRouter API key not found")
    exit(1)

print(f"[OK] API Key found: {api_key[:10]}...{api_key[-4:]}")

# Test models
test_models = [
    'google/gemma-2-9b-it:free',
    'meta-llama/llama-3.1-8b-instruct:free',
    'microsoft/phi-3-medium-128k-instruct:free',
    'qwen/qwen-2-7b-instruct:free'
]

for model in test_models:
    print(f"\n[TEST] Testing model: {model}")
    
    try:
        response = requests.post(
            'https://openrouter.ai/api/v1/chat/completions',
            headers={
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json'
            },
            json={
                'model': model,
                'messages': [
                    {
                        'role': 'user',
                        'content': 'Merhaba, test mesajı. Kısa yanıt ver.'
                    }
                ],
                'temperature': 0.1,
                'max_tokens': 50
            },
            timeout=10
        )
        
        if response.status_code == 200:
            result = response.json()
            if 'choices' in result and result['choices']:
                content = result['choices'][0]['message']['content']
                print(f"[OK] {model} - Response: {content[:50]}...")
            else:
                print(f"[ERROR] {model} - Empty response")
        else:
            print(f"[ERROR] {model} - HTTP {response.status_code}")
            if response.status_code == 404:
                print(f"[INFO] Model {model} not found or deprecated")
                
    except Exception as e:
        print(f"[ERROR] {model} - Exception: {e}")

print("\n=== TEST COMPLETE ===")
