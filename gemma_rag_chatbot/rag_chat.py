import requests
from neo4j import GraphDatabase

# ==== 1. Ayarlar ====
# Neo4j bilgileri
uri = "bolt://localhost:7687"
username = "neo4j"
password = "Omer1642"

# OpenRouter API anahtarı
openrouter_api_key = "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"
gemma_model = "google/gemma-3-27b-it:free"

# ==== 2. Soruyu al ve Cypher sorgusu oluştur (şimdilik sabit) ====
user_question = "The Matrix filminde kimler oynamıştır?"

cypher_query = """
MATCH (p:Person)-[:ACTED_IN]->(m:Movie {title: "The Matrix"})
RETURN p.name AS actor
"""

# ==== 3. Neo4j'den veriyi çek ====
driver = GraphDatabase.driver(uri, auth=(username, password))

def run_query(tx):
    result = tx.run(cypher_query)
    return [record["actor"] for record in result]

with driver.session() as session:
    actors = session.execute_read(run_query)

driver.close()

# ==== 4. Gemma’ya istek gönder ====
context = ", ".join(actors)
prompt = f"{user_question}\n\nBu filmde oynayan oyuncular: {context}\n\nBuna göre bana doğal dilde yanıt ver."

headers = {
    "Authorization": f"Bearer {openrouter_api_key}",
    "Content-Type": "application/json"
}

data = {
    "model": gemma_model,
    "messages": [
        {"role": "system", "content": "Sen Neo4j veritabanından alınan bilgileri açıklayan bir asistansın."},
        {"role": "user", "content": prompt}
    ]
}

response = requests.post("https://openrouter.ai/api/v1/chat/completions", json=data, headers=headers)

try:
    answer = response.json()['choices'][0]['message']['content']
    print(">>> RAG Cevabı:")
    print(answer)
except Exception:
    print(">>> HATA:")
    print(response.text)
