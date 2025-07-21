import os
import logging
from flask import Flask, render_template, request, jsonify
from neo4j import GraphDatabase
from neo4j.exceptions import Neo4jError
import requests
import json
from dotenv import load_dotenv
from cache import get_from_cache, save_to_cache
from history import add_to_history, load_history

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', os.urandom(24))

# ======== Configuration ========
NEO4J_URI = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
NEO4J_USER = os.getenv('NEO4J_USER', 'neo4j')
NEO4J_PASS = os.getenv('NEO4J_PASSWORD')

GEMMA_MODEL = os.getenv('GEMMA_MODEL', 'google/gemma-3-27b-it:free')
OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY')

# Validate required environment variables
if not NEO4J_PASS:
    logger.error("NEO4J_PASSWORD environment variable is not set")
    raise ValueError("NEO4J_PASSWORD is required")

if not OPENROUTER_API_KEY:
    logger.error("OPENROUTER_API_KEY environment variable is not set")
    raise ValueError("OPENROUTER_API_KEY is required")

# ======== Neo4j Connection ========
try:
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
    driver.verify_connectivity()
    logger.info("Successfully connected to Neo4j")
    neo4j_available = True
except Exception as e:
    logger.error(f"Failed to connect to Neo4j: {str(e)}")
    logger.info("Running in fallback mode without Neo4j")
    neo4j_available = False
    driver = None

def query_neo4j(cypher_query):
    """Execute Neo4j query with error handling"""
    if not neo4j_available:
        logger.warning("Neo4j not available")
        return None
        
    def run_query(tx):
        try:
            result = tx.run(cypher_query)
            return [record.values() for record in result]
        except Neo4jError as e:
            logger.error(f"Neo4j query error: {str(e)}")
            raise
    
    try:
        with driver.session() as session:
            return session.execute_read(run_query)
    except Exception as e:
        logger.error(f"Failed to execute query: {cypher_query}")
        logger.error(f"Error: {str(e)}")
        return None

def validate_cypher_query(query):
    """Basic validation to prevent Cypher injection"""
    dangerous_keywords = ['DELETE', 'REMOVE', 'DROP', 'CREATE', 'MERGE', 'SET']
    query_upper = query.upper()
    
    for keyword in dangerous_keywords:
        if keyword in query_upper:
            logger.warning(f"Dangerous keyword '{keyword}' detected in query")
            return False
    
    return True

def ask_cypher_json(question):
    """Generate Cypher query from natural language question"""
    logger.info(f"Generating Cypher for question: {question}")
    
    # Check cache
    cache_key = f"cypher_{question}"
    cached = get_from_cache(cache_key)
    if cached:
        logger.info("Using cached Cypher query")
        return cached

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }

    schema = """
Database Schema:
(p:Person)-[:ACTED_IN]->(m:Movie)
(p:Person)-[:DIRECTED]->(m:Movie)
(m:Movie)-[:BELONGS_TO_GENRE]->(g:Genre)
(m:Movie)-[:PRODUCED_BY]->(c:Company)
(m:Movie)-[:PRODUCED_IN_COUNTRY]->(co:Country)
(m:Movie)-[:SPOKEN_IN_LANGUAGE]->(l:Language)

Properties:
- Movie: title, released, rating
- Person: name, birthdate
- Genre, Company, Country, Language: name
- ACTED_IN relationship: earnings (salary information)

IMPORTANT SYNTAX RULES:
- To access relationship properties, use: MATCH (p)-[r:ACTED_IN]->(m) RETURN r.earnings
- NEVER use: relationships.ACTED_IN.earnings or similar syntax
- Always define relationship variable (like 'r') to access its properties
"""

    prompt = f"""
Generate a JSON response for the user's question:

Format:
{{
  "cypher": "Neo4j Cypher query",
  "description": "Brief explanation in Turkish"
}}

CRITICAL SYNTAX RULES:
1. Return ONLY valid JSON
2. Query must be Neo4j 4.x compatible
3. Add LIMIT (maximum 50 results)
4. Only use READ operations (MATCH, RETURN)
5. Handle Turkish characters properly
6. For relationship properties: MATCH (p)-[r:ACTED_IN]->(m) RETURN r.propertyName
7. NEVER use: relationships.ACTED_IN.propertyName syntax
8. Always use relationship variables like 'r', 'rel', 'acted' etc.

Common movie titles in database:
- English: "The Da Vinci Code", "The Matrix", "Titanic"
- Turkish: Film names might be in Turkish or English

User question: "{question}"

Correct examples:
{{
  "cypher": "MATCH (p:Person)-[r:ACTED_IN]->(m:Movie) WHERE m.title = 'The Matrix' RETURN p.name, r.earnings LIMIT 10",
  "description": "Matrix filminde oynayan oyuncular ve maaşları"
}}

{{
  "cypher": "MATCH (p:Person)-[acted:ACTED_IN]->(m:Movie) WHERE m.title CONTAINS 'Da Vinci' RETURN p.name AS actor, acted.earnings AS salary LIMIT 20",
  "description": "Da Vinci filmlerindeki oyuncular ve kazançları"
}}
"""

    data = {
        "model": GEMMA_MODEL,
        "messages": [
            {
                "role": "system",
                "content": f"You are a Neo4j Cypher query expert. You MUST follow proper Neo4j syntax rules for relationship properties. Return only valid JSON.\n\nDatabase schema:\n{schema}"
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        "max_tokens": 1000,
        "temperature": 0.1  # Lower temperature for more consistent syntax
    }

    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions", 
            json=data, 
            headers=headers,
            timeout=30
        )
        response.raise_for_status()
        
        result = response.json()
        
        if "choices" not in result:
            logger.error(f"Invalid LLM response: {result}")
            return None

        raw = result["choices"][0]["message"]["content"]
        logger.debug(f"LLM raw response: {raw}")

        # Extract JSON
        import re
        json_match = re.search(r'\{.*\}', raw, re.DOTALL)
        if not json_match:
            logger.error("No JSON block found in response")
            return None

        json_data = json.loads(json_match.group(0))
        
        # Validate required fields
        if "cypher" not in json_data:
            logger.error("Missing 'cypher' field in JSON")
            return None

        # Fix common syntax errors
        cypher_query = json_data["cypher"]
        
        # Fix relationship property access syntax
        if "relationships." in cypher_query:
            logger.warning("Fixing incorrect relationship syntax")
            # This is a basic fix - you might need more sophisticated parsing
            cypher_query = cypher_query.replace("relationships.ACTED_IN.earnings", "r.earnings")
            cypher_query = cypher_query.replace("relationships.DIRECTED.", "r.")
            json_data["cypher"] = cypher_query

        # Validate Cypher query
        if not validate_cypher_query(json_data["cypher"]):
            logger.error("Query validation failed")
            return None

        # Save to cache
        save_to_cache(cache_key, json_data)
        logger.info(f"Successfully generated and cached Cypher query: {json_data['cypher']}")
        return json_data

    except requests.RequestException as e:
        logger.error(f"Request error: {str(e)}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"JSON parse error: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error in ask_cypher_json: {str(e)}")
        return None

def ask_gemma(question, cypher_results):
    """Get natural language answer from Gemma"""
    logger.info(f"Generating answer for question: {question}")
    
    # Check cache
    cache_key = f"answer_{question}_{str(cypher_results)}"
    cached = get_from_cache(cache_key)
    if cached:
        logger.info("Using cached answer")
        return cached

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }

    # Get history
    history = load_history()
    
    # Create history prompt
    history_prompt = ""
    for h in history[-3:]:  # Last 3 conversations
        if h.get("question") and h.get("answer"):
            history_prompt += f"User: {h['question']}\nAssistant: {h['answer']}\n\n"

    # Format results
    formatted_results = ""
    if cypher_results:
        formatted_results = f"Database results: {cypher_results}"
    else:
        formatted_results = "No results found in database."

    prompt = f"""Previous conversations:
{history_prompt}

Current question: {question}
{formatted_results}

Please provide a warm, friendly, and informative answer in Turkish. Use emojis sparingly."""

    data = {
        "model": GEMMA_MODEL,
        "messages": [
            {
                "role": "system",
                "content": """You are a warm, helpful movie database assistant. 
Answer user questions in Turkish in a friendly and explanatory manner.
- Give short and clear answers
- Use emojis sparingly
- Interpret database results meaningfully
- Suggest alternatives if no data is available"""
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
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions", 
            json=data, 
            headers=headers,
            timeout=30
        )
        response.raise_for_status()
        
        result = response.json()
        
        if "choices" not in result:
            logger.error(f"Invalid Gemma response: {result}")
            return "Üzgünüm, cevap üretilemedi."

        answer = result["choices"][0]["message"]["content"]
        
        # Save to cache
        save_to_cache(cache_key, answer)
        logger.info("Successfully generated and cached answer")
        
        return answer

    except requests.RequestException as e:
        logger.error(f"Request error in ask_gemma: {str(e)}")
        return "Üzgünüm, bir bağlantı hatası oluştu."
    except Exception as e:
        logger.error(f"Unexpected error in ask_gemma: {str(e)}")
        return "Üzgünüm, cevap üretilemedi."

@app.route("/", methods=["GET", "POST"])
def index():
    """Main route handler"""
    return render_template("index.html")

@app.route("/api/ask", methods=["POST"])
def api_ask():
    """API endpoint for questions"""
    try:
        data = request.get_json()
        question = data.get("question", "").strip()
        
        if not question:
            return jsonify({"error": "Lütfen bir soru yazın."}), 400

        logger.info(f"Received question: {question}")

        # Check if Neo4j is available
        if not neo4j_available:
            answer = "Üzgünüm, veritabanı bağlantısı mevcut değil. Lütfen Neo4j servisinin çalıştığından emin olun."
            return jsonify({"answer": answer, "cypher": None, "error": "Neo4j unavailable"})

        # 1. Generate Cypher query
        json_data = ask_cypher_json(question)
        if not json_data or "cypher" not in json_data:
            answer = "Üzgünüm, sorunuzu anlayamadım. Lütfen farklı bir şekilde sormayı deneyin."
            add_to_history(question, answer)
            return jsonify({"answer": answer, "cypher": None})

        cypher_query = json_data["cypher"]
        logger.info(f"Generated Cypher: {cypher_query}")

        # 2. Execute query on Neo4j
        results = query_neo4j(cypher_query)
        logger.info(f"Query results: {results}")

        # 3. Get natural language answer from Gemma
        answer = ask_gemma(question, results)
        
        # 4. Add to history
        add_to_history(question, answer)
        
        return jsonify({
            "answer": answer,
            "cypher": cypher_query,
            "results": results
        })

    except Exception as e:
        logger.error(f"Error in api_ask: {str(e)}")
        return jsonify({"error": "Bir hata oluştu. Lütfen tekrar deneyin."}), 500

@app.route("/api/history", methods=["GET"])
def api_history():
    """Get conversation history"""
    try:
        history = load_history()
        return jsonify({"history": history})
    except Exception as e:
        logger.error(f"Error loading history: {str(e)}")
        return jsonify({"error": "Geçmiş yüklenemedi."}), 500

@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Sayfa bulunamadı"}), 404

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Internal error: {str(error)}")
    return jsonify({"error": "Sunucu hatası"}), 500

if __name__ == "__main__":
    # Get configuration from environment
    debug = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    host = os.getenv('FLASK_HOST', '0.0.0.0')
    port = int(os.getenv('FLASK_PORT', 5000))
    
    logger.info(f"Starting Flask app on {host}:{port} (debug={debug})")
    app.run(debug=debug, host=host, port=port)