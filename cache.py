import json
import hashlib
import os
from datetime import datetime, timedelta

CACHE_FILE = "cache.json"
CACHE_EXPIRE_HOURS = 24  # 24 saat sonra cache'i temizle

def serialize_for_cache(obj):
    """Neo4j objelerini cache'e kaydetmek için serialize et"""
    if hasattr(obj, 'labels') and hasattr(obj, 'items'):  # Neo4j Node
        return {
            'type': 'neo4j_node',
            'labels': list(obj.labels),
            'properties': dict(obj.items()),
            'id': obj.element_id if hasattr(obj, 'element_id') else str(obj.id)
        }
    elif hasattr(obj, 'type') and hasattr(obj, 'start_node'):  # Neo4j Relationship
        return {
            'type': 'neo4j_relationship',
            'rel_type': obj.type,
            'properties': dict(obj.items()),
            'start_node': obj.start_node.element_id if hasattr(obj.start_node, 'element_id') else str(obj.start_node.id),
            'end_node': obj.end_node.element_id if hasattr(obj.end_node, 'element_id') else str(obj.end_node.id)
        }
    elif isinstance(obj, list):
        return [serialize_for_cache(item) for item in obj]
    elif isinstance(obj, dict):
        return {key: serialize_for_cache(value) for key, value in obj.items()}
    else:
        return obj

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
    """Cache'e veri kaydet (Neo4j objelerini serialize ederek)"""
    try:
        cache = _load_cache()
        hash_key = hashlib.sha256(key.encode()).hexdigest()
        
        # Serialize Neo4j objects
        serialized_data = serialize_for_cache(data)
        
        cache[hash_key] = {
            "data": serialized_data,
            "timestamp": datetime.now().isoformat()
        }
        
        _save_cache(cache)
        print(f"💾 Cache'e kaydedildi: {key[:50]}...")
        
    except Exception as e:
        print(f"❌ Cache kaydetme hatası: {e}")
        # Don't raise exception, just log it

def clear_cache():
    """Tüm cache'i temizle"""
    if os.path.exists(CACHE_FILE):
        os.remove(CACHE_FILE)
        print("🗑️ Cache temizlendi")

# Başlangıçta eski cache'leri temizle
_clean_expired_cache()


# ========== SCHEMA CACHE İYİLEŞTİRMESİ ==========

import time
from typing import Optional, Dict, Any

class SchemaCache:
    """Schema bilgilerini cache'leyerek performansı artıran sınıf"""
    
    def __init__(self, ttl_seconds: int = 300):  # 5 dakika default
        self.cache: Optional[Dict[str, Any]] = None
        self.last_update: float = 0
        self.ttl = ttl_seconds
        self.cache_key = "neo4j_schema_cache"
        
        # Başlangıçta persistent cache'den yükle
        self._load_from_persistent_cache()
    
    def get_schema(self) -> Optional[Dict[str, Any]]:
        """Schema cache'ini al, expired ise None döndür"""
        if self.is_expired():
            return None
        return self.cache
    
    def set_schema(self, schema: Dict[str, Any]) -> None:
        """Schema'yı cache'le ve persistent storage'a kaydet"""
        self.cache = schema
        self.last_update = time.time()
        
        # Persistent cache'e de kaydet
        self._save_to_persistent_cache(schema)
        
        print(f"📊 Schema cache güncellendi (TTL: {self.ttl}s)")
    
    def is_expired(self) -> bool:
        """Cache'in süresi dolmuş mu?"""
        if self.cache is None:
            return True
        return time.time() - self.last_update > self.ttl
    
    def get_cache_age(self) -> float:
        """Cache'in yaşını saniye cinsinden döndür"""
        if self.cache is None:
            return float('inf')
        return time.time() - self.last_update
    
    def clear_cache(self) -> None:
        """Cache'i temizle"""
        self.cache = None
        self.last_update = 0
        
        # Persistent cache'den de sil
        cache = _load_cache()
        hash_key = hashlib.sha256(self.cache_key.encode()).hexdigest()
        if hash_key in cache:
            del cache[hash_key]
            _save_cache(cache)
        
        print("🗑️ Schema cache temizlendi")
    
    def _load_from_persistent_cache(self) -> None:
        """Persistent cache'den schema'yı yükle"""
        try:
            cached_schema = get_from_cache(self.cache_key)
            if cached_schema:
                self.cache = cached_schema
                self.last_update = time.time()  # Fresh olarak işaretle
                print("📂 Schema persistent cache'den yüklendi")
        except Exception as e:
            print(f"⚠️ Persistent cache yükleme hatası: {e}")
    
    def _save_to_persistent_cache(self, schema: Dict[str, Any]) -> None:
        """Schema'yı persistent cache'e kaydet"""
        try:
            save_to_cache(self.cache_key, {
                "schema": schema,
                "memory_cache_time": self.last_update,
                "ttl_seconds": self.ttl
            })
        except Exception as e:
            print(f"⚠️ Persistent cache kaydetme hatası: {e}")

# Global schema cache instance
schema_cache = SchemaCache(ttl_seconds=300)  # 5 dakika TTL