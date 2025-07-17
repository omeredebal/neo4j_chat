from neo4j import GraphDatabase
# Neo4j bağlantı bilgileri
uri = "bolt://localhost:7687"
username = "neo4j"              # kendi kullanıcı adını yaz
password = "Omer1642"  # Neo4j Browser'da girişte kullandığın şifre
# Sürücü oluştur
driver = GraphDatabase.driver(uri, auth=(username, password))
def run_query(tx):
    result = tx.run("MATCH (p:Person)-[r:ACTED_IN]->(m:Movie) RETURN p.name AS actor, m.title AS movie LIMIT 5")
    return result.data()

with driver.session() as session:
    results = session.read_transaction(run_query)
    for row in results:
        print(f"{row['actor']} acted in {row['movie']}")

driver.close()
