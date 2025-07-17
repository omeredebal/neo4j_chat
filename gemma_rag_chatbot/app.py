from flask import Flask, render_template, request
from neo4j import GraphDatabase
import requests

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
    def run_query(tx):
        result = tx.run(cypher_query)
        return [record.values() for record in result]
    with driver.session() as session:
        return session.execute_read(run_query)

def ask_cypher(question):
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }

    prompt = f"""
Sen bir Neo4j veritabanı asistanısın. Aşağıdaki kullanıcı sorusuna SADECE geçerli bir Cypher sorgusu üret.

LÜTFEN DİKKAT:
- ACTED_IN ilişkisi (p:Person)-[:ACTED_IN]->(m:Movie) şeklindedir.
- Sadece geçerli Cypher döndür. Açıklama, ``` işareti veya kod bloğu yazma.

Soru:
"{question}"
"""

    data = {
        "model": GEMMA_MODEL,
        "messages": [
            {"role": "system", "content": "Kullanıcının sorusuna uygun Neo4j Cypher sorgusu üret."},
            {"role": "user", "content": prompt}
        ]
    }

    try:
        response = requests.post("https://openrouter.ai/api/v1/chat/completions", json=data, headers=headers)
        cypher = response.json().get("choices", [{}])[0].get("message", {}).get("content", "")
        cypher = cypher.replace("```cypher", "").replace("```", "").strip()
        print("✅ Üretilen Cypher:\n", cypher)
        return cypher
    except Exception as e:
        print("❌ Cypher oluşturulamadı:", str(e))
        return None


def ask_gemma(question, context):
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }

    prompt = f"""
Soru: {question}
Veritabanından gelen bilgiler: {context}

Yukarıdaki bilgilere göre kullanıcıya doğal dilde kısa ve açıklayıcı bir cevap ver.
"""

    data = {
        "model": GEMMA_MODEL,
        "messages": [
            {"role": "system", "content": "Kullanıcının sorusuna Neo4j veritabanındaki bilgilerle açıklayıcı cevap ver."},
            {"role": "user", "content": prompt}
        ]
    }

    try:
        response = requests.post("https://openrouter.ai/api/v1/chat/completions", json=data, headers=headers)
        return response.json()["choices"][0]["message"]["content"]
    except Exception as e:
        print("❌ Doğal dil yanıtı alınamadı:", str(e))
        print("📦 Dönen veri:", response.text)
        return "Cevap üretilemedi."

@app.route("/", methods=["GET", "POST"])
def index():
    answer = ""
    if request.method == "POST":
        question = request.form["question"]

        cypher = ask_cypher(question)
        if not cypher:
            answer = "Cypher sorgusu üretilemedi. Lütfen daha net bir soru sorun."
            return render_template("index.html", answer=answer)

        print("✅ Üretilen Cypher:", cypher)

        try:
            results = query_neo4j(cypher)
            if results:
                context = ", ".join(str(row[0]) for row in results)
                answer = ask_gemma(question, context)
            else:
                answer = "Veritabanında bu soruya karşılık gelen bir bilgi bulunamadı."
        except Exception as e:
            print("❌ Neo4j sorgu hatası:", str(e))
            answer = f"Neo4j sorgusu başarısız oldu: {str(e)}"

    return render_template("index.html", answer=answer)

if __name__ == "__main__":
    app.run(debug=True)
