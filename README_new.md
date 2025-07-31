# 🔗 Neo4j GraphRAG Asistanı

> **İnceHesap teknolojileriyle güçlendirilmiş akıllı veritabanı sorgulama sistemi**

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://python.org)
[![Neo4j](https://img.shields.io/badge/Neo4j-5.0+-red.svg)](https://neo4j.com)
[![GraphRAG](https://img.shields.io/badge/GraphRAG-Pipeline-orange.svg)](https://github.com)
[![Gemini](https://img.shields.io/badge/Gemini-AI-purple.svg)](https://ai.google.dev)

## 🎯 Proje Özeti

Neo4j GraphRAG Asistanı, doğal dilde yazılan soruları Neo4j Cypher sorgularına çeviren ve akıllı cevaplar üreten gelişmiş bir **Graph Retrieval-Augmented Generation** sistemidir. Dinamik schema detection, semantic search ve hybrid retrieval teknolojilerini birleştirerek profesyonel graf veritabanı analizi sunar.

## ⚡ Ana Özellikler

- **🧠 GraphRAG Pipeline**: Vector embeddings + Graph context hybrid retrieval
- **🔄 Text2Cypher**: Türkçe soruları Cypher sorgularına otomatik çevirme  
- **📊 Dynamic Schema**: Canlı veritabanı yapısını otomatik algılama
- **🎨 Modern UI**: Responsive web arayüzü ve real-time sorgulama
- **🚀 Unlimited Data**: Karakter/token limit olmadan tüm veri erişimi
- **💾 Smart Cache**: SHA256 hash tabanlı akıllı önbellekleme sistemi

## 🏗️ Sistem Mimarisi

```
Neo4j Database ←→ GraphRAG Pipeline ←→ Gemini AI ←→ Web Interface
      ↓                    ↓                ↓            ↓
   Schema          Vector Embeddings    Text2Cypher   User Query
   Detection       Graph Context        Generation    Processing
```

## 📦 Proje Yapısı

```
neo4j_chat/
├── app.py                 # Ana Flask uygulaması & GraphRAG entegrasyonu
├── embeddings.py          # Vector embeddings & semantic search
├── context_manager.py     # Graf context management
├── graphrag_pipeline.py   # Hybrid retrieval pipeline
├── cache.py              # Akıllı önbellekleme sistemi
├── history.py            # Sohbet geçmişi yönetimi
├── templates/index.html  # Modern web arayüzü
└── requirements.txt      # Python dependencies
```

## 🚀 Kurulum

### 1. Gereksinimler
```bash
# Python 3.8+ gerekli
# Neo4j 5.0+ veritabanı
# Gemini API anahtarı
```

### 2. Ortam Kurulumu
```bash
git clone <repository-url>
cd neo4j_chat
python -m venv chatbot_env
chatbot_env\Scripts\activate  # Windows
pip install -r requirements.txt
```

### 3. Konfigürasyon
```bash
# .env dosyasını oluşturun
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_password
GEMINI_API_KEY=your_gemini_key
USE_GEMINI=True
```

### 4. Çalıştırma
```bash
python app.py
# http://localhost:5000 adresini ziyaret edin
```

## 💡 Kullanım Örnekleri

```
✅ "Obsidian Elite ürününe yapılan yorumu getir"
✅ "En çok bağlantısı olan node hangisi?"
✅ "MSI marka ürünlerini listele"
✅ "Veritabanı şemasını göster"
✅ "En büyük bağlı bileşen nedir?"
```

## 🔧 Teknik Detaylar

### GraphRAG Components
- **EmbeddingManager**: Gemini AI ile vector embeddings
- **GraphContextManager**: Multi-hop graph traversal
- **GraphRAGPipeline**: Hybrid semantic + structural retrieval

### Dynamic Features  
- **Schema Detection**: Real-time database structure analysis
- **Property Discovery**: Automatic node/relationship property mapping
- **Smart Query Generation**: Context-aware Cypher creation
- **JSON Serialization**: Safe Neo4j object conversion

## 📊 Performans

- **Query Speed**: ~2-3 saniye (cache miss)
- **Cache Hit**: ~100ms yanıt süresi
- **Semantic Search**: 1000+ node'da etkili
- **Memory Usage**: ~100MB RAM (ortalama)

## 🛡️ Güvenlik

- **SQL Injection Protection**: Cypher query validation
- **Safe Execution**: Sadece MATCH/RETURN sorguları
- **Error Handling**: Comprehensive exception management
- **Access Control**: Environment variable based auth

## 🤝 Katkıda Bulunma

1. Fork edin
2. Feature branch oluşturun (`git checkout -b feature/amazing-feature`)
3. Commit yapın (`git commit -m 'Add amazing feature'`)
4. Push edin (`git push origin feature/amazing-feature`)
5. Pull Request açın

## 📄 Lisans

Bu proje MIT lisansı altında yayınlanmıştır. Detaylar için `LICENSE` dosyasına bakın.

---

**İnceHesap Neo4j GraphRAG Asistanı** - Graf veritabanlarınızı akıllı sorgulama deneyimi
