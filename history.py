import json
import os
from datetime import datetime

HISTORY_FILE = "history.json"
MAX_HISTORY = 10  # Son 10 konuşmayı sakla

def load_history():
    """Geçmişi yükle"""
    if not os.path.exists(HISTORY_FILE):
        return []
    
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            history = json.load(f)
            # Geçerli formatta olduğunu kontrol et
            if isinstance(history, list):
                return history
            else:
                return []
    except (json.JSONDecodeError, IOError) as e:
        print(f"❌ Geçmiş dosyası okunamadı: {e}")
        return []

def save_history(history):
    """Geçmişi kaydet"""
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except IOError as e:
        print(f"❌ Geçmiş dosyası kaydedilemedi: {e}")

def add_to_history(question, answer):
    """Geçmişe yeni konuşma ekle"""
    history = load_history()
    
    # Yeni konuşma
    new_entry = {
        "question": question,
        "answer": answer,
        "timestamp": datetime.now().isoformat()
    }
    
    # Aynı sorunun zaten var olup olmadığını kontrol et
    for i, entry in enumerate(history):
        if entry.get("question") == question:
            # Güncelle
            history[i] = new_entry
            save_history(history)
            print(f"🔄 Geçmiş güncellendi: {question[:50]}...")
            return history
    
    # Yeni ekle
    history.append(new_entry)
    
    # Maksimum sayıyı aşırsa eski olanları sil
    if len(history) > MAX_HISTORY:
        history = history[-MAX_HISTORY:]
    
    save_history(history)
    print(f"➕ Geçmişe eklendi: {question[:50]}...")
    return history

def get_recent_history(count=5):
    """Son N konuşmayı al"""
    history = load_history()
    return history[-count:] if history else []

def clear_history():
    """Tüm geçmişi temizle"""
    if os.path.exists(HISTORY_FILE):
        os.remove(HISTORY_FILE)
        print("🗑️ Geçmiş temizlendi")

def search_history(keyword):
    """Geçmişte arama yap"""
    history = load_history()
    results = []
    
    for entry in history:
        if keyword.lower() in entry.get("question", "").lower():
            results.append(entry)
    
    return results