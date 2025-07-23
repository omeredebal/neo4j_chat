# 🎬 Neo4j RAG Film Chatbot

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://python.org)
[![Flask](https://img.shields.io/badge/Flask-3.0+-green.svg)](https://flask.palletsprojects.com)
[![Neo4j](https://img.shields.io/badge/Neo4j-5.15+-red.svg)](https://neo4j.com)
[![OpenRouter](https://img.shields.io/badge/OpenRouter-API-purple.svg)](https://openrouter.ai)

Modern AI ve graf veritabanı teknolojileri kullanarak geliştirilmiş akıllı film sorgulama sistemi. Kullanıcılar Türkçe sorular sorabilir, sistem bu soruları Neo4j Cypher sorgularına dönüştürür ve anlamlı cevaplar üretir.

## ✨ Özellikler

### 🔥 Temel Özellikler
- **Doğal Dil İşleme**: Türkçe sorularınızı otomatik olarak Cypher sorgularına dönüştürür
- **Çoklu Model Desteği**: 3 farklı AI modeli ile failover sistemi
- **Akıllı Önbellek**: SHA256 hash tabanlı cache sistemi (24 saat otomatik temizlik)
- **Konuşma Geçmişi**: Son 10 konuşmanızı hatırlar ve bağlam oluşturur
- **Real-time Sağlık Kontrolü**: Neo4j bağlantı durumunu sürekli izler
- **Responsive Web UI**: Modern ve kullanıcı dostu arayüz

### 🎯 Gelişmiş Özellikler
- **Otomatik Syntax Düzeltme**: Yanlış Cypher sorgularını düzeltir (`relationships.ACTED_IN.earnings` → `r.earnings`)
- **Rate Limiting Koruması**: API limitlerini aşmamak için akıllı retry mekanizması
- **Güvenlik**: Cypher injection koruması ve tehlikeli komut engelleme
- **Hata Yakalama**: Kapsamlı error handling ve UTF-8 destekli logging
- **Auto-Reconnect**: Neo4j bağlantısı kesildiğinde otomatik yeniden bağlanma

## 🏗️ Proje Mimarisi

```
📦 gemma_rag_chatbot/
├── 📄 app.py                 # Ana Flask uygulaması (917 satır)
├── 📄 cache.py               # Akıllı önbellek sistemi
├── 📄 history.py             # Konuşma geçmişi yönetimi
├── 📄 requirements.txt       # Python bağımlılıkları
├── 📄 .env                   # Ortam değişkenleri
├── 📁 templates/
│   └── 📄 index.html         # Modern web arayüzü
├── 📄 cache.json            # Cache verileri
├── 📄 history.json          # Konuşma geçmişi
├── 📄 app.log               # Uygulama logları
└── 📄 README.md             # Dokümantasyon
```

## 🚀 Hızlı Başlangıç

### 📋 Gereksinimler

- **Python 3.8+**
- **Neo4j Desktop/Server** (5.15+)
- **OpenRouter API Key** ([buradan](https://openrouter.ai) ücretsiz alabilirsiniz)

### ⚡ Kurulum

#### 1. Projeyi İndirin
```bash
git clone <repository-url>
cd neo4j_chat/gemma_rag_chatbot
```

#### 2. Bağımlılıkları Yükleyin
```bash
pip install -r requirements.txt
```

#### 3. Neo4j Kurulumu

**Neo4j Desktop ile:**
1. [Neo4j Desktop](https://neo4j.com/download/) indirin ve kurun
2. Yeni bir database oluşturun
3. Şifreyi `Omer1642` olarak ayarlayın (veya `.env` dosyasını güncelleyin)
4. Database'i başlatın (port 7687)

**Docker ile:**
```bash
docker run \
    --name neo4j \
    -p7474:7474 -p7687:7687 \
    -d \
    --env NEO4J_AUTH=neo4j/Omer1642 \
    neo4j:latest
```

#### 4. Ortam Değişkenlerini Ayarlayın

Mevcut `.env` dosyasını düzenleyin:
```env
# Neo4j Configuration
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=Omer1642

# OpenRouter API (Kendi key'inizi buraya yazın)
OPENROUTER_API_KEY=sk-or-v1-your-api-key-here

# Model Configuration
GEMMA_MODEL=google/gemma-3-27b-it:free
FALLBACK_MODELS=google/gemma-3-27b-it:free,meta-llama/llama-3.1-8b-instruct:free,microsoft/phi-3-mini-128k-instruct:free

# Application Settings
FLASK_DEBUG=False
FLASK_HOST=0.0.0.0
FLASK_PORT=5000
SECRET_KEY=your-secret-key-here-change-in-production

# Cache Settings
CACHE_EXPIRE_HOURS=24
MAX_HISTORY_COUNT=10
```

#### 5. Örnek Veri Yükleme

Neo4j Browser'da (`http://localhost:7474`) aşağıdaki Cypher komutlarını çalıştırın:

```cypher
// Film verileri - GERÇEK SCHEMA'YA GÖRE
CREATE (matrix:Movie {title: "The Matrix", released: 1999, tagline: "Welcome to the Real World"})
CREATE (reloaded:Movie {title: "The Matrix Reloaded", released: 2003})
CREATE (revolutions:Movie {title: "The Matrix Revolutions", released: 2003})
CREATE (davinci:Movie {title: "The Da Vinci Code", released: 2006})
CREATE (topgun:Movie {title: "Top Gun", released: 1986})
CREATE (jerry:Movie {title: "Jerry Maguire", released: 1996})
CREATE (fewgood:Movie {title: "A Few Good Men", released: 1992})

// Oyuncular
CREATE (keanu:Person {name: "Keanu Reeves", born: 1964})
CREATE (tom:Person {name: "Tom Cruise", born: 1962})
CREATE (carrie:Person {name: "Carrie-Anne Moss", born: 1967})
CREATE (laurence:Person {name: "Laurence Fishburne", born: 1961})
CREATE (hugo:Person {name: "Hugo Weaving", born: 1960})
CREATE (alpacino:Person {name: "Al Pacino", born: 1940})

// ACTED_IN ilişkileri - earnings ve roles ile
CREATE (keanu)-[:ACTED_IN {earnings: 40985512, roles: ["Neo"]}]->(matrix)
CREATE (keanu)-[:ACTED_IN {earnings: 14280931, roles: ["Neo"]}]->(reloaded)
CREATE (keanu)-[:ACTED_IN {earnings: 1774495, roles: ["Neo"]}]->(revolutions)

CREATE (carrie)-[:ACTED_IN {earnings: 11013692, roles: ["Trinity"]}]->(matrix)
CREATE (carrie)-[:ACTED_IN {earnings: 45893844, roles: ["Trinity"]}]->(reloaded)
CREATE (carrie)-[:ACTED_IN {earnings: 847589, roles: ["Trinity"]}]->(revolutions)

CREATE (laurence)-[:ACTED_IN {earnings: 6627028, roles: ["Morpheus"]}]->(matrix)
CREATE (laurence)-[:ACTED_IN {earnings: 29171704, roles: ["Morpheus"]}]->(reloaded)
CREATE (laurence)-[:ACTED_IN {earnings: 12711369, roles: ["Morpheus"]}]->(revolutions)

CREATE (hugo)-[:ACTED_IN {earnings: 53301987, roles: ["Agent Smith"]}]->(matrix)
CREATE (hugo)-[:ACTED_IN {earnings: 38578122, roles: ["Agent Smith"]}]->(reloaded)
CREATE (hugo)-[:ACTED_IN {earnings: 28693627, roles: ["Agent Smith"]}]->(revolutions)

CREATE (tom)-[:ACTED_IN {earnings: 5103879, roles: ["Maverick"]}]->(topgun)
CREATE (tom)-[:ACTED_IN {earnings: 22466802, roles: ["Jerry Maguire"]}]->(jerry)
CREATE (tom)-[:ACTED_IN {earnings: 1558255, roles: ["Lt. Daniel Kaffee"]}]->(fewgood)

CREATE (alpacino)-[:ACTED_IN {earnings: 6352636, roles: ["John Milton"]}]->(:Movie {title: "The Devil's Advocate", released: 1997})

// Sosyal ağ bağlantıları
CREATE (keanu)-[:HAS_CONTACT]-(carrie)
CREATE (keanu)-[:HAS_CONTACT]-(laurence)
CREATE (carrie)-[:HAS_CONTACT]-(laurence)
```

#### 6. Uygulamayı Başlatın
```bash
python app.py
```

Tarayıcınızda `http://localhost:5000` adresine gidin! 🎉

## 📖 Kullanım Kılavuzu

### 💬 Gerçek Örnekler (Loglardan)

Aşağıdaki sorular gerçekten çalışmaktadır:

| Kategori | Örnek Sorular | Sonuç |
|----------|---------------|-------|
| **Matrix Filmleri** | "Matrix filminde kim oynadı?" | 13 oyuncu listesi + kazançları |
| **Oyuncu Kazançları** | "Bu oyuncuların her biri için kazandıkları toplam maaşları listele" | 50 oyuncu + toplam kazançları |
| **Film Filtreleme** | "2000 sonrası çıkan filmler" | 12 film listesi |
| **En Yüksek Hasılat** | "En yüksek hasılatlı filmler" | Film başına toplam kazanç |
| **Oyuncu Detayları** | "Al Pacino isimli oyunucun doğum yılı nedir ve oynadığı filmleri listele" | Doğum yılı + filmografi |

### 🔍 Sistem Tarafından Üretilen Cypher Örnekleri

```cypher
-- Matrix oyuncularını bul
MATCH (p:Person)-[r:ACTED_IN]->(m:Movie) 
WHERE m.title CONTAINS 'Matrix' 
RETURN p.name AS oyuncu, r.roles AS roller, r.earnings AS kazanc 
LIMIT 50

-- Toplam kazançları hesapla
MATCH (p:Person)-[r:ACTED_IN]->(m:Movie) 
RETURN p.name AS oyuncu_adi, SUM(r.earnings) AS toplam_maas 
ORDER BY toplam_maas DESC 
LIMIT 50

-- Al Pacino bilgileri
MATCH (p:Person)-[r:ACTED_IN]->(m:Movie) 
WHERE p.name = "Al Pacino" 
RETURN p.born AS dogum_yili, m.title AS film_adi 
LIMIT 50
```

## ⚙️ Yapılandırma

### 🤖 Desteklenen AI Modelleri

Sistem otomatik failover ile şu modelleri kullanır:

1. **google/gemma-3-27b-it:free** (Birincil) - En iyi Türkçe desteği
2. **meta-llama/llama-3.1-8b-instruct:free** (Yedek) - Hızlı alternatif
3. **microsoft/phi-3-mini-128k-instruct:free** (Yedek) - Son çare

Rate limit durumunda otomatik olarak sonraki modele geçer.

### 📊 Cache Sistemi

- **Hash Algoritması**: SHA256
- **Expire Süresi**: 24 saat
- **Otomatik Temizlik**: Başlangıçta eski cache'ler temizlenir
- **Cache Dosyası**: `cache.json`

### 📚 Konuşma Geçmişi

- **Maksimum Kayıt**: 10 konuşma
- **Format**: JSON with timestamp
- **Dosya**: `history.json`
- **Context Support**: Son 2 konuşma context olarak kullanılır

## 🔒 Güvenlik Özellikleri

### 🛡️ Cypher Injection Koruması

```python
# Tehlikeli komutlar engellenir
dangerous_keywords = [
    'DELETE', 'REMOVE', 'DROP', 'CREATE', 'MERGE', 'SET', 
    'DETACH', 'CALL', 'LOAD', 'FOREACH', 'WITH'
]
```

### 🔧 Otomatik Syntax Düzeltme

```python
# Yaygın hatalar otomatik düzeltilir
fixes = [
    (r'relationships\.ACTED_IN\.earnings', 'r.earnings'),
    (r'relationships\.ACTED_IN\.roles', 'r.roles'),
    (r'\.birthdate\b', '.born'),
    (r'-\[:ACTED_IN\]->', '-[r:ACTED_IN]->'),
]
```

## 🚀 Production Deployment

### 🐳 Docker ile

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
EXPOSE 5000

CMD ["python", "app.py"]
```

### 🌐 Environment Variables

Production için gerekli değişkenler:
```bash
export NEO4J_PASSWORD="secure_password"
export OPENROUTER_API_KEY="your_production_key"
export SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex())')"
export FLASK_DEBUG=False
```

## 📊 API Endpoints

| Method | Endpoint | Açıklama | Response |
|--------|----------|----------|----------|
| `GET` | `/` | Ana sayfa | HTML |
| `POST` | `/api/ask` | Soru sorma | JSON |
| `GET` | `/api/history` | Son 10 konuşma | JSON |
| `GET` | `/api/health` | Sistem durumu | JSON |
| `POST` | `/api/clear-cache` | Cache temizle | JSON |

### 📋 /api/ask Request/Response

**Request:**
```json
{
  "question": "Matrix filminde kim oynadı?"
}
```

**Response:**
```json
{
  "answer": "Matrix filminde rol alan oyuncular ve canlandırdıkları karakterler şöyle:\n\n1. Keanu Reeves - Neo (40,985,512)\n2. Carrie-Anne Moss - Trinity (11,013,692)...",
  "cypher": "MATCH (p:Person)-[r:ACTED_IN]->(m:Movie) WHERE m.title CONTAINS 'Matrix' RETURN p.name AS oyuncu, r.roles AS roller, r.earnings AS kazanc LIMIT 50",
  "results": [["Keanu Reeves", ["Neo"], 40985512], ["Carrie-Anne Moss", ["Trinity"], 11013692]],
  "description": "Matrix filminde oynayan oyuncuların isimleri, rolleri ve kazançları."
}
```

## 📈 Performans Metrikleri

Gerçek kullanımdan elde edilen veriler:

- **Ortalama Yanıt Süresi**: 5-15 saniye (AI model gecikmeleri dahil)
- **Cache Hit Oranı**: %40-60 (tekrar sorularda)
- **Neo4j Sorgu Süresi**: <200ms
- **Başarılı Cypher Üretimi**: %85-90

## 🐛 Bilinen Sorunlar ve Çözümler

### ❌ Yaygın Hatalar

| Hata | Log Göstergesi | Çözüm |
|------|---------------|-------|
| Neo4j bağlantısı | `Failed to connect to Neo4j` | Neo4j servisini başlatın |
| Token limiti | `Rate limit hit` | Farklı API key kullanın |
| Yanlış schema | `Unknown label/property` | Cache temizleyin |
| JSON parse error | `JSON parse error` | Model değiştirin |

### 🔧 Debug Komutları

```bash
# Sağlık kontrolü
curl http://localhost:5000/api/health

# Cache temizleme
curl -X POST http://localhost:5000/api/clear-cache

# Log izleme
tail -f app.log | grep ERROR
```

## 🤝 Geliştirme

### 🛠️ Kod Yapısı

- **app.py** (917 satır): Ana uygulama mantığı
- **cache.py**: Hash tabanlı cache sistemi
- **history.py**: Konuşma geçmişi yönetimi
- **templates/index.html**: Modern web arayüzü

### 📝 Katkıda Bulunma

1. Fork edin
2. Feature branch oluşturun (`git checkout -b feature/amazing-feature`)
3. Commit edin (`git commit -m 'Add amazing feature'`)
4. Push edin (`git push origin feature/amazing-feature`)
5. Pull Request açın

## 📄 Lisans

Bu proje MIT Lisansı altında lisanslanmıştır.

## 🙏 Teşekkürler

- [Neo4j](https://neo4j.com/) - Graf veritabanı teknolojisi
- [OpenRouter](https://openrouter.ai/) - AI model API erişimi
- [Flask](https://flask.palletsprojects.com/) - Web framework
- [Google Gemma](https://ai.google.dev/gemma) - Güçlü dil modeli

---

<div align="center">

**⭐ Bu proje faydalı olduysa yıldız vermeyi unutmayın!**

Made with ❤️ using Neo4j + AI + Flask

</div>