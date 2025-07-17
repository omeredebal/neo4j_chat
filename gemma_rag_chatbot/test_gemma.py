import requests

# 👉 Buraya kendi OpenRouter API key'ini yapıştır
api_key = "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"

# Gerekli HTTP başlıkları
headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json"
}

# API'ye gönderilecek veri (Gemma modeli)
data = {
    "model": "google/gemma-3-27b-it:free",  # Doğru ve aktif model ismi
    "messages": [
        {"role": "system", "content": "Sen yardımsever bir asistansın."},
        {"role": "user", "content": "Neo4j nedir?"}
    ]
}

# API isteğini gönder
response = requests.post("https://openrouter.ai/api/v1/chat/completions", json=data, headers=headers)

# ✅ Yanıtı işle
try:
    content = response.json()['choices'][0]['message']['content']
    print(">>> Gemma yanıtı:")
    print(content)
except Exception:
    print(">>> HATA veya boş yanıt döndü:")
    print(response.text)
