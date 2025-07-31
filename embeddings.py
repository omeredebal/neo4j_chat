"""
Vector Embeddings ve Semantic Search modülü
GraphRAG mimarisi için vector tabanlı arama desteği
"""
import logging
import numpy as np
from typing import List, Dict, Any, Optional
import google.generativeai as genai
from cache import get_from_cache, save_to_cache

logger = logging.getLogger(__name__)

class EmbeddingManager:
    """Vector embeddings yönetimi"""
    
    def __init__(self, api_key: str, model: str = "models/embedding-001"):
        self.api_key = api_key
        self.model = model
        self.available = False
        
        try:
            genai.configure(api_key=api_key)
            self.available = True
            logger.info("Embedding manager initialized successfully")
        except Exception as e:
            logger.error(f"Embedding manager initialization failed: {e}")
    
    def get_text_embedding(self, text: str) -> Optional[List[float]]:
        """Metin için embedding oluştur"""
        if not self.available:
            return None
            
        # Cache kontrolü
        cache_key = f"embedding_{hash(text)}"
        cached = get_from_cache(cache_key)
        if cached:
            return cached
        
        try:
            result = genai.embed_content(
                model=self.model,
                content=text,
                task_type="semantic_similarity"
            )
            
            embedding = result['embedding']
            save_to_cache(cache_key, embedding)
            return embedding
            
        except Exception as e:
            logger.error(f"Embedding generation failed: {e}")
            return None
    
    def calculate_similarity(self, emb1: List[float], emb2: List[float]) -> float:
        """Cosine similarity hesapla"""
        try:
            vec1 = np.array(emb1)
            vec2 = np.array(emb2)
            
            dot_product = np.dot(vec1, vec2)
            norm1 = np.linalg.norm(vec1)
            norm2 = np.linalg.norm(vec2)
            
            if norm1 == 0 or norm2 == 0:
                return 0.0
                
            return float(dot_product / (norm1 * norm2))
            
        except Exception as e:
            logger.error(f"Similarity calculation failed: {e}")
            return 0.0
    
    def semantic_search(self, driver, query_text: str, limit: int = 10) -> List[Dict]:
        """Semantic search with DYNAMIC property discovery"""
        if not self.available:
            logger.warning("Embedding manager not available for semantic search")
            return []
        
        query_embedding = self.get_text_embedding(query_text)
        if not query_embedding:
            logger.warning("Could not generate embedding for query")
            return []
        
        try:
            # DYNAMIC APPROACH: Tüm node'ları ve property'lerini tara
            cypher_query = """
            MATCH (n) 
            WHERE any(prop IN keys(n) WHERE 
                toString(n[prop]) <> '' AND 
                toString(n[prop]) IS NOT NULL
            )
            WITH n, 
                 [prop IN keys(n) WHERE toString(n[prop]) <> '' | 
                  prop + ': ' + toString(n[prop])] AS text_parts,
                 labels(n) AS node_labels
            WITH n, node_labels, 
                 reduce(text = '', part IN text_parts | text + ' ' + part) AS searchable_text
            WHERE size(trim(searchable_text)) > 5
            RETURN elementId(n) AS id, node_labels, searchable_text, 
                   properties(n) AS all_properties
            LIMIT 1000
            """
            
            with driver.session() as session:
                result = session.run(cypher_query)
                candidates = []
                
                for record in result:
                    node_text = record["searchable_text"]
                    node_embedding = self.get_text_embedding(node_text)
                    
                    if node_embedding:
                        similarity = self.calculate_similarity(query_embedding, node_embedding)
                        
                        candidates.append({
                            'id': record["id"],
                            'labels': record["node_labels"],
                            'text': node_text,
                            'properties': record["all_properties"], 
                            'similarity': similarity
                        })
                
                # Similarity'ye göre sırala
                candidates.sort(key=lambda x: x['similarity'], reverse=True)
                
                logger.info(f"Semantic search found {len(candidates)} candidates, returning top {limit}")
                return candidates[:limit]
                
        except Exception as e:
            logger.error(f"Semantic search failed: {e}")
            return []

def create_semantic_index(driver, embedding_manager: EmbeddingManager):
    """Neo4j'de semantic index oluştur"""
    if not embedding_manager.available:
        logger.warning("Embeddings not available, skipping semantic index")
        return False
    
    try:
        # Vector index oluştur (Neo4j 5.0+)
        index_query = """
        CREATE VECTOR INDEX semantic_nodes IF NOT EXISTS
        FOR (n:Node) ON (n.embedding)
        OPTIONS {
            indexConfig: {
                `vector.dimensions`: 768,
                `vector.similarity_function`: 'cosine'
            }
        }
        """
        
        with driver.session() as session:
            session.run(index_query)
            logger.info("Semantic vector index created")
            return True
            
    except Exception as e:
        logger.error(f"Semantic index creation failed: {e}")
        return False

def semantic_search(driver, query: str, embedding_manager: EmbeddingManager, k: int = 5) -> List[Dict]:
    """Semantic search ile benzer node'ları bul"""
    if not embedding_manager.available:
        return []
    
    try:
        # Query embedding oluştur
        query_embedding = embedding_manager.get_text_embedding(query)
        if not query_embedding:
            return []
        
        # Vector similarity search
        search_query = """
        MATCH (n)
        WHERE n.embedding IS NOT NULL
        WITH n, gds.similarity.cosine(n.embedding, $query_embedding) AS similarity
        WHERE similarity > 0.7
        RETURN n, similarity
        ORDER BY similarity DESC
        LIMIT $k
        """
        
        with driver.session() as session:
            result = session.run(search_query, 
                               query_embedding=query_embedding, 
                               k=k)
            
            return [{"node": record["n"], "similarity": record["similarity"]} 
                   for record in result]
                   
    except Exception as e:
        logger.error(f"Semantic search failed: {e}")
        return []
