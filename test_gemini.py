#!/usr/bin/env python3
"""
Gemini API bağlantı testi
"""

import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

try:
    import google.generativeai as genai
    print("✅ google-generativeai paketi başarıyla yüklendi")
except ImportError as e:
    print(f"❌ google-generativeai paketi yüklenemedi: {e}")
    exit(1)

# API key kontrolü
api_key = os.getenv('GEMINI_API_KEY')
if not api_key:
    print("❌ GEMINI_API_KEY bulunamadı .env dosyasında")
    exit(1)

print(f"✅ GEMINI_API_KEY bulundu (son 8 karakter: ...{api_key[-8:]})")

# Gemini API'yi başlat
try:
    genai.configure(api_key=api_key)
    print("✅ Gemini API konfigürasyonu tamamlandı")
except Exception as e:
    print(f"❌ Gemini API konfigürasyonu başarısız: {e}")
    exit(1)

# Model listesini al
try:
    models = list(genai.list_models())
    print(f"✅ Gemini API bağlantısı başarılı, {len(models)} model bulundu")
    
    # gemini-1.5-flash modelini kontrol et
    flash_model = None
    for model in models:
        if 'gemini-1.5-flash' in model.name:
            flash_model = model
            break
    
    if flash_model:
        print(f"✅ gemini-1.5-flash modeli bulundu: {flash_model.name}")
    else:
        print("⚠️ gemini-1.5-flash modeli bulunamadı, mevcut modeller:")
        for model in models:
            print(f"  - {model.name}")
            
except Exception as e:
    print(f"❌ Gemini API bağlantı hatası: {e}")
    print(f"❌ Hata tipi: {type(e).__name__}")
    exit(1)

# Basit bir test yap
try:
    model = genai.GenerativeModel('gemini-1.5-flash')
    response = model.generate_content("Merhaba, bu bir test mesajıdır. Türkçe yanıt ver.")
    
    if response and response.text:
        print("✅ Gemini API test başarılı!")
        print(f"📝 Yanıt: {response.text[:100]}...")
    else:
        print("⚠️ Gemini API yanıt verdi ama boş")
        
except Exception as e:
    print(f"❌ Gemini API test başarısız: {e}")
    print(f"❌ Hata tipi: {type(e).__name__}")
    
    # API key hatası kontrolü
    if "API_KEY" in str(e) or "authentication" in str(e).lower():
        print("🔑 API key sorunu olabilir. Yeni key deneyin:")
        print("   https://aistudio.google.com/app/apikey")
    elif "quota" in str(e).lower() or "limit" in str(e).lower():
        print("📊 Quota/limit sorunu. Gemini API limitlerini kontrol edin")
    elif "region" in str(e).lower() or "location" in str(e).lower():
        print("🌍 Bölge kısıtlaması olabilir. VPN deneyin")

print("\n🎯 Test tamamlandı!")
