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
import google.generativeai as genai

# GraphRAG imports
from embeddings import EmbeddingManager, create_semantic_index
from context_manager import GraphContextManager
from graphrag_pipeline import GraphRAGPipeline

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

# Gemini Configuration
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
GEMINI_MODEL = os.getenv('GEMINI_MODEL', 'gemini-2.0-flash-exp')
USE_GEMINI = os.getenv('USE_GEMINI', 'True').lower() == 'true'

# Fallback OpenRouter Configuration
GEMMA_MODEL = os.getenv('GEMMA_MODEL', 'google/gemma-3-27b-it:free')
OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY')

# Model alternatives for failover
FALLBACK_MODELS = [
    'google/gemma-2-9b-it:free',
    'meta-llama/llama-3.1-8b-instruct:free',
    'microsoft/phi-3-medium-128k-instruct:free',
    'qwen/qwen-2-7b-instruct:free'
]

# Initialize Gemini and GraphRAG
gemini_available = False
embedding_manager = None
graphrag_pipeline = None

if USE_GEMINI and GEMINI_API_KEY:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        logger.info(f"Gemini API configured with model: {GEMINI_MODEL}")
        gemini_available = True
        
        # Initialize GraphRAG components
        embedding_manager = EmbeddingManager(GEMINI_API_KEY)
        logger.info("GraphRAG embedding manager initialized")
        
    except Exception as e:
        logger.error(f"Failed to initialize Gemini API: {str(e)}")
        if "API_KEY" in str(e) or "Invalid API key" in str(e):
            logger.error("Invalid Gemini API key - check your key at https://aistudio.google.com/app/apikey")
        gemini_available = False

# Validate required environment variables
if not NEO4J_PASS:
    logger.error("NEO4J_PASSWORD environment variable is not set")
    raise ValueError("NEO4J_PASSWORD is required")

if USE_GEMINI and not GEMINI_API_KEY:
    logger.error("GEMINI_API_KEY environment variable is not set but USE_GEMINI is True")
    USE_GEMINI = False

if not USE_GEMINI and not OPENROUTER_API_KEY:
    logger.error("Neither GEMINI_API_KEY nor OPENROUTER_API_KEY is set")
    raise ValueError("At least one AI API key is required")

# ======== Neo4j Connection ========
neo4j_available = False
driver = None

def initialize_neo4j():
    """Initialize Neo4j connection with retry logic and GraphRAG setup"""
    global neo4j_available, driver, graphrag_pipeline
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
            driver.verify_connectivity()
            neo4j_available = True
            logger.info(f"Successfully connected to Neo4j (attempt {attempt + 1})")
            
            # Initialize GraphRAG pipeline
            if embedding_manager and embedding_manager.available:
                graphrag_pipeline = GraphRAGPipeline(driver, embedding_manager)
                logger.info("GraphRAG pipeline initialized successfully")
                
                # Create semantic index if possible
                create_semantic_index(driver, embedding_manager)
            
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
    """Execute Neo4j query with enhanced error handling and JSON serialization"""
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
                    values.append(convert_neo4j_value(value))
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

def convert_neo4j_value(value):
    """Convert Neo4j objects to JSON serializable Python objects"""
    try:
        # Neo4j Node
        if hasattr(value, 'labels') and hasattr(value, 'items'):
            return {
                'labels': list(value.labels),
                'properties': dict(value.items()),
                'id': value.element_id if hasattr(value, 'element_id') else str(value.id)
            }
        
        # Neo4j Relationship
        elif hasattr(value, 'type') and hasattr(value, 'start_node'):
            return {
                'type': value.type,
                'properties': dict(value.items()),
                'start_node': value.start_node.element_id if hasattr(value.start_node, 'element_id') else str(value.start_node.id),
                'end_node': value.end_node.element_id if hasattr(value.end_node, 'element_id') else str(value.end_node.id)
            }
        
        # Neo4j Path
        elif hasattr(value, 'nodes') and hasattr(value, 'relationships'):
            return {
                'nodes': [convert_neo4j_value(node) for node in value.nodes],
                'relationships': [convert_neo4j_value(rel) for rel in value.relationships],
                'length': len(value.relationships)
            }
        
        # Neo4j datetime/date objects
        elif hasattr(value, 'value'):
            return value.value
        
        # Lists
        elif isinstance(value, list):
            return [convert_neo4j_value(item) for item in value]
        
        # Dictionaries
        elif isinstance(value, dict):
            return {key: convert_neo4j_value(val) for key, val in value.items()}
        
        # Basic types (int, float, str, bool, None)
        else:
            return value
            
    except Exception as e:
        logger.warning(f"Failed to convert Neo4j value: {value}, error: {e}")
        return str(value)  # Fallback to string representation

def detect_live_schema():
    """Neo4j'den canlı schema bilgilerini TAMAMEN dinamik olarak çeker"""
    if not neo4j_available:
        return None
    
    try:
        logger.info("Detecting COMPREHENSIVE live schema from Neo4j...")
        
        # TAMAMEN DİNAMİK SCHEMA DETECTİON
        
        # 1. Tüm node türlerini ve sample properties'lerini al
        comprehensive_node_query = """
        MATCH (n) 
        WITH labels(n)[0] AS node_label, collect(keys(n)) AS all_keys, count(n) AS node_count,
             collect(n)[0] AS sample_node
        WITH node_label, node_count, sample_node,
             reduce(unique_keys = [], key_set IN all_keys | 
                    unique_keys + [k IN key_set WHERE NOT k IN unique_keys]) AS unique_properties
        RETURN node_label, node_count, unique_properties, 
               properties(sample_node) AS sample_properties
        ORDER BY node_label
        """
        
        # 2. Tüm relationship türlerini ve properties'lerini al
        comprehensive_rel_query = """
        MATCH ()-[r]->() 
        WITH type(r) AS rel_type, collect(keys(r)) AS all_keys, count(r) AS rel_count,
             collect(r)[0] AS sample_rel
        WITH rel_type, rel_count, sample_rel,
             reduce(unique_keys = [], key_set IN all_keys | 
                    unique_keys + [k IN key_set WHERE NOT k IN unique_keys]) AS unique_properties
        RETURN rel_type, rel_count, unique_properties,
               properties(sample_rel) AS sample_properties
        ORDER BY rel_type
        """
        
        # 3. Node-to-Node connections pattern analizi
        connection_pattern_query = """
        MATCH (n1)-[r]->(n2)
        WITH labels(n1)[0] AS from_label, type(r) AS rel_type, labels(n2)[0] AS to_label, count(*) AS connection_count
        RETURN from_label, rel_type, to_label, connection_count
        ORDER BY connection_count DESC
        LIMIT 50
        """
        
        # 4. Property value samples - gerçek veri örnekleri
        property_samples_query = """
        MATCH (n) 
        WITH labels(n)[0] AS node_type, keys(n) AS props, n
        UNWIND props AS prop_name
        WITH node_type, prop_name, n[prop_name] AS prop_value
        WHERE prop_value IS NOT NULL
        WITH node_type, prop_name, collect(DISTINCT toString(prop_value))[0..3] AS sample_values, count(*) AS total_count
        RETURN node_type, prop_name, sample_values, total_count
        ORDER BY node_type, prop_name
        """
        
        # Execute all queries
        nodes_info = query_neo4j(comprehensive_node_query) or []
        relationships_info = query_neo4j(comprehensive_rel_query) or []
        connection_patterns = query_neo4j(connection_pattern_query) or []
        property_samples = query_neo4j(property_samples_query) or []
        
        # Process results
        total_nodes = sum(info[1] for info in nodes_info) if nodes_info else 0
        total_rels = sum(info[1] for info in relationships_info) if relationships_info else 0
        
        # Organize property samples by node type
        property_samples_by_type = {}
        for sample in property_samples:
            node_type = sample[0]
            prop_name = sample[1]
            sample_vals = sample[2]
            total_count = sample[3]
            
            if node_type not in property_samples_by_type:
                property_samples_by_type[node_type] = {}
            
            property_samples_by_type[node_type][prop_name] = {
                'sample_values': sample_vals,
                'total_count': total_count
            }
        
        logger.info(f"COMPREHENSIVE schema detection completed: {len(nodes_info)} node types, {len(relationships_info)} relationship types, {len(connection_patterns)} connection patterns")
        
        return {
            "nodes": nodes_info,
            "relationships": relationships_info,
            "connection_patterns": connection_patterns,
            "property_samples": property_samples_by_type,
            "total_nodes": total_nodes,
            "total_relationships": total_rels,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Comprehensive schema detection failed: {str(e)}")
        return None

def generate_dynamic_schema():
    """Canlı schema bilgilerinden KAPSAMLI GraphRAG prompt oluştur"""
    schema_info = detect_live_schema()
    
    if not schema_info:
        return """
FALLBACK SCHEMA - Veritabanına bağlanılamadı:
Bu durumda temel Neo4j sorgu örnekleri kullanılacaktır.

Temel Sorgular:
- MATCH (n) RETURN labels(n), count(n) - Node türlerini listele
- MATCH ()-[r]->() RETURN type(r), count(r) - İlişki türlerini listele
- CALL db.schema.visualization() - Şemayı görselleştir
"""
    
    # ENHANCED Node türlerini properties ile birlikte dinamik olarak oluştur
    nodes_text = ""
    for node_info in schema_info["nodes"]:
        node_label = node_info[0]
        node_count = node_info[1]
        node_properties = node_info[2]  # unique_properties
        sample_props = node_info[3]     # sample_properties
        
        # Property samples from property_samples
        prop_details = ""
        if node_label in schema_info.get("property_samples", {}):
            prop_samples = schema_info["property_samples"][node_label]
            for prop_name, prop_info in prop_samples.items():
                sample_vals = prop_info["sample_values"]
                total_count = prop_info["total_count"]
                prop_details += f"    - {prop_name}: {sample_vals} (toplam {total_count} kayıt)\n"
        
        nodes_text += f"""
NODE: ({node_label}) - {node_count} adet node
Properties: {node_properties}
Sample values:
{prop_details}
"""
    
    # ENHANCED İlişki türlerini properties ile birlikte dinamik olarak oluştur
    relationships_text = ""
    for rel_info in schema_info["relationships"]:
        rel_type = rel_info[0]
        rel_count = rel_info[1]
        rel_properties = rel_info[2]    # unique_properties
        sample_props = rel_info[3]      # sample_properties
        
        relationships_text += f"""
RELATIONSHIP: :{rel_type} ({rel_count} adet)
Properties: {rel_properties}
Sample properties: {sample_props}
"""
    
    # CONNECTION PATTERNS - Hangi node'lar nasıl bağlanıyor
    patterns_text = ""
    for pattern in schema_info.get("connection_patterns", []):
        from_label = pattern[0]
        rel_type = pattern[1]
        to_label = pattern[2]
        count = pattern[3]
        patterns_text += f"({from_label})-[:{rel_type}]->({to_label}) : {count} bağlantı\n"
    
    dynamic_schema = f"""
🔥 CANLI DİNAMİK VERİTABANI ŞEMASI (Neo4j'den otomatik tespit edildi):
Toplam Node: {schema_info['total_nodes']} | Toplam İlişki: {schema_info['total_relationships']}
Son güncelleme: {schema_info['timestamp']}

📊 DETAYLI NODE TÜRLERİ VE PROPERTİLERİ:
{nodes_text}

🔗 DETAYLI İLİŞKİ TÜRLERİ VE PROPERTİLERİ:
{relationships_text}

🌐 BAĞLANTI DESENLERI (Graf Yapısı):
{patterns_text}

⚡ ÖNEMLİ CYPHER SYNTAX KURALLARI:
1. İlişki değişkenlerini MUTLAKA kullan: MATCH (n1)-[r:RELATIONSHIP_TYPE]->(n2)
2. Property erişimi: n.property_name, r.property_name
3. ASLA kullanma: relationships.RELATIONSHIP_TYPE.property (YANLIŞ!)
4. Dinamik property erişimi: n[property_name] 
5. Property varlığı kontrolü: WHERE n.property IS NOT NULL
6. Pattern matching: MATCH (n:NodeType {{property: 'value'}})

🚀 DİNAMİK AKILLI SORGU ÖRNEKLERİ:
"""
    
    # Her node tipi için dinamik örnek sorgular oluştur
    for node_info in schema_info["nodes"]:
        node_label = node_info[0]
        node_properties = node_info[2]
        
        dynamic_schema += f"""
-- {node_label} node'ları için akıllı sorgular:
MATCH (n:{node_label}) RETURN n LIMIT 10
MATCH (n:{node_label}) RETURN keys(n), count(n)
MATCH (n:{node_label}) WHERE n.{node_properties[0] if node_properties else 'name'} CONTAINS 'search_term' RETURN n
"""
    
    # Her relationship tipi için dinamik örnek sorgular
    for rel_info in schema_info["relationships"]:
        rel_type = rel_info[0]
        dynamic_schema += f"""
-- {rel_type} ilişkisi için akıllı sorgular:
MATCH (n1)-[r:{rel_type}]->(n2) RETURN n1, r, n2 LIMIT 5
MATCH (n1)-[r:{rel_type}]->(n2) RETURN type(r), count(r), keys(r)
"""
    
    # CONNECTION PATTERN based queries
    for pattern in schema_info.get("connection_patterns", [])[:5]:  # İlk 5 pattern
        from_label = pattern[0]
        rel_type = pattern[1]
        to_label = pattern[2]
        
        dynamic_schema += f"""
-- {from_label} -> {to_label} pattern sorgular:
MATCH ({from_label.lower()}:{from_label})-[r:{rel_type}]->({to_label.lower()}:{to_label}) 
RETURN {from_label.lower()}, r, {to_label.lower()} LIMIT 10
"""
    
    # Genel analiz sorguları ekle
    dynamic_schema += f"""

🔍 KAPSAMLI ANALİZ SORGU ÖRNEKLERİ:

-- En merkezi node'ları bul (degree centrality)
MATCH (n)
WITH n, size([(n)-[]-() | 1]) AS degree
WHERE degree > 0
RETURN n, degree
ORDER BY degree DESC LIMIT 10

-- Node properties analizi
MATCH (n) 
WITH labels(n)[0] AS node_type, keys(n) AS props
UNWIND props AS prop
RETURN node_type, prop, count(*) AS usage_count
ORDER BY node_type, usage_count DESC

-- İlişki properties analizi  
MATCH ()-[r]->()
WITH type(r) AS rel_type, keys(r) AS props
UNWIND props AS prop
RETURN rel_type, prop, count(*) AS usage_count
ORDER BY rel_type, usage_count DESC

-- Belirli property değerine sahip node'ları bul
MATCH (n) 
WHERE any(prop IN keys(n) WHERE toString(n[prop]) CONTAINS 'arama_terimi')
RETURN n, [prop IN keys(n) WHERE toString(n[prop]) CONTAINS 'arama_terimi' | prop + ': ' + toString(n[prop])] AS matching_properties

-- Graf derinlik analizi
MATCH path = (start)-[*1..3]-(end)
WHERE start <> end
RETURN length(path) AS depth, count(path) AS path_count
ORDER BY depth

-- Orphan node'ları bul (bağlantısız)
MATCH (n)
WHERE NOT (n)-[]-()
RETURN labels(n)[0] AS node_type, count(n) AS orphan_count
ORDER BY orphan_count DESC

TEXT2CYPHER TASK - DİNAMİK VERİ ERİŞİMİ:
Kullanıcının doğal dilindeki sorusunu yukarıdaki DETAYLI şema bilgilerini kullanarak Cypher sorgusuna çevir.
- Gerçek property isimlerini kullan
- Dinamik değer eşleştirmesi yap
- Pattern matching kullan
- CONTAINS, STARTS WITH, ENDS WITH operatörlerini kullan
- Yanıtın sadece Cypher sorgusu olsun, açıklama yazma.

ÖRNEK DÖNÜŞÜMLER:
"Obsidian Elite ürününe yapılan yorumu getir" ->
MATCH (p:Product {{name: 'Obsidian Elite'}})<-[:REVIEWED_BY]-(r:Review) RETURN p, r
veya 
MATCH (p:Product) WHERE p.name CONTAINS 'Obsidian Elite' 
MATCH (p)<-[:REVIEW_OF]-(r:Review) RETURN p, r

"MSI marka ürünleri" ->
MATCH (b:Brand {{name: 'MSI'}})<-[:MADE_BY]-(p:Product) RETURN p, b
veya
MATCH (p:Product) WHERE p.brand CONTAINS 'MSI' RETURN p
"""
    
    return dynamic_schema


def call_gemini_api(prompt, system_prompt=""):
    """Call Gemini API for text generation"""
    if not gemini_available:
        logger.error("Gemini API not available")
        return None
        
    try:
        # Güvenlik ayarlarını gevşet
        safety_settings = [
            {
                "category": "HARM_CATEGORY_HARASSMENT",
                "threshold": "BLOCK_NONE"
            },
            {
                "category": "HARM_CATEGORY_HATE_SPEECH", 
                "threshold": "BLOCK_NONE"
            },
            {
                "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                "threshold": "BLOCK_NONE"
            },
            {
                "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                "threshold": "BLOCK_NONE"
            }
        ]
        
        model = genai.GenerativeModel(
            model_name=GEMINI_MODEL,
            safety_settings=safety_settings
        )
        
        # Combine system and user prompts
        if system_prompt:
            full_prompt = f"SISTEM TALIMATI: {system_prompt}\n\nKULLANICI SORUSU: {prompt}"
        else:
            full_prompt = prompt
        
        response = model.generate_content(
            full_prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.3,
                max_output_tokens=8192,  # Daha uzun yanıtlar için artırıldı
                top_p=0.95,  
                top_k=40
            )
        )
        
        if response and response.text:
            logger.info("Gemini API call successful")
            return response.text.strip()
        elif response and response.candidates:
            # Güvenlik filtresine takıldı mı kontrol et
            candidate = response.candidates[0]
            if hasattr(candidate, 'finish_reason') and candidate.finish_reason == 3:  # SAFETY
                logger.warning("Gemini API blocked by safety filter")
                return None
            else:
                logger.warning(f"Gemini API finish reason: {getattr(candidate, 'finish_reason', 'unknown')}")
                return None
        else:
            logger.warning("Gemini API returned completely empty response")
            return None
            
    except Exception as e:
        logger.error(f"Gemini API call failed: {str(e)}")
        # API key hatası detayı
        if "API_KEY" in str(e) or "Invalid API key" in str(e) or "403" in str(e):
            logger.error("Gemini API key hatası - yeni key gerekebilir")
        elif "quota" in str(e).lower() or "limit" in str(e).lower():
            logger.error("Gemini API quota/limit hatası") 
        elif "400" in str(e):
            logger.error("Gemini API bad request - model veya parametre hatası")
        return None


def call_openrouter_api(prompt, system_prompt="", model=None):
    """Fallback to OpenRouter API"""
    if not OPENROUTER_API_KEY:
        return None
        
    if not model:
        model = FALLBACK_MODELS[0]
    
    try:
        response = requests.post(
            'https://openrouter.ai/api/v1/chat/completions',
            headers={
                'Authorization': f'Bearer {OPENROUTER_API_KEY}',
                'Content-Type': 'application/json'
            },
            json={
                'model': model,
                'messages': [
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': prompt}
                ],
                'temperature': 0.1,
                'max_tokens': 2048
            },
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            return result['choices'][0]['message']['content'].strip()
        else:
            logger.warning(f"OpenRouter API error: {response.status_code}")
            return None
            
    except Exception as e:
        logger.error(f"OpenRouter API call failed: {str(e)}")
        return None


def create_cypher_from_question(question, schema_context):
    """Convert natural language question to Cypher query using Gemini AI"""
    try:
        prompt = f"""
{schema_context}

GÖREV: Aşağıdaki doğal dil sorusunu Neo4j Cypher sorgusuna çevir.

SORU: {question}

ÖNEMLİ KURALLAR:
1. Sadece MATCH ve RETURN kullan, değiştirici sorgular yasak
2. İlişki değişkenleri mutlaka kullan: -[r:RELATIONSHIP_TYPE]->
3. Güvenli sorgular yaz, deletion/modification yok
4. Sonuç LIMIT ile sınırla (max 50)
5. Yanıtın sadece Cypher sorgusu olsun

CYPHER SORGUSU:
"""
        
        system_prompt = "Sen bir Neo4j Cypher uzmanısın. Doğal dil sorularını Cypher sorgularına çevirirsin. Sadece güvenli MATCH/RETURN sorguları oluştur."
        
        # Use Gemini API
        if USE_GEMINI and GEMINI_API_KEY:
            cypher_query = call_gemini_api(prompt, system_prompt)
            if cypher_query:
                cypher_query = clean_cypher_query(cypher_query)
                cypher_query = fix_advanced_cypher_syntax(cypher_query)
                
                if validate_cypher_query(cypher_query):
                    logger.info(f"Generated Cypher query with Gemini: {cypher_query}")
                    return cypher_query
                else:
                    logger.warning("Generated invalid Cypher with Gemini")
        
        # If Gemini fails, return a basic schema query
        logger.error("Gemini API failed, returning basic query")
        return "MATCH (n) RETURN labels(n), count(n) ORDER BY count(n) DESC LIMIT 10"
        
    except Exception as e:
        logger.error(f"Critical error in create_cypher_from_question: {str(e)}")
        return "MATCH (n) RETURN labels(n), count(n) LIMIT 10"


def validate_cypher_query(query):
    """Enhanced validation to prevent Cypher injection"""
    if not query or not isinstance(query, str):
        return False
    
    # Dangerous keywords
    dangerous_keywords = [
        'DELETE', 'REMOVE', 'DROP', 'CREATE', 'MERGE', 'SET', 
        'DETACH', 'FOREACH', 'LOAD'
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
    
    # Fix common syntax issues
    fixes = [
        # İlişki property erişim hatalarını düzelt
        (r'relationships\.(\w+)\.(\w+)', r'r.\2'),
        
        # Property name düzeltmeleri
        (r'\.birthdate\b', '.born'),
        (r'\.year\b', '.released'),
        (r'\.salary\b', '.earnings'),
        
        # İlişki değişkenleri ekle
        (r'-\[:(\w+)\]->', r'-[r:\1]->'),
        (r'-\[:(\w+)\]-', r'-[r:\1]-'),
    ]
    
    for pattern, replacement in fixes:
        cypher_query = re.sub(pattern, replacement, cypher_query, flags=re.IGNORECASE)
    
    return cypher_query


def clean_cypher_query(query):
    """Clean up AI generated Cypher query"""
    if not query:
        return ""
    
    # Remove markdown formatting
    query = re.sub(r'```cypher\s*', '', query, flags=re.IGNORECASE)
    query = re.sub(r'```\s*$', '', query)
    query = re.sub(r'^```', '', query)
    
    # Remove extra whitespace and comments
    lines = query.split('\n')
    cleaned_lines = []
    for line in lines:
        line = line.strip()
        if line and not line.startswith('//') and not line.startswith('--'):
            cleaned_lines.append(line)
    
    # Join with spaces
    query = ' '.join(cleaned_lines)
    
    # Ensure single spaces
    query = re.sub(r'\s+', ' ', query)
    
    return query.strip()

def ask_cypher_json(question, model_index=0):
    """Generate Cypher query from natural language question using GraphRAG"""
    logger.info(f"Generating Cypher for question: {question}")
    
    # Check cache first
    cache_key = f"cypher_{question}"
    cached = get_from_cache(cache_key)
    if cached:
        logger.info("Using cached Cypher query")
        return cached

    if not gemini_available:
        logger.error("Gemini API not available")
        return {"error": "gemini_not_available", "message": "Gemini API kullanılamıyor."}
    
    # Get dynamic schema
    dynamic_schema = generate_dynamic_schema()
    
    # Use GraphRAG pipeline if available
    if graphrag_pipeline:
        try:
            # Full GraphRAG pipeline
            graphrag_result = graphrag_pipeline.full_graphrag_pipeline(question, dynamic_schema)
            
            if graphrag_result.get("pipeline_status") == "success":
                # Use enhanced prompt from GraphRAG
                enhanced_prompt = graphrag_result.get("enhanced_prompt", "")
                context_summary = graphrag_result.get("context_summary", "")
                
                prompt = f"""
{enhanced_prompt}

ZORUNLU FORMAT:
{{
  "cypher": "Neo4j Cypher sorgusu - sadece MATCH ve RETURN kullan",
  "description": "GraphRAG context tabanlı açıklama"
}}

ÖNEMLİ KURALLAR:
1. Context bilgilerini kullan
2. Semantic benzerliklerden faydalun
3. ASLA LIMIT kullanma - tüm sonuçları göster
4. Graf yapısını derinlemesine sorgula

JSON YANIT:
"""
                
                logger.info(f"Using GraphRAG enhanced prompt. Context score: {graphrag_result.get('retrieval_score', 0.0):.2f}")
            else:
                # Fallback to basic prompt
                prompt = f"""
{dynamic_schema}

GÖREV: Kullanıcının sorusunu Cypher sorgusuna çevir.
SORU: "{question}"

FORMAT:
{{
  "cypher": "Neo4j Cypher sorgusu",
  "description": "Açıklama"
}}

KURALLAR: LIMIT kullanma, tüm verileri getir.
"""
                
        except Exception as e:
            logger.error(f"GraphRAG pipeline failed: {e}")
            # Fallback to basic approach
            prompt = f"""
{dynamic_schema}

SORU: "{question}"
FORMAT: {{"cypher": "sorgu", "description": "açıklama"}}
KURAL: Tüm verileri getir, LIMIT yok.
"""
    else:
        # Basic prompt without GraphRAG
        prompt = f"""
{dynamic_schema}

GÖREV: Soruyu Cypher'a çevir.
SORU: "{question}"

FORMAT:
{{
  "cypher": "Neo4j Cypher sorgusu - LIMIT kullanma",
  "description": "Türkçe açıklama"
}}
"""

    # Rest of the function remains the same...
    system_prompt = f"Sen bir Neo4j Cypher uzmanısın. GraphRAG context'ini kullan. LIMIT asla kullanma. Sadece geçerli JSON döndür."

    try:
        # Use Gemini API
        response_text = call_gemini_api(prompt, system_prompt)
        
        if not response_text:
            logger.error("Gemini API returned empty response")
            return {
                "cypher": "MATCH (n) RETURN labels(n), count(n) ORDER BY count(n) DESC",
                "description": "Veritabanındaki node türlerini listeler"
            }

        # Parse JSON response
        try:
            import json
            clean_response = response_text.strip()
            if '```json' in clean_response:
                clean_response = clean_response.split('```json')[1].split('```')[0].strip()
            elif '```' in clean_response:
                clean_response = clean_response.split('```')[1].strip()
            
            result = json.loads(clean_response)
            
            if 'cypher' not in result:
                logger.error("Missing 'cypher' field in response")
                return {
                    "cypher": "MATCH (n) RETURN labels(n), count(n) ORDER BY count(n) DESC",
                    "description": "Varsayılan şema sorgusu"
                }
            
            save_to_cache(cache_key, result)
            logger.info(f"Generated Cypher with GraphRAG: {result.get('cypher', '')}")
            return result
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error: {e}")
            return {
                "cypher": "MATCH (n) RETURN labels(n), count(n) ORDER BY count(n) DESC",
                "description": "JSON parse hatası"
            }
            
    except Exception as e:
        logger.error(f"Unexpected error in ask_cypher_json: {str(e)}")
        return {
            "cypher": "MATCH (n) RETURN labels(n), count(n) ORDER BY count(n) DESC",
            "description": "Hata nedeniyle varsayılan sorgu"
        }


def ask_gemma(question, cypher_results, model_index=0):
    """Generate natural language answer using Gemini AI"""
    logger.info(f"Generating answer for question: {question}")
    
    # Check cache
    cache_key = f"answer_{question}_{str(cypher_results)}"
    cached = get_from_cache(cache_key)
    if cached:
        logger.info("Using cached answer")
        return cached

    # Format results better - tüm verileri göster
    formatted_results = "Veri bulunamadı."
    if cypher_results:
        try:
            # Convert any remaining Neo4j objects
            safe_results = []
            for row in cypher_results:
                safe_row = []
                for value in row:
                    safe_row.append(convert_neo4j_value(value))
                safe_results.append(safe_row)
            
            if len(safe_results) == 1 and len(safe_results[0]) == 1:
                formatted_results = f"Sonuç: {safe_results[0][0]}"
            else:
                # Tüm sonuçları göster, sınırlama yok
                formatted_results = f"Toplam {len(safe_results)} sonuç bulundu. Tüm sonuçlar: {safe_results}"
        except Exception as e:
            logger.warning(f"Result formatting error: {e}")
            formatted_results = f"Toplam {len(cypher_results)} sonuç bulundu (formatting issue)."

    # Get relevant history
    history = load_history()
    history_context = ""
    if history:
        for h in history[-2:]:  # Last 2 conversations
            if h.get("question") and h.get("answer"):
                history_context += f"Önceki soru: {h['question']}\nÖnceki cevap: {h['answer'][:100]}...\n\n"

    prompt = f"""Sen Neo4j veritabanı asistanısın. İnceHesap teknolojileri ile güçlendirilmiş bir GraphRAG sistemini kullanıyorsun.

Önceki konuşmalar:
{history_context}

Mevcut soru: {question}
Veritabanı sonuçları: {formatted_results}

GÖREV: Türkçe olarak samimi, yardımsever ve profesyonel bir cevap ver:

1. Sonuçları DETAYLI şekilde açıkla - tüm verileri göster
2. Listeleme sorularında TÜM öğeleri tek tek listele ve numaralandır
3. Sayısal veriler varsa öne çıkar ve tablo halinde göster
4. Graf yapısından bahsederken "node" ve "ilişki" terimlerini kullan
5. Kullanıcı başka ne sorabileceği konusunda ipucu ver
6. Yanıtın UZUN ve KAPSAMLI olsun, veri varsa hepsini göster
7. Her veri kaydını ayrı satırda göster
8. Özellik bilgilerini tam olarak belirt

ÖNEMLİ: 
- Veritabanında ne varsa HEPSINI detaylı olarak açıkla
- Listeleme istendiyse TÜM verileri numara ile göster
- Kısa yanıt verme, detaylı ve kapsamlı ol
- Hiçbir veriyi atlama, hepsini tek tek listele
- "1. XXX, 2. YYY, 3. ZZZ" şeklinde numaralı liste yap

ÖRNEK FORMAT:
MSI markasına ait Anakart ürünleri şunlardır:
1. [Ürün Adı] - [Özellikler]
2. [Ürün Adı] - [Özellikler]
...ve böyle devam et

YANITINIZ:
- Detaylı ve kapsamlı olun  
- TÜM verileri tek tek numaralı listeleyin
- Sayıları güzel formatlayın (örn: 1.558.255 → 1,558,255)  
- Her ürünü ayrı satırda gösterin
- Emoji çok az kullanın
- Eğer veri yoksa alternatif öneriler sunun"""

    system_prompt = """Sen yardımsever bir veritabanı asistanısın. Türkçe cevaplar veriyorsun.
- Kısa ve anlaşılır ol
- Sayıları güzel formatla
- Emoji az kullan
- Veri yoksa alternatif öner"""

    # Use Gemini API
    if gemini_available:
        answer = call_gemini_api(prompt, system_prompt)
        if answer:
            # Post-process answer
            answer = re.sub(r'\n\n+', '\n\n', answer)  # Remove excessive newlines
            answer = answer.replace('$', ' $')  # Better dollar formatting
            
            save_to_cache(cache_key, answer)
            logger.info("Successfully generated answer with Gemini")
            return answer
        else:
            logger.error("Gemini API failed to generate answer")
            return "Üzgünüm, şu anda Gemini API'si ile cevap oluşturamıyorum. Veritabanına bağlanabiliyorum ama AI yanıt üretemiyorum."
    else:
        return "Gemini API kullanılamıyor. Lütfen API anahtarını ve yapılandırmayı kontrol edin."

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
    logger.info(f"Gemini API available: {gemini_available}")
    if gemini_available:
        logger.info(f"Gemini model: {GEMINI_MODEL}")
    
    app.run(debug=debug, host=host, port=port)