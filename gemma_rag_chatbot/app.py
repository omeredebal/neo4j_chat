import os
import logging
import sys
import re
from datetime import datetime
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

def detect_live_schema():
    """Neo4j'den canlı schema bilgilerini çeker"""
    if not neo4j_available:
        return None
    
    try:
        logger.info("Detecting live schema from Neo4j...")
        
        # Node türlerini ve sayılarını al
        simple_node_query = """
        MATCH (n) 
        RETURN labels(n)[0] as label, count(n) as count 
        ORDER BY label
        """
        
        # Relationship türlerini ve sayılarını al
        simple_rel_query = """
        MATCH ()-[r]->() 
        RETURN type(r) as relationshipType, count(r) as count 
        ORDER BY relationshipType
        """
        
        nodes = query_neo4j(simple_node_query) or []
        relationships = query_neo4j(simple_rel_query) or []
        
        # Schema örnek sorguları - her relationship için properties
        sample_queries = {}
        for rel_info in relationships:
            rel_type = rel_info[0]
            sample_query = f"""
            MATCH ()-[r:{rel_type}]->() 
            WITH r
            LIMIT 1
            RETURN keys(r) as properties
            """
            try:
                props_result = query_neo4j(sample_query)
                if props_result and props_result[0][0]:
                    sample_queries[rel_type] = props_result[0][0]
                else:
                    sample_queries[rel_type] = []
            except:
                sample_queries[rel_type] = []
        
        total_nodes = sum(info[1] for info in nodes) if nodes else 0
        total_rels = sum(info[1] for info in relationships) if relationships else 0
        
        logger.info(f"Schema detection completed: {len(nodes)} node types, {len(relationships)} relationship types")
        
        return {
            "nodes": nodes,
            "relationships": relationships, 
            "relationship_properties": sample_queries,
            "total_nodes": total_nodes,
            "total_relationships": total_rels,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Schema detection failed: {str(e)}")
        return None

def generate_dynamic_schema():
    """Canlı schema bilgilerinden prompt oluştur"""
    schema_info = detect_live_schema()
    
    if not schema_info:
        # Fallback to static schema
        return """
FALLBACK STATIC SCHEMA:

Nodes:
- (p:Person) Properties: name (string), born (integer, optional)
- (m:Movie) Properties: title (string), released (integer), tagline (string, optional)

Relationships:
- (p:Person)-[r:ACTED_IN]->(m:Movie) Properties: r.earnings (integer), r.roles (array)
- (p1:Person)-[:HAS_CONTACT]-(p2:Person) Properties: none

CRITICAL SYNTAX RULES:
1. ALWAYS use relationship variables: MATCH (p)-[r:ACTED_IN]->(m)
2. Access relationship properties as: r.earnings, r.roles
3. NEVER use: relationships.ACTED_IN.earnings
4. Person birth year: p.born, Movie release year: m.released
"""
    
    nodes_text = "\n".join([
        f"- {info[0]} ({info[1]} nodes)" 
        for info in schema_info["nodes"]
    ])
    
    relationships_text = ""
    for rel_info in schema_info["relationships"]:
        rel_type = rel_info[0]
        rel_count = rel_info[1]
        props = schema_info["relationship_properties"].get(rel_type, [])
        props_text = f"Properties: {', '.join(props)}" if props else "Properties: none detected"
        relationships_text += f"- {rel_type} ({rel_count} relationships) - {props_text}\n"
    
    dynamic_schema = f"""
LIVE DATABASE SCHEMA (Auto-detected from Neo4j):
Total Nodes: {schema_info['total_nodes']} | Total Relationships: {schema_info['total_relationships']}

Node Types:
{nodes_text}

Relationship Types:
{relationships_text}

CRITICAL SYNTAX RULES:
1. ALWAYS use relationship variables: MATCH (p)-[r:RELATIONSHIP_TYPE]->(m)
2. Access relationship properties as: r.property_name
3. NEVER use: relationships.RELATIONSHIP_TYPE.property (THIS IS WRONG!)
4. Person birth year: p.born (not p.birthdate)
5. Movie release year: m.released (not m.year)
6. Use type(r) to get relationship type in queries
7. For unknown properties, explore with keys(r)
8. For social relationships: HAS_CONTACT (bidirectional), FOLLOWS (directional)

SAMPLE QUERIES FOR DETECTED RELATIONSHIPS:
"""
    
    # Her relationship için örnek sorgu ekle
    for rel_info in schema_info["relationships"]:
        rel_type = rel_info[0]
        if rel_type == "ACTED_IN":
            dynamic_schema += f"""
-- {rel_type} (Actor queries)
MATCH (p:Person)-[r:{rel_type}]->(m:Movie) WHERE p.name = 'Keanu Reeves'
RETURN p.name, m.title, r.earnings, r.roles LIMIT 10
"""
        elif rel_type == "DIRECTED":
            dynamic_schema += f"""
-- {rel_type} (Director queries)  
MATCH (p:Person)-[r:{rel_type}]->(m:Movie)
RETURN p.name AS director, m.title AS film, m.released AS year ORDER BY m.released DESC LIMIT 10
"""
        elif rel_type == "PRODUCED":
            dynamic_schema += f"""
-- {rel_type} (Producer queries)
MATCH (p:Person)-[r:{rel_type}]->(m:Movie)
RETURN p.name AS producer, m.title AS film LIMIT 10
"""
        elif rel_type == "WROTE":
            dynamic_schema += f"""
-- {rel_type} (Writer queries)
MATCH (p:Person)-[r:{rel_type}]->(m:Movie)
RETURN p.name AS writer, m.title AS film LIMIT 10
"""
        elif rel_type == "REVIEWED":
            dynamic_schema += f"""
-- {rel_type} (Review queries)
MATCH (p:Person)-[r:{rel_type}]->(m:Movie)
RETURN p.name AS reviewer, m.title AS film, r.rating AS rating LIMIT 10
"""
        elif rel_type == "HAS_CONTACT":
            dynamic_schema += f"""
-- {rel_type} (Social network)
MATCH (p1:Person)-[:{rel_type}]-(p2:Person) WHERE p1.name = 'Keanu Reeves'
RETURN p2.name AS contact LIMIT 10
"""
        elif rel_type == "FOLLOWS":
            dynamic_schema += f"""
-- {rel_type} (Follow relationships)
MATCH (p1:Person)-[:{rel_type}]->(p2:Person)
RETURN p1.name AS follower, p2.name AS followed LIMIT 10
"""
        else:
            dynamic_schema += f"""
-- {rel_type} (Generic relationship)
MATCH (p:Person)-[r:{rel_type}]->(m:Movie)
RETURN p.name, m.title, type(r) as relationship_type LIMIT 10
"""
    
    # Multi-role queries
    dynamic_schema += """
-- Multi-role queries (person with multiple roles in film industry)
MATCH (p:Person)-[r]->(m:Movie) WHERE p.name = 'Steven Spielberg'
RETURN p.name, type(r) AS role, m.title ORDER BY m.released LIMIT 20

-- Film crew (all people involved in a specific movie)
MATCH (m:Movie)<-[r]-(p:Person) WHERE m.title = 'The Matrix'
RETURN p.name, type(r) AS role ORDER BY role LIMIT 30
"""
    
    return dynamic_schema

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
        (r'relationships\.PRODUCED\.', 'r.'),
        (r'relationships\.WROTE\.', 'r.'),
        (r'relationships\.REVIEWED\.', 'r.'),
        (r'relationships\.(\w+)\.(\w+)', r'r.\2'),
        
        # Property name fixes
        (r'\.birthdate\b', '.born'),
        (r'\.year\b', '.released'),
        (r'\.salary\b', '.earnings'),
        
        # Ensure relationship variables exist for all relationship types
        (r'-\[:ACTED_IN\]->', '-[r:ACTED_IN]->'),
        (r'-\[:DIRECTED\]->', '-[r:DIRECTED]->'),
        (r'-\[:PRODUCED\]->', '-[r:PRODUCED]->'),
        (r'-\[:WROTE\]->', '-[r:WROTE]->'),
        (r'-\[:REVIEWED\]->', '-[r:REVIEWED]->'),
        (r'-\[:HAS_CONTACT\]-', '-[:HAS_CONTACT]-'),  # Bidirectional, no properties
        (r'-\[:FOLLOWS\]->', '-[:FOLLOWS]->'),  # Directional, no properties
    ]
    
    for pattern, replacement in fixes:
        cypher_query = re.sub(pattern, replacement, cypher_query, flags=re.IGNORECASE)
    
    # Ensure relationship variable is defined when accessing properties
    property_access_patterns = ['r.earnings', 'r.roles', 'r.rating', 'r.review']
    for prop_pattern in property_access_patterns:
        if prop_pattern in cypher_query:
            # Make sure we have relationship variable defined
            if '-[:' in cypher_query and '-[r:' not in cypher_query:
                cypher_query = re.sub(r'-\[:(\w+)\]->', r'-[r:\1]->', cypher_query)
    
    return cypher_query

def ask_cypher_json(question, model_index=0):
    """Generate Cypher query from natural language question - DYNAMIC SCHEMA"""
    logger.info(f"Generating Cypher for question: {question}")
    
    # Check cache first
    cache_key = f"cypher_{question}"
    cached = get_from_cache(cache_key)
    if cached:
        logger.info("Using cached Cypher query")
        return cached

    if model_index >= len(FALLBACK_MODELS):
        logger.error("All models failed")
        return {"error": "token_exhausted", "message": "Tüm AI modelleri token limitine ulaştı. Lütfen daha sonra tekrar deneyin."}
    
    current_model = FALLBACK_MODELS[model_index]
    
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }

    # DİNAMİK SCHEMA KULLAN
    dynamic_schema = generate_dynamic_schema()

    prompt = f"""
Generate a JSON response for the user's question using the EXACT schema provided above.

MANDATORY FORMAT:
{{
  "cypher": "Neo4j Cypher query using correct schema",
  "description": "Brief explanation in Turkish"
}}

SCHEMA ENFORCEMENT RULES:
1. Use ONLY the relationships detected in the live schema
2. Person properties: name, born (not birthdate!)
3. Movie properties: title, released (not year!), tagline  
4. Use relationship variables: [r:RELATIONSHIP_TYPE]
5. NEVER use: relationships.RELATIONSHIP_TYPE.property
6. ALWAYS use: r.property_name
7. Add LIMIT (max 50)
8. Only READ operations
9. Use type(r) for relationship type queries
10. For multi-role queries: MATCH (p)-[r]->(m) WHERE... RETURN type(r)

User question: "{question}"

ADVANCED EXAMPLES FOR ALL RELATIONSHIP TYPES:

{{
  "cypher": "MATCH (p:Person)-[r:DIRECTED]->(m:Movie) RETURN p.name AS director, m.title AS film, m.released AS year ORDER BY m.released DESC LIMIT 20",
  "description": "Yönetmenleri ve filmlerini kronolojik sırayla listeler"
}}

{{
  "cypher": "MATCH (p:Person)-[r]->(m:Movie) WHERE m.title = 'The Matrix' RETURN p.name AS person, type(r) AS role ORDER BY role LIMIT 30",
  "description": "Matrix filmindeki tüm rolleri (oyuncu, yönetmen, yapımcı vs.) listeler"
}}

{{
  "cypher": "MATCH (p1:Person)-[:FOLLOWS]->(p2:Person) RETURN p1.name AS follower, p2.name AS followed LIMIT 25",
  "description": "Sosyal ağdaki takip ilişkilerini gösterir"
}}

{{
  "cypher": "MATCH (p:Person)-[r:PRODUCED]->(m:Movie) RETURN p.name AS producer, m.title AS film, m.released AS year ORDER BY year DESC LIMIT 15",
  "description": "Yapımcıları ve ürettikleri filmleri listeler"
}}

{{
  "cypher": "MATCH (p:Person)-[r:REVIEWED]->(m:Movie) RETURN p.name AS reviewer, m.title AS film, r.rating AS rating ORDER BY r.rating DESC LIMIT 20",
  "description": "Film eleştirilerini puanlarıyla birlikte listeler"
}}
"""

    data = {
        "model": current_model,
        "messages": [
            {
                "role": "system",
                "content": f"You are a Neo4j Cypher expert. Use ONLY the provided live schema. NEVER use relationships.RELATIONSHIP_TYPE.property syntax. ALWAYS use relationship variables like r.property. Return only valid JSON.\n\nSchema:\n{dynamic_schema}"
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
        
        # Token limit kontrolü
        if response.status_code == 429:
            logger.warning(f"Rate limit hit for model {current_model}")
            return ask_cypher_json(question, model_index + 1)
            
        # Quota exceeded kontrolü
        if response.status_code == 402:
            logger.error(f"Token quota exceeded for model {current_model}")
            return ask_cypher_json(question, model_index + 1)
        
        response.raise_for_status()
        result = response.json()
        
        # API yanıtında token limit kontrolü
        if "error" in result:
            error_type = result["error"].get("type", "")
            error_code = result["error"].get("code", "")
            
            if "quota" in error_type.lower() or "limit" in error_type.lower():
                logger.error(f"Token quota error from {current_model}: {result['error']}")
                return ask_cypher_json(question, model_index + 1)
        
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
        # HTTP 429 veya 402 hatalarını kontrol et
        if hasattr(e, 'response') and e.response is not None:
            if e.response.status_code in [429, 402]:
                return ask_cypher_json(question, model_index + 1)
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
        return "Token limitine ulaşıldı. Lütfen daha sonra tekrar deneyin veya farklı bir soru sorun."
    
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
- Film adlarını hem İngilizce hem Türkçe belirtin
- Farklı roller varsa (oyuncu, yönetmen, yapımcı) belirtin"""

    data = {
        "model": current_model,
        "messages": [
            {
                "role": "system",
                "content": """Sen yardımsever bir film veritabanı asistanısın. Türkçe cevaplar veriyorsun.
- Kısa ve anlaşılır ol
- Sayıları güzel formatla
- Emoji az kullan
- Veri yoksa alternatif öner
- Farklı rolleri (oyuncu, yönetmen, yapımcı) açıkla"""
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
        
        # Token limit kontrolü
        if response.status_code == 429:
            logger.warning(f"Rate limit hit for answer generation with {current_model}")
            return ask_gemma(question, cypher_results, model_index + 1)
            
        # Quota exceeded kontrolü  
        if response.status_code == 402:
            logger.error(f"Token quota exceeded for answer generation with {current_model}")
            return ask_gemma(question, cypher_results, model_index + 1)
        
        response.raise_for_status()
        result = response.json()
        
        # API yanıtında token limit kontrolü
        if "error" in result:
            error_type = result["error"].get("type", "")
            if "quota" in error_type.lower() or "limit" in error_type.lower():
                logger.error(f"Token quota error in answer generation: {result['error']}")
                return ask_gemma(question, cypher_results, model_index + 1)
        
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
        if hasattr(e, 'response') and e.response is not None:
            if e.response.status_code in [429, 402]:
                return ask_gemma(question, cypher_results, model_index + 1)
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
        
        # Token limit kontrolü
        if isinstance(json_data, dict) and json_data.get("error") == "token_exhausted":
            return jsonify({
                "answer": json_data["message"], 
                "cypher": None, 
                "error": "token_limit",
                "results": None
            })
            
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
        
        # Token limit kontrolü cevap için
        if "Token limitine ulaşıldı" in answer:
            return jsonify({
                "answer": answer,
                "cypher": cypher_query,
                "results": results,
                "error": "token_limit",
                "description": json_data.get("description", "")
            })
        
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

@app.route("/api/schema", methods=["GET"])
def api_schema():
    """Get current database schema information"""
    try:
        schema_info = detect_live_schema()
        if schema_info:
            return jsonify({
                "status": "success",
                "schema": schema_info,
                "message": f"Schema detected: {schema_info['total_nodes']} nodes, {schema_info['total_relationships']} relationships"
            })
        else:
            return jsonify({
                "status": "error", 
                "message": "Schema detection failed - Neo4j may not be available"
            }), 503
    except Exception as e:
        logger.error(f"Error getting schema: {str(e)}")
        return jsonify({"error": "Schema bilgisi alınamadı"}), 500

@app.route("/api/health", methods=["GET"])
def api_health():
    """Health check endpoint with enhanced information"""
    health_status = {
        "status": "healthy",
        "neo4j": neo4j_available,
        "timestamp": os.getenv('TIMESTAMP', 'unknown'),
        "models": FALLBACK_MODELS
    }
    
    if neo4j_available:
        try:
            # Test query
            test_result = query_neo4j("MATCH (n) RETURN count(n) AS total LIMIT 1")
            health_status["neo4j_test"] = "success"
            health_status["total_nodes"] = test_result[0][0] if test_result else 0
            
            # Get schema info
            schema_info = detect_live_schema()
            if schema_info:
                health_status["schema"] = {
                    "node_types": len(schema_info["nodes"]),
                    "relationship_types": len(schema_info["relationships"]),
                    "total_nodes": schema_info["total_nodes"],
                    "total_relationships": schema_info["total_relationships"]
                }
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