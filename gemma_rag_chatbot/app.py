import os
import logging
import sys
import re
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

# Configure logging with better formatting
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
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

# Model alternatives for failover
FALLBACK_MODELS = [
    'google/gemma-3-27b-it:free',
    'meta-llama/llama-3.1-8b-instruct:free',
    'microsoft/phi-3-mini-128k-instruct:free'
]

# Validate required environment variables
if not NEO4J_PASS:
    logger.error("NEO4J_PASSWORD environment variable is not set")
    raise ValueError("NEO4J_PASSWORD is required")

if not OPENROUTER_API_KEY:
    logger.error("OPENROUTER_API_KEY environment variable is not set")
    raise ValueError("OPENROUTER_API_KEY is required")

# ======== Neo4j Connection ========
neo4j_available = False
driver = None

def initialize_neo4j():
    """Initialize Neo4j connection with retry logic"""
    global neo4j_available, driver
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
            driver.verify_connectivity()
            neo4j_available = True
            logger.info(f"Successfully connected to Neo4j (attempt {attempt + 1})")
            return True
        except Exception as e:
            logger.warning(f"Neo4j connection attempt {attempt + 1} failed: {str(e)}")
            if attempt == max_retries - 1:
                logger.error("Failed to connect to Neo4j after all retries")
                neo4j_available = False
                return False
    return False

# Initialize connection
initialize_neo4j()

def query_neo4j(cypher_query):
    """Execute Neo4j query with enhanced error handling"""
    if not neo4j_available:
        logger.warning("Neo4j not available")
        return None
    
    # Clean the query
    cypher_query = cypher_query.strip()
    if not cypher_query:
        logger.error("Empty Cypher query")
        return None
        
    def run_query(tx):
        try:
            result = tx.run(cypher_query)
            records = []
            for record in result:
                # Convert Neo4j types to Python types
                values = []
                for value in record.values():
                    if hasattr(value, 'value'):  # Neo4j datetime/date objects
                        values.append(value.value)
                    else:
                        values.append(value)
                records.append(values)
            return records
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
    """Enhanced validation to prevent Cypher injection"""
    if not query or not isinstance(query, str):
        return False
    
    # Dangerous keywords
    dangerous_keywords = [
        'DELETE', 'REMOVE', 'DROP', 'CREATE', 'MERGE', 'SET', 
        'DETACH', 'CALL', 'LOAD', 'FOREACH', 'WITH'
    ]
    
    query_upper = query.upper()
    
    for keyword in dangerous_keywords:
        if f' {keyword} ' in f' {query_upper} ':
            logger.warning(f"Dangerous keyword '{keyword}' detected in query")
            return False
    
    # Check for basic structure
    if not query_upper.startswith('MATCH'):
        logger.warning("Query must start with MATCH")
        return False
        
    if 'RETURN' not in query_upper:
        logger.warning("Query must contain RETURN")
        return False
    
    return True

def fix_advanced_cypher_syntax(cypher_query):
    """Advanced Cypher syntax fixing based on real schema"""
    if not cypher_query:
        return cypher_query
    
    # Fix wrong relationship property access
    fixes = [
        # Main problem fixes
        (r'relationships\.ACTED_IN\.earnings', 'r.earnings'),
        (r'relationships\.ACTED_IN\.roles', 'r.roles'),
        (r'relationships\.DIRECTED\.', 'r.'),
        (r'relationships\.(\w+)\.(\w+)', r'r.\2'),
        
        # Property name fixes
        (r'\.birthdate\b', '.born'),
        (r'\.year\b', '.released'),
        (r'\.salary\b', '.earnings'),
        
        # Ensure relationship variables exist
        (r'-\[:ACTED_IN\]->', '-[r:ACTED_IN]->'),
        (r'-\[:HAS_CONTACT\]-', '-[:HAS_CONTACT]-'),
    ]
    
    for pattern, replacement in fixes:
        cypher_query = re.sub(pattern, replacement, cypher_query, flags=re.IGNORECASE)
    
    # Ensure relationship variable is defined when accessing properties
    if 'r.earnings' in cypher_query or 'r.roles' in cypher_query:
        if '-[:ACTED_IN]->' in cypher_query and '-[r:ACTED_IN]->' not in cypher_query:
            cypher_query = cypher_query.replace('-[:ACTED_IN]->', '-[r:ACTED_IN]->')
    
    return cypher_query

def ask_cypher_json(question, model_index=0):
    """Generate Cypher query from natural language question - UPDATED FOR REAL SCHEMA"""
    logger.info(f"Generating Cypher for question: {question}")
    
    # Check cache first
    cache_key = f"cypher_{question}"
    cached = get_from_cache(cache_key)
    if cached:
        logger.info("Using cached Cypher query")
        return cached

    if model_index >= len(FALLBACK_MODELS):
        logger.error("All models failed")
        return None
    
    current_model = FALLBACK_MODELS[model_index]
    
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }

    # GERÇEK SCHEMA'YA GÖRE GÜNCELLENDİ
    schema = """
ACTUAL DATABASE SCHEMA (based on JSON analysis):

Nodes:
- (p:Person) 
  Properties: name (string), born (integer, optional)
  
- (m:Movie) 
  Properties: title (string), released (integer), tagline (string, optional)

Relationships:
- (p:Person)-[r:ACTED_IN]->(m:Movie)
  Properties: r.earnings (integer), r.roles (array of strings)
  
- (p1:Person)-[:HAS_CONTACT]-(p2:Person)
  Properties: none (social network connections)

CRITICAL SYNTAX RULES:
1. ALWAYS use relationship variables: MATCH (p)-[r:ACTED_IN]->(m)
2. Access relationship properties as: r.earnings, r.roles
3. NEVER use: relationships.ACTED_IN.earnings (THIS IS WRONG!)
4. Person birth year: p.born (not p.birthdate)
5. Movie release year: m.released (not m.year)
6. Actor roles: r.roles (array)
7. Actor earnings/salary: r.earnings

SAMPLE CORRECT QUERIES:
- MATCH (p:Person)-[r:ACTED_IN]->(m:Movie) WHERE p.name = 'Keanu Reeves' RETURN p.name, m.title, r.earnings, r.roles
- MATCH (p:Person)-[r:ACTED_IN]->(m:Movie) WHERE m.title CONTAINS 'Matrix' RETURN p.name, r.earnings ORDER BY r.earnings DESC
- MATCH (p:Person) WHERE p.born > 1960 RETURN p.name, p.born ORDER BY p.born
"""

    prompt = f"""
Generate a JSON response for the user's question using the EXACT schema provided above.

MANDATORY FORMAT:
{{
  "cypher": "Neo4j Cypher query using correct schema",
  "description": "Brief explanation in Turkish"
}}

SCHEMA ENFORCEMENT RULES:
1. Person properties: name, born (not birthdate!)
2. Movie properties: title, released (not year!), tagline  
3. ACTED_IN relationship: earnings, roles (array)
4. Use relationship variables: [r:ACTED_IN], [acted:ACTED_IN], [role:ACTED_IN]
5. NEVER use: relationships.ACTED_IN.earnings
6. ALWAYS use: r.earnings, r.roles
7. Add LIMIT (max 50)
8. Only READ operations

COMMON MOVIE TITLES IN DATABASE:
"The Matrix", "The Matrix Reloaded", "The Matrix Revolutions", "The Devil's Advocate", 
"The Replacements", "Johnny Mnemonic", "Something's Gotta Give", "Cloud Atlas"

COMMON ACTORS:
"Keanu Reeves", "Carrie-Anne Moss", "Laurence Fishburne", "Hugo Weaving"

User question: "{question}"

CORRECT EXAMPLES:
{{
  "cypher": "MATCH (p:Person)-[r:ACTED_IN]->(m:Movie) WHERE p.name = 'Keanu Reeves' RETURN m.title AS film, r.earnings AS maas, r.roles AS roller ORDER BY r.earnings DESC LIMIT 10",
  "description": "Keanu Reeves'un oynadığı filmler, maaşları ve rolleri (yüksekten düşüğe)"
}}

{{
  "cypher": "MATCH (p:Person)-[r:ACTED_IN]->(m:Movie) WHERE m.title CONTAINS 'Matrix' RETURN p.name AS oyuncu, r.earnings AS maas, r.roles AS rol ORDER BY r.earnings DESC LIMIT 20",
  "description": "Matrix filmlerindeki oyuncular ve kazançları"
}}

{{
  "cypher": "MATCH (p:Person)-[r:ACTED_IN]->(m:Movie) WHERE m.released > 2000 RETURN m.title AS film, m.released AS yil, count(p) AS oyuncu_sayisi ORDER BY m.released DESC LIMIT 15",
  "description": "2000 sonrası filmler ve oyuncu sayıları"
}}
"""

    data = {
        "model": current_model,
        "messages": [
            {
                "role": "system",
                "content": f"You are a Neo4j Cypher expert. Use ONLY the provided schema. NEVER use relationships.ACTED_IN.earnings syntax. ALWAYS use relationship variables like r.earnings. Return only valid JSON.\n\nSchema:\n{schema}"
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        "max_tokens": 1000,
        "temperature": 0.05,  # Very low for consistent syntax
        "top_p": 0.9,
        "stop": ["}}", "}\n\n"]
    }

    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions", 
            json=data, 
            headers=headers,
            timeout=30
        )
        
        if response.status_code == 429:
            logger.warning(f"Rate limit hit for model {current_model}, trying next model")
            return ask_cypher_json(question, model_index + 1)
        
        response.raise_for_status()
        result = response.json()
        
        if "choices" not in result or not result["choices"]:
            logger.error(f"Invalid response from {current_model}")
            return ask_cypher_json(question, model_index + 1)

        raw_content = result["choices"][0]["message"]["content"]
        logger.debug(f"Raw response from {current_model}: {raw_content}")

        # Extract JSON with better parsing
        json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', raw_content, re.DOTALL)
        if not json_match:
            logger.error("No valid JSON found in response")
            return ask_cypher_json(question, model_index + 1)

        try:
            json_data = json.loads(json_match.group(0))
        except json.JSONDecodeError:
            # Try to fix common JSON issues
            json_str = json_match.group(0)
            json_str = re.sub(r',\s*}', '}', json_str)  # Remove trailing commas
            json_str = re.sub(r',\s*]', ']', json_str)
            try:
                json_data = json.loads(json_str)
            except json.JSONDecodeError as e:
                logger.error(f"JSON parse error after fixes: {e}")
                return ask_cypher_json(question, model_index + 1)
        
        if "cypher" not in json_data:
            logger.error("Missing 'cypher' field in response")
            return ask_cypher_json(question, model_index + 1)

        # ADVANCED SYNTAX FIXING
        cypher_query = fix_advanced_cypher_syntax(json_data["cypher"])
        json_data["cypher"] = cypher_query

        # Validate Cypher query
        if not validate_cypher_query(cypher_query):
            logger.error("Query validation failed")
            return ask_cypher_json(question, model_index + 1)

        # Cache and return
        save_to_cache(cache_key, json_data)
        logger.info(f"Successfully generated Cypher with {current_model}: {cypher_query}")
        return json_data

    except requests.RequestException as e:
        logger.error(f"Request error with {current_model}: {str(e)}")
        return ask_cypher_json(question, model_index + 1)
    except Exception as e:
        logger.error(f"Unexpected error with {current_model}: {str(e)}")
        return ask_cypher_json(question, model_index + 1)

def ask_gemma(question, cypher_results, model_index=0):
    """Generate natural language answer with fallback models"""
    logger.info(f"Generating answer for question: {question}")
    
    # Check cache
    cache_key = f"answer_{question}_{str(cypher_results)}"
    cached = get_from_cache(cache_key)
    if cached:
        logger.info("Using cached answer")
        return cached

    if model_index >= len(FALLBACK_MODELS):
        return "Üzgünüm, cevap üretilemedi. Lütfen daha sonra tekrar deneyin."
    
    current_model = FALLBACK_MODELS[model_index]

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }

    # Format results better
    formatted_results = "Veri bulunamadı."
    if cypher_results:
        if len(cypher_results) == 1 and len(cypher_results[0]) == 1:
            formatted_results = f"Sonuç: {cypher_results[0][0]}"
        elif len(cypher_results) <= 10:
            formatted_results = f"Sonuçlar: {cypher_results}"
        else:
            formatted_results = f"Toplam {len(cypher_results)} sonuç bulundu. İlk 10 tanesi: {cypher_results[:10]}"

    # Get relevant history
    history = load_history()
    history_context = ""
    if history:
        for h in history[-2:]:  # Last 2 conversations
            if h.get("question") and h.get("answer"):
                history_context += f"Önceki soru: {h['question']}\nÖnceki cevap: {h['answer'][:100]}...\n\n"

    prompt = f"""Önceki konuşmalar:
{history_context}

Mevcut soru: {question}
Veritabanı sonuçları: {formatted_results}

Lütfen Türkçe olarak samimi, yardımsever ve bilgilendirici bir cevap verin:
- Kısa ve net olun
- Sayıları güzel formatlayın (örn: 1.558.255 → 1,558,255)
- Emoji çok az kullanın
- Eğer veri yoksa alternatif öneriler sunun
- Film adlarını hem İngilizce hem Türkçe belirtin"""

    data = {
        "model": current_model,
        "messages": [
            {
                "role": "system",
                "content": """Sen yardımsever bir film veritabanı asistanısın. Türkçe cevaplar veriyorsun.
- Kısa ve anlaşılır ol
- Sayıları güzel formatla
- Emoji az kullan
- Veri yoksa alternatif öner"""
            },
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 1000,
        "temperature": 0.7
    }

    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions", 
            json=data, 
            headers=headers,
            timeout=30
        )
        
        if response.status_code == 429:
            logger.warning(f"Rate limit hit for answer generation with {current_model}")
            return ask_gemma(question, cypher_results, model_index + 1)
        
        response.raise_for_status()
        result = response.json()
        
        if "choices" not in result or not result["choices"]:
            logger.error(f"Invalid response from {current_model}")
            return ask_gemma(question, cypher_results, model_index + 1)

        answer = result["choices"][0]["message"]["content"].strip()
        
        # Post-process answer
        answer = re.sub(r'\n\n+', '\n\n', answer)  # Remove excessive newlines
        answer = answer.replace('$', ' $')  # Better dollar formatting
        
        save_to_cache(cache_key, answer)
        logger.info(f"Successfully generated answer with {current_model}")
        return answer

    except requests.RequestException as e:
        logger.error(f"Request error in answer generation with {current_model}: {str(e)}")
        return ask_gemma(question, cypher_results, model_index + 1)
    except Exception as e:
        logger.error(f"Unexpected error in answer generation with {current_model}: {str(e)}")
        return ask_gemma(question, cypher_results, model_index + 1)

@app.route("/", methods=["GET"])
def index():
    """Main route handler"""
    return render_template("index.html")

@app.route("/api/ask", methods=["POST"])
def api_ask():
    """Enhanced API endpoint for questions"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "JSON verisi gerekli"}), 400
            
        question = data.get("question", "").strip()
        
        if not question:
            return jsonify({"error": "Lütfen bir soru yazın"}), 400
            
        if len(question) > 500:
            return jsonify({"error": "Soru çok uzun (maksimum 500 karakter)"}), 400

        logger.info(f"Received question: {question}")

        # Check Neo4j availability
        if not neo4j_available:
            # Try to reconnect
            if not initialize_neo4j():
                answer = "Üzgünüm, veritabanı bağlantısı mevcut değil. Lütfen Neo4j servisinin çalıştığından emin olun ve tekrar deneyin."
                return jsonify({
                    "answer": answer, 
                    "cypher": None, 
                    "error": "Neo4j unavailable",
                    "results": None
                })

        # Generate Cypher query
        json_data = ask_cypher_json(question)
        if not json_data or "cypher" not in json_data:
            answer = "Üzgünüm, sorunuzu anlayamadım. Lütfen farklı bir şekilde sormayı deneyin veya daha spesifik olun."
            add_to_history(question, answer)
            return jsonify({"answer": answer, "cypher": None, "results": None})

        cypher_query = json_data["cypher"]
        logger.info(f"Generated Cypher: {cypher_query}")

        # Execute query
        results = query_neo4j(cypher_query)
        logger.info(f"Query results: {len(results) if results else 0} rows")

        # Generate natural language answer
        answer = ask_gemma(question, results)
        
        # Add to history
        add_to_history(question, answer)
        
        return jsonify({
            "answer": answer,
            "cypher": cypher_query,
            "results": results,
            "description": json_data.get("description", "")
        })

    except Exception as e:
        logger.error(f"Error in api_ask: {str(e)}", exc_info=True)
        return jsonify({"error": "Bir hata oluştu. Lütfen tekrar deneyin"}), 500

@app.route("/api/history", methods=["GET"])
def api_history():
    """Get conversation history"""
    try:
        history = load_history()
        return jsonify({"history": history[-10:]})  # Last 10 conversations
    except Exception as e:
        logger.error(f"Error loading history: {str(e)}")
        return jsonify({"error": "Geçmiş yüklenemedi"}), 500

@app.route("/api/clear-cache", methods=["POST"])
def api_clear_cache():
    """Clear cache endpoint"""
    try:
        from cache import clear_cache
        clear_cache()
        return jsonify({"message": "Cache temizlendi"})
    except Exception as e:
        logger.error(f"Error clearing cache: {str(e)}")
        return jsonify({"error": "Cache temizlenemedi"}), 500

@app.route("/api/health", methods=["GET"])
def api_health():
    """Health check endpoint"""
    health_status = {
        "status": "healthy",
        "neo4j": neo4j_available,
        "timestamp": os.getenv('TIMESTAMP', 'unknown')
    }
    
    if neo4j_available:
        try:
            # Test query
            test_result = query_neo4j("MATCH (n) RETURN count(n) AS total LIMIT 1")
            health_status["neo4j_test"] = "success"
            health_status["total_nodes"] = test_result[0][0] if test_result else 0
        except Exception as e:
            health_status["neo4j_test"] = f"failed: {str(e)}"
    
    return jsonify(health_status)

@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Sayfa bulunamadı"}), 404

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Internal error: {str(error)}")
    return jsonify({"error": "Sunucu hatası"}), 500

@app.errorhandler(429)
def rate_limit_error(error):
    return jsonify({"error": "Çok fazla istek. Lütfen biraz bekleyin"}), 429

if __name__ == "__main__":
    # Get configuration from environment
    debug = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    host = os.getenv('FLASK_HOST', '0.0.0.0')
    port = int(os.getenv('FLASK_PORT', 5000))
    
    logger.info(f"Starting Flask app on {host}:{port} (debug={debug})")
    logger.info(f"Neo4j available: {neo4j_available}")
    logger.info(f"Using models: {FALLBACK_MODELS}")
    
    app.run(debug=debug, host=host, port=port)