"""
GraphRAG Context Manager
Graf yapısından context çıkarma ve yönetme
"""
import logging
from typing import List, Dict, Any, Optional, Tuple
import json

logger = logging.getLogger(__name__)

class GraphContextManager:
    """Graf context yönetimi"""
    
    def __init__(self, driver):
        self.driver = driver
    
    def extract_entity_context(self, entities: List[str], depth: int = 2) -> Dict[str, Any]:
        """DYNAMIC entity context extraction with comprehensive property matching"""
        try:
            # COMPLETELY DYNAMIC approach - no hardcoded property names
            context_query = """
            // Find entities by ANY text property match
            MATCH (start)
            WHERE any(prop IN keys(start) WHERE 
                any(entity IN $entities WHERE 
                    toString(start[prop]) CONTAINS entity OR 
                    entity CONTAINS toString(start[prop])
                )
            )
            
            // Get comprehensive context around these entities
            OPTIONAL MATCH path = (start)-[r*1..3]-(connected)
            WHERE length(path) <= $depth
            
            WITH start, connected, r, path,
                 // Calculate relevance score
                 reduce(score = 0, entity IN $entities | 
                    score + reduce(prop_score = 0, prop IN keys(start) |
                        prop_score + CASE 
                            WHEN toString(start[prop]) CONTAINS entity THEN 10
                            WHEN entity CONTAINS toString(start[prop]) THEN 5  
                            ELSE 0 
                        END
                    )
                 ) AS relevance_score
            
            WITH start, 
                 collect({
                     connected_node: connected,
                     connected_properties: properties(connected),
                     connected_labels: labels(connected),
                     relationship_chain: [rel IN r | {
                         type: type(rel),
                         properties: properties(rel)
                     }],
                     path_length: length(path),
                     relevance: relevance_score
                 })[..20] AS context_nodes,
                 relevance_score
            
            // Find similar entities based on shared property values
            OPTIONAL MATCH (similar)
            WHERE similar <> start
            AND any(start_prop IN keys(start) WHERE 
                any(sim_prop IN keys(similar) WHERE 
                    toString(start[start_prop]) = toString(similar[sim_prop]) AND
                    toString(start[start_prop]) <> '' AND
                    toString(start[start_prop]) IS NOT NULL
                )
            )
            
            WITH start, context_nodes, relevance_score,
                 collect({
                     similar_node: similar,
                     similar_properties: properties(similar),
                     similar_labels: labels(similar),
                     shared_values: [prop IN keys(start) WHERE 
                         any(sim_prop IN keys(similar) WHERE 
                             toString(start[prop]) = toString(similar[sim_prop])
                         ) | {
                             property: prop, 
                             value: toString(start[prop])
                         }
                     ][..5]
                 })[..10] AS similar_entities
            
            RETURN {
                central_entities: collect({
                    node: start,
                    properties: properties(start),
                    labels: labels(start),
                    relevance_score: relevance_score,
                    context_connections: context_nodes,
                    similar_entities: similar_entities,
                    context_summary: {
                        total_connections: size(context_nodes),
                        total_similar: size(similar_entities),
                        centrality_score: relevance_score + size(context_nodes) * 2
                    }
                }),
                query_entities: $entities,
                extraction_depth: $depth,
                total_context_size: reduce(total = 0, entity IN collect(start) | 
                    total + size(context_nodes) + size(similar_entities)
                )
            } AS comprehensive_context
            """
            
            with self.driver.session() as session:
                result = session.run(context_query, entities=entities, depth=depth)
                record = result.single()
                
                if record:
                    return record["comprehensive_context"]
                return {"central_entities": [], "query_entities": entities}
                
        except Exception as e:
            logger.error(f"Dynamic entity context extraction failed: {e}")
            return {"central_entities": [], "query_entities": entities, "error": str(e)}
    
    def get_node_neighborhood(self, node_id: str, radius: int = 1) -> Dict[str, Any]:
        """Node'un komşularını ve ilişkilerini getir"""
        try:
            neighborhood_query = f"""
            MATCH (center {{id: $node_id}})
            MATCH (center)-[r*1..{radius}]-(neighbor)
            RETURN {{
                center: center,
                neighbors: collect(DISTINCT neighbor),
                relationships: collect(DISTINCT r),
                patterns: [
                    (center)-[r1]-(n1) | {{
                        relationship_type: type(r1),
                        neighbor_type: labels(n1)[0],
                        properties: keys(r1)
                    }}
                ]
            }} AS neighborhood
            """
            
            with self.driver.session() as session:
                result = session.run(neighborhood_query, node_id=node_id)
                record = result.single()
                
                return record["neighborhood"] if record else {}
                
        except Exception as e:
            logger.error(f"Neighborhood extraction failed: {e}")
            return {}
    
    def find_connection_paths(self, start_node: str, end_node: str, max_depth: int = 4) -> List[Dict]:
        """İki node arasındaki bağlantı yollarını bul"""
        try:
            path_query = f"""
            MATCH path = shortestPath((start)-[*1..{max_depth}]-(end))
            WHERE start.name = $start_node AND end.name = $end_node
            RETURN {{
                path: path,
                length: length(path),
                nodes: [n IN nodes(path) | {{
                    labels: labels(n),
                    properties: properties(n)
                }}],
                relationships: [r IN relationships(path) | {{
                    type: type(r),
                    properties: properties(r)
                }}]
            }} AS connection_path
            LIMIT 5
            """
            
            with self.driver.session() as session:
                result = session.run(path_query, 
                                   start_node=start_node, 
                                   end_node=end_node)
                
                return [record["connection_path"] for record in result]
                
        except Exception as e:
            logger.error(f"Connection path finding failed: {e}")
            return []
    
    def get_schema_context(self) -> Dict[str, Any]:
        """Veritabanı şema context'i"""
        try:
            schema_query = """
            CALL db.schema.visualization()
            YIELD nodes, relationships
            RETURN {
                node_types: [n IN nodes | {
                    label: n.label,
                    properties: n.properties
                }],
                relationship_types: [r IN relationships | {
                    type: r.type,
                    properties: r.properties,
                    from: r.from,
                    to: r.to
                }]
            } AS schema_context
            """
            
            with self.driver.session() as session:
                result = session.run(schema_query)
                record = result.single()
                
                return record["schema_context"] if record else {}
                
        except Exception as e:
            logger.warning(f"Schema context extraction failed, using fallback: {e}")
            return self._get_fallback_schema_context()
    
    def _get_fallback_schema_context(self) -> Dict[str, Any]:
        """Fallback şema context'i"""
        try:
            # Basit şema bilgileri
            node_query = "MATCH (n) RETURN DISTINCT labels(n)[0] AS label, count(n) AS count"
            rel_query = "MATCH ()-[r]->() RETURN DISTINCT type(r) AS type, count(r) AS count"
            
            with self.driver.session() as session:
                nodes = list(session.run(node_query))
                rels = list(session.run(rel_query))
                
                return {
                    "node_types": [{"label": r["label"], "count": r["count"]} for r in nodes],
                    "relationship_types": [{"type": r["type"], "count": r["count"]} for r in rels]
                }
                
        except Exception as e:
            logger.error(f"Fallback schema context failed: {e}")
            return {"node_types": [], "relationship_types": []}

def merge_contexts(semantic_context: List[Dict], graph_context: Dict[str, Any]) -> Dict[str, Any]:
    """Semantic ve graph context'lerini birleştir"""
    try:
        merged = {
            "semantic_matches": semantic_context,
            "graph_structure": graph_context,
            "combined_entities": [],
            "relevance_score": 0.0
        }
        
        # Semantic matches'den entities çıkar
        for match in semantic_context:
            if "node" in match:
                merged["combined_entities"].append({
                    "entity": match["node"],
                    "similarity": match.get("similarity", 0.0),
                    "source": "semantic"
                })
        
        # Graph context'den entities ekle
        if "related_nodes" in graph_context:
            for node in graph_context["related_nodes"]:
                merged["combined_entities"].append({
                    "entity": node,
                    "similarity": 0.5,  # Default graph relevance
                    "source": "graph"
                })
        
        # Relevance score hesapla
        if merged["combined_entities"]:
            avg_similarity = sum(e["similarity"] for e in merged["combined_entities"]) / len(merged["combined_entities"])
            merged["relevance_score"] = avg_similarity
        
        return merged
        
    except Exception as e:
        logger.error(f"Context merging failed: {e}")
        return {"semantic_matches": [], "graph_structure": {}, "combined_entities": [], "relevance_score": 0.0}
