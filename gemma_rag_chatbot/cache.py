import json
import hashlib
import os
from datetime import datetime, timedelta

CACHE_FILE = "cache.json"
CACHE_EXPIRE_HOURS = 24  # 24 saat sonra cache'i temizle

def _load_cache():
    """Cache dosyasını yükle"""
    if not os.path.exists(CACHE_FILE):
        return {}
    
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"❌ Cache dosyası okunamadı: {e}")
        return {}

def _save_cache(cache):
    """Cache dosyasını kaydet"""
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except IOError as e:
        print(f"❌ Cache dosyası kaydedilemedi: {e}")

def _is_expired(timestamp):
    """Cache'in süresi dolmuş mu kontrol et"""
    if not timestamp:
        return True
    
    try:
        cache_time = datetime.fromisoformat(timestamp)
        expire_time = cache_time + timedelta(hours=CACHE_EXPIRE_HOURS)
        return datetime.now() > expire_time
    except:
        return True

def _clean_expired_cache():
    """Süresi dolmuş cache'leri temizle"""
    cache = _load_cache()
    cleaned_cache = {}
    
    for key, value in cache.items():
        if isinstance(value, dict) and "timestamp" in value:
            if not _is_expired(value["timestamp"]):
                cleaned_cache[key] = value
        else:
            # Eski format - sil
            pass
    
    if len(cleaned_cache) != len(cache):
        _save_cache(cleaned_cache)
        print(f"🧹 {len(cache) - len(cleaned_cache)} adet eski cache temizlendi")

def get_from_cache(key):
    """Cache'den veri al"""
    cache = _load_cache()
    hash_key = hashlib.sha256(key.encode()).hexdigest()
    
    if hash_key in cache:
        cached_item = cache[hash_key]
        
        # Yeni format kontrolü
        if isinstance(cached_item, dict) and "timestamp" in cached_item:
            if not _is_expired(cached_item["timestamp"]):
                print(f"✅ Cache'den alındı: {key[:50]}...")
                return cached_item["data"]
            else:
                print(f"⏰ Cache süresi dolmuş: {key[:50]}...")
                return None
        else:
            # Eski format - sil
            del cache[hash_key]
            _save_cache(cache)
            return None
    
    return None

def save_to_cache(key, data):
    """Cache'e veri kaydet"""
    cache = _load_cache()
    hash_key = hashlib.sha256(key.encode()).hexdigest()
    
    cache[hash_key] = {
        "data": data,
        "timestamp": datetime.now().isoformat()
    }
    
    _save_cache(cache)
    print(f"💾 Cache'e kaydedildi: {key[:50]}...")

def clear_cache():
    """Tüm cache'i temizle"""
    if os.path.exists(CACHE_FILE):
        os.remove(CACHE_FILE)
        print("🗑️ Cache temizlendi")

# Başlangıçta eski cache'leri temizle
_clean_expired_cache()