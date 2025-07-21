# 🎬 Neo4j RAG Chatbot

Film veritabanı üzerinde doğal dil ile sorgulama yapabilen akıllı chatbot uygulaması. Neo4j graf veritabanı ve Gemma LLM kullanarak kullanıcı sorularını Cypher sorgularına dönüştürür ve anlamlı cevaplar üretir.

## ✨ Özellikler

- **Doğal Dil Anlama**: Türkçe sorularınızı Neo4j Cypher sorgularına dönüştürür
- **Akıllı Önbellek**: Tekrar eden sorular için hızlı yanıt
- **Konuşma Geçmişi**: Son 10 konuşmanızı hatırlar
- **Graf Veritabanı**: Neo4j ile güçlü film veritabanı
- **LLM Entegrasyonu**: Gemma 3 modeli ile doğal cevaplar

## 🚀 Kurulum

### 1. Gereksinimler

```bash
# Python 3.8+
# Neo4j Desktop veya Neo4j Community Server
```

### 2. Projeyi İndirin

```bash
git clone <repo-url>
cd neo4j_chat/gemma_rag_chatbot
```

### 3. Sanal Ortam Oluşturun

```bash
python -m venv chatbot_env
# Windows:
chatbot_env\Scripts\activate
# Linux/MacOS:
source chatbot_env/bin/activate
```

### 4. Bağımlılıkları Yükleyin

```bash
pip install -r requirements.txt
```

### 5. Neo4j Veritabanını Kurun

1. [Neo4j Desktop](https://neo4j.com/download/) indirin
2. Yeni bir veritabanı oluşturun
3. Film veritabanını içe aktarın (örnek veri)
4. Veritabanı bilgilerini `app.py` dosyasında güncelleyin

### 6. API Anahtarını Ayarlayın

`app.py` dosyasında OpenRouter API anahtarınızı güncelleyin:

```python
OPENROUTER_API_KEY = "your-api-key-here"
```

## 🎯 Kullanım

### Uygulamayı Başlatın

```bash
python app.py
```

Tarayıcınızda `http://localhost:5000` adresine gidin.

### Örnek Sorular

- "Matrix filminde kim oynadı?"
- "Tom Cruise'un oynadığı filmleri listele"
- "Keanu Reeves hangi filmlerde oynadı?"
- "2000 yılından sonra çıkan filmler"
- "Keanu Reeves'in filmlerden kazandığı maaşları göster"

## 🏗️ Proje Yapısı

```
gemma_rag_chatbot/
├── app.py              # Ana Flask uygulaması
├── cache.py            # Önbellek yönetimi
├── history.py          # Konuşma geçmişi yönetimi
├── cache.json          # Önbellek verileri
├── history.json        # Konuşma geçmişi
├── requirements.txt    # Python bağımlılıkları
└── templates/
    └── index.html      # Web arayüzü
```

## 🔧 Yapılandırma

### Neo4j Bağlantı Ayarları

```python
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASS = "your-password"
```

### Veritabanı Şeması

```cypher
(p:Person)-[:ACTED_IN]->(m:Movie)
(p:Person)-[:DIRECTED]->(m:Movie)
(m:Movie)-[:BELONGS_TO_GENRE]->(g:Genre)
(m:Movie)-[:PRODUCED_BY]->(c:Company)
(m:Movie)-[:PRODUCED_IN_COUNTRY]->(co:Country)
(m:Movie)-[:SPOKEN_IN_LANGUAGE]->(l:Language)
```

## 💡 Nasıl Çalışır?

1. **Soru Analizi**: Kullanıcı sorusu LLM tarafından analiz edilir
2. **Cypher Üretimi**: Soru Neo4j Cypher sorgusuna dönüştürülür
3. **Veri Çekimi**: Sorgu Neo4j veritabanında çalıştırılır
4. **Cevap Üretimi**: Sonuçlar LLM tarafından doğal dile çevrilir
5. **Önbellek**: Sonuçlar gelecekte hızlı erişim için saklanır

## 📊 Performans Optimizasyonları

- **Akıllı Önbellek**: 24 saat süreyle yanıtları saklar
- **Sorgu Sınırları**: Maksimum 50 sonuç döndürür
- **Geçmiş Yönetimi**: Son 10 konuşmayı tutar
- **Hata Yönetimi**: Kapsamlı hata yakalama ve logging

## 🔐 Güvenlik

- API anahtarları kod içinde saklanır (production için environment variables kullanın)
- Cypher injection koruması
- Güvenli Neo4j bağlantıları

## 🛠️ Geliştirme

### Debug Modunu Aktifleştirin

```python
app.run(debug=True, host="0.0.0.0", port=5000)
```

### Önbellek Temizleme

```python
from cache import clear_cache
clear_cache()
```

### Geçmiş Temizleme

```python
from history import clear_history
clear_history()
```

## 🤝 Katkıda Bulunma

1. Fork yapın
2. Feature branch oluşturun (`git checkout -b feature/AmazingFeature`)
3. Commit yapın (`git commit -m 'Add some AmazingFeature'`)
4. Push yapın (`git push origin feature/AmazingFeature`)
5. Pull Request oluşturun

## 📝 Lisans

Bu proje MIT lisansı altında lisanslanmıştır.

## 🙏 Teşekkürler

- [Neo4j](https://neo4j.com/) - Graf veritabanı
- [OpenRouter](https://openrouter.ai/) - LLM API
- [Flask](https://flask.palletsprojects.com/) - Web framework
- [Gemma](https://ai.google.dev/gemma) - Language model

---

💡 **İpucu**: Daha iyi sonuçlar için sorularınızı mümkün olduğunca açık ve spesifik şekilde sorun!
