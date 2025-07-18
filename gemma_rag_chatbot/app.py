from flask import Flask, render_template, request
from neo4j import GraphDatabase
import requests
import json
from cache import get_from_cache, save_to_cache
from history import add_to_history, load_history

app = Flask(__name__)

# ======== Ayarlar ========
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASS = "Omer1642"

GEMMA_MODEL = "google/gemma-3-27b-it:free"
OPENROUTER_API_KEY = "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"

# ======== Neo4j Bağlantısı ========
driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))

def query_neo4j(cypher_query):
    """Neo4j sorgusu çalıştır"""
    def run_query(tx):
        result = tx.run(cypher_query)
        return [record.values() for record in result]
    
    try:
        with driver.session() as session:
            return session.execute_read(run_query)
    except Exception as e:
        print(f"❌ Neo4j sorgu hatası: {str(e)}")
        return None

def ask_cypher_json(question):
    """Cypher sorgusu üret"""
    # Cache kontrolü
    cache_key = f"cypher_{question}"
    cached = get_from_cache(cache_key)
    if cached:
        return cached

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }

    schema = """
Veritabanı yapısı:
(p:Person)-[:ACTED_IN]->(m:Movie)
(p:Person)-[:DIRECTED]->(m:Movie)
(m:Movie)-[:BELONGS_TO_GENRE]->(g:Genre)
(m:Movie)-[:PRODUCED_BY]->(c:Company)
(m:Movie)-[:PRODUCED_IN_COUNTRY]->(co:Country)
(m:Movie)-[:SPOKEN_IN_LANGUAGE]->(l:Language)

Özellikler:
- Movie: title, released, rating
- Person: name, birthdate
- Genre, Company, Country, Language: name
"""

    prompt = f"""
Kullanıcının sorusuna göre bir JSON cevabı üret:

Format:
{{
  "cypher": "NEO4J Cypher sorgusu",
  "description": "Sorgunun ne yaptığına dair kısa açıklama"
}}

Önemli kurallar:
1. SADECE geçerli JSON döndür
2. Cypher sorgusu Neo4j 4.x uyumlu olmalı
3. Türkçe karakter sorunu olmasın
4. LIMIT ekle (maksimum 50 sonuç)

Kullanıcı sorusu: "{question}"

Örnek:
{{
  "cypher": "MATCH (p:Person)-[:ACTED_IN]->(m:Movie) WHERE m.title CONTAINS 'Matrix' RETURN p.name LIMIT 10",
  "description": "Matrix filminde oynayan oyuncuları bul"
}}
"""

    data = {
        "model": GEMMA_MODEL,
        "messages": [
            {
                "role": "system",
                "content": f"Sen bir Neo4j Cypher sorgu uzmanısın. Sadece geçerli JSON döndür.\n\nVeritabanı şeması:\n{schema}"
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        "max_tokens": 1000,
        "temperature": 0.3
    }

    try:
        response = requests.post("https://openrouter.ai/api/v1/chat/completions", json=data, headers=headers)
        result = response.json()
        
        if "choices" not in result:
            print("❌ LLM cevabında 'choices' yok:", result)
            return None

        raw = result["choices"][0]["message"]["content"]
        print(f"🔍 LLM ham cevap: {raw}")

        # JSON'ı çıkar
        import re
        json_match = re.search(r'\{.*\}', raw, re.DOTALL)
        if not json_match:
            print("❌ JSON bloğu bulunamadı")
            return None

        json_data = json.loads(json_match.group(0))
        
        # Gerekli alanları kontrol et
        if "cypher" not in json_data:
            print("❌ JSON'da cypher alanı yok")
            return None

        # Cache'e kaydet
        save_to_cache(cache_key, json_data)
        return json_data

    except Exception as e:
        print(f"❌ Cypher JSON parse hatası: {str(e)}")
        return None

def ask_gemma(question, cypher_results):
    """Gemma'dan doğal dil cevabı al"""
    # Cache kontrolü
    cache_key = f"answer_{question}_{str(cypher_results)}"
    cached = get_from_cache(cache_key)
    if cached:
        return cached

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }

    # Geçmişi al
    history = load_history()
    
    # Geçmiş prompt'u oluştur
    history_prompt = ""
    for h in history[-3:]:  # Son 3 konuşma
        if h.get("question") and h.get("answer"):
            history_prompt += f"Kullanıcı: {h['question']}\nAsistan: {h['answer']}\n\n"

    # Veri formatını düzenle
    formatted_results = ""
    if cypher_results:
        formatted_results = f"Veritabanı sonuçları: {cypher_results}"
    else:
        formatted_results = "Veritabanında sonuç bulunamadı."

    prompt = f"""Önceki konuşmalar:
{history_prompt}

Şu anki soru: {question}
{formatted_results}

Lütfen bu bilgileri kullanarak sıcak, dostça ve bilgilendirici bir Türkçe cevap ver. Gerekirse emoji kullanabilirsin ama abartma."""

    data = {
        "model": GEMMA_MODEL,
        "messages": [
            {
                "role": "system",
                "content": """Sen sıcak, yardımsever bir film veritabanı asistanısın. 
Kullanıcının sorularını samimi ve açıklayıcı şekilde Türkçe yanıtla.
- Kısa ve net cevaplar ver
- Gerekirse emoji kullan ama abartma
- Veritabanı sonuçlarını anlamlı şekilde yorumla
- Veri yoksa alternatif öneriler sun"""
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        "max_tokens": 1500,
        "temperature": 0.7
    }

    try:
        response = requests.post("https://openrouter.ai/api/v1/chat/completions", json=data, headers=headers)
        result = response.json()
        
        if "choices" not in result:
            print("❌ Gemma cevabında 'choices' yok:", result)
            return "Üzgünüm, cevap üretilemedi."

        answer = result["choices"][0]["message"]["content"]
        
        # Cache'e kaydet
        save_to_cache(cache_key, answer)
        
        return answer

    except Exception as e:
        print(f"❌ Gemma cevap hatası: {str(e)}")
        return "Üzgünüm, cevap üretilemedi."

@app.route("/", methods=["GET", "POST"])
def index():
    answer = ""
    
    if request.method == "POST":
        question = request.form.get("question", "").strip()
        
        if not question:
            answer = "Lütfen bir soru yazın."
            return render_template("index.html", answer=answer)

        print(f"📝 Soru: {question}")

        # 1. Cypher sorgusu üret
        json_data = ask_cypher_json(question)
        if not json_data or "cypher" not in json_data:
            answer = "Üzgünüm, sorunuzu anlayamadım. Lütfen farklı bir şekilde sormayı deneyin."
            add_to_history(question, answer)
            return render_template("index.html", answer=answer)

        cypher_query = json_data["cypher"]
        print(f"🔍 Cypher: {cypher_query}")

        # 2. Neo4j'de sorguyu çalıştır
        results = query_neo4j(cypher_query)
        print(f"📊 Sonuçlar: {results}")

        # 3. Gemma'dan doğal cevap al
        answer = ask_gemma(question, results)
        
        # 4. Geçmişe ekle
        add_to_history(question, answer)
        
        print(f"💬 Cevap: {answer}")

    return render_template("index.html", answer=answer)

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)