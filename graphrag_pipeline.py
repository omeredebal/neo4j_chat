"""
GraphRAG Pipeline - Tam GraphRAG implementasyonu
Vector + Graph Hybrid Retrieval & Generation
"""
import logging
import re
from typing import List, Dict, Any, Optional, Tuple
from embeddings import EmbeddingManager, semantic_search
from context_manager import GraphContextManager, merge_contexts
from cache import get_from_cache, save_to_cache

logger = logging.getLogger(__name__)

class GraphRAGPipeline:
    """Tam GraphRAG pipeline"""
    
    def __init__(self, driver, embedding_manager: EmbeddingManager):
        self.driver = driver
        self.embedding_manager = embedding_manager
        self.context_manager = GraphContextManager(driver)
        
    def extract_entities(self, text: str) -> List[str]:
        """Metinden entity'leri çıkar"""
        try:
            # Basit regex-based entity extraction
            # Büyük harfle başlayan kelimeler (proper nouns)
            entities = re.findall(r'\b[A-ZÜĞŞÇÖ][a-züğşçöıA-ZÜĞŞÇÖI]+\b', text)
            
            # Tekil hale getir ve temizle
            entities = list(set(entities))
            entities = [e for e in entities if len(e) > 2]  # Çok kısa olanları filtrele
            
            logger.info(f"Extracted entities: {entities}")
            return entities[:10]  # Max 10 entity
            
        except Exception as e:
            logger.error(f"Entity extraction failed: {e}")
            return []
    
    def hybrid_retrieval(self, question: str, k: int = 5) -> Dict[str, Any]:
        """Hybrid retrieval: Semantic + Graph-based"""
        try:
            # 1. Entity extraction
            entities = self.extract_entities(question)
            
            # 2. Semantic search
            semantic_results = semantic_search(
                self.driver, question, self.embedding_manager, k
            )
            
            # 3. Graph-based context
            graph_context = {}
            if entities:
                graph_context = self.context_manager.extract_entity_context(entities, depth=2)
            
            # 4. Merge contexts
            combined_context = merge_contexts(semantic_results, graph_context)
            
            return {
                "entities": entities,
                "semantic_results": semantic_results,
                "graph_context": graph_context,
                "combined_context": combined_context,
                "retrieval_score": combined_context.get("relevance_score", 0.0)
            }
            
        except Exception as e:
            logger.error(f"Hybrid retrieval failed: {e}")
            return {"entities": [], "semantic_results": [], "graph_context": {}, "combined_context": {}}
    
    def context_aware_cypher_generation(self, question: str, context: Dict[str, Any], schema_info: str) -> Dict[str, Any]:
        """Context-aware Cypher sorgu üretimi"""
        try:
            # Context'ten önemli bilgileri çıkar
            context_summary = self._summarize_context(context)
            
            enhanced_prompt = f"""
{schema_info}

CONTEXT INFORMATION:
{context_summary}

DETECTED ENTITIES: {context.get('entities', [])}
SEMANTIC RELEVANCE: {context.get('retrieval_score', 0.0):.2f}

GÖREV: Context bilgilerini kullanarak soruyu Cypher sorgusuna çevir.

USER QUESTION: "{question}"

ÖNEMLİ:
- Context'teki entity'leri kullan
- Semantic olarak benzer node'ları öncelikle
- Graf yapısından faydalanarak derinlemesine sorgula
- LIMIT kullanma, tüm ilgili verileri getir

JSON FORMAT:
{{
  "cypher": "context-aware Cypher query",
  "description": "Context tabanlı açıklama",
  "context_used": "kullanılan context bilgileri"
}}
"""
            
            return {"prompt": enhanced_prompt, "context_summary": context_summary}
            
        except Exception as e:
            logger.error(f"Context-aware Cypher generation failed: {e}")
            return {"prompt": "", "context_summary": ""}
    
    def _summarize_context(self, context: Dict[str, Any]) -> str:
        """Context'i özetleyerek prompt'a dahil et"""
        try:
            summary_parts = []
            
            # Semantic matches
            semantic_results = context.get("semantic_results", [])
            if semantic_results:
                summary_parts.append(f"Semantic matches: {len(semantic_results)} similar nodes found")
                for match in semantic_results[:3]:  # Top 3
                    node = match.get("node", {})
                    similarity = match.get("similarity", 0.0)
                    summary_parts.append(f"  - Node: {node} (similarity: {similarity:.2f})")
            
            # Graph context
            graph_context = context.get("graph_context", {})
            if graph_context:
                central_nodes = graph_context.get("central_nodes", [])
                related_nodes = graph_context.get("related_nodes", [])
                
                if central_nodes:
                    summary_parts.append(f"Central nodes: {len(central_nodes)} found")
                if related_nodes:
                    summary_parts.append(f"Related nodes: {len(related_nodes)} found")
            
            # Combined entities
            combined_context = context.get("combined_context", {})
            entities = combined_context.get("combined_entities", [])
            if entities:
                summary_parts.append(f"Combined entities: {len(entities)} total")
            
            return "\n".join(summary_parts) if summary_parts else "No specific context found"
            
        except Exception as e:
            logger.error(f"Context summarization failed: {e}")
            return "Context summarization failed"
    
    def generate_contextual_answer(self, question: str, results: List, context: Dict[str, Any], cypher: str) -> str:
        """Context-aware cevap üretimi"""
        try:
            # Results'ı formatla
            formatted_results = "Veri bulunamadı."
            if results:
                if len(results) == 1 and len(results[0]) == 1:
                    formatted_results = f"Sonuç: {results[0][0]}"
                else:
                    formatted_results = f"Toplam {len(results)} sonuç bulundu. Detaylar: {results}"
            
            # Context bilgilerini ekle
            context_info = self._summarize_context(context)
            retrieval_score = context.get("retrieval_score", 0.0)
            
            enhanced_prompt = f"""
GRAPHRAG CONTEXT-AWARE RESPONSE:

Soru: {question}
Cypher Sorgusu: {cypher}
Sonuçlar: {formatted_results}

CONTEXT INFORMATION:
{context_info}
Retrieval Confidence: {retrieval_score:.2f}

GÖREV: Context bilgilerini kullanarak DETAYLI ve KAPSAMLI cevap ver:

1. Sonuçları TAMAMEN listele - hiçbirini atlama
2. Context'ten gelen semantic benzerliklerden bahset
3. Graf yapısındaki ilişkileri açıkla
4. Her veriyi numaralı liste halinde göster
5. Kullanıcının sorusunu tam olarak yanıtla

ÖRNEK FORMAT:
GraphRAG analizi sonucunda bulunan veriler:

1. [Veri 1] - [Context açıklaması]
2. [Veri 2] - [İlişki bilgisi]
...

Graf yapısı analizi: [Context'ten çıkarılan ilişkiler]
Semantic benzerlik: [Benzer kavramlar]

YANITINIZ (Türkçe, detaylı, kapsamlı):
"""
            
            return enhanced_prompt
            
        except Exception as e:
            logger.error(f"Contextual answer generation failed: {e}")
            return f"Context-aware cevap üretilemedi: {str(e)}"
    
    def full_graphrag_pipeline(self, question: str, schema_info: str) -> Dict[str, Any]:
        """Tam GraphRAG pipeline"""
        try:
            logger.info(f"Starting GraphRAG pipeline for: {question}")
            
            # Cache kontrolü
            cache_key = f"graphrag_{hash(question + schema_info)}"
            cached = get_from_cache(cache_key)
            if cached:
                logger.info("Using cached GraphRAG result")
                return cached
            
            # 1. Hybrid Retrieval
            retrieval_result = self.hybrid_retrieval(question)
            
            # 2. Context-aware Cypher Generation
            cypher_context = self.context_aware_cypher_generation(
                question, retrieval_result, schema_info
            )
            
            pipeline_result = {
                "question": question,
                "entities": retrieval_result.get("entities", []),
                "retrieval_context": retrieval_result,
                "cypher_context": cypher_context,
                "context_summary": cypher_context.get("context_summary", ""),
                "enhanced_prompt": cypher_context.get("prompt", ""),
                "retrieval_score": retrieval_result.get("retrieval_score", 0.0),
                "pipeline_status": "success"
            }
            
            # Cache successful result
            save_to_cache(cache_key, pipeline_result)
            
            logger.info(f"GraphRAG pipeline completed with score: {pipeline_result['retrieval_score']:.2f}")
            return pipeline_result
            
        except Exception as e:
            logger.error(f"GraphRAG pipeline failed: {e}")
            return {
                "question": question,
                "entities": [],
                "retrieval_context": {},
                "context_summary": f"Pipeline failed: {str(e)}",
                "enhanced_prompt": "",
                "retrieval_score": 0.0,
                "pipeline_status": "failed",
                "error": str(e)
            }
