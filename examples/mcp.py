# GraphRAG MCP Router - Model Context Protocol command interface.
# Routes agent commands to search, graph traversal, and stats functions.

import os
import sys
import warnings
# Suppress ALL warnings to prevent stdout contamination (breaks MCP protocol)
warnings.filterwarnings('ignore')
import json
import re
import ast
import logging
from typing import Any, Dict, List, Optional
from dataclasses import asdict

# Configure logging to hide noisy INFO/WARNING from stdout (which breaks MCP)
# Redirecting to stderr ensures logs are still visible in Docker/Process logs
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s:%(name)s:%(message)s',
    stream=sys.stderr
)
logger = logging.getLogger(__name__)
# Explicitly silence some common noisy libraries
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("duckdb").setLevel(logging.WARNING)

import json_to_tson
from query_engine import GraphRAGQueryEngine, QueryResult
from duckdb_store import getStore
from graphrag_config import getSettingsForDatabase

# --- Constants ---
DEFAULT_TOP_K = 10
DEFAULT_HOPS = 1
TOGGLE_MINIFIED_OUTPUT = True   # False for pretty-printed JSON (indent=2)
TOGGLE_TSON_OUTPUT = True      # False to bypass TSON tabular compression

# Singleton instances for reuse across calls
_queryEngine: Optional[GraphRAGQueryEngine] = None


def _getQueryEngine() -> GraphRAGQueryEngine:
    # Lazy singleton for query engine using active database from environment.
    global _queryEngine
    if _queryEngine is None:
        dbName = os.environ.get("GRAPHRAG_DATABASE")
        logger.info(f"Initializing query engine for database: {dbName or 'default'}")
        
        settings = getSettingsForDatabase(dbName)
        store = getStore(settings.DUCKDB_PATH)
        _queryEngine = GraphRAGQueryEngine(store)
    return _queryEngine


def _preprocessData(data: Any) -> Any:
    # Process data for JSON/TSON serialization: converts dataclasses, drops Nones, applies TSON.
    if data is None:
        return None
    
    if hasattr(data, '__dataclass_fields__'):
        # Convert dataclass to dict
        return _preprocessData(asdict(data))
    
    if isinstance(data, dict):
        processed = {}
        for k, v in data.items():
            processedValue = _preprocessData(v)
            if processedValue is not None:
                processed[k] = processedValue
        return processed
    
    if isinstance(data, list):
        processedList = [res for item in data if (res := _preprocessData(item)) is not None]
        # Apply TSON compression if enabled and applicable
        if TOGGLE_TSON_OUTPUT:
            return json_to_tson.convertToTSON(processedList)
        return processedList
    
    if isinstance(data, (int, float, str, bool)):
        return data
    
    # Fallback: convert to string
    return str(data)


def _truncateResults(result: Any, topK: int) -> Any:
    # Apply safety limits (topK) to prevent token bloat while preserving reasoning quality.
    if not hasattr(result, '__dataclass_fields__') and not isinstance(result, dict):
        return result
        
    # Convert to dict for easier manipulation
    data = asdict(result) if hasattr(result, '__dataclass_fields__') else result
    
    # Skip truncation if this is a stats response (integers, not lists)
    # or if essential keys are missing
    entities_val = data.get("entities")
    chunks_val = data.get("chunks")
    if not isinstance(entities_val, list) and not isinstance(chunks_val, list):
        return data

    entityLimit = topK
    directRelLimit = min(topK * 3, 30)
    extendedRelLimit = max(topK // 2, 5)
    
    # 1. Truncate Top-Level Entities (only if it's a list)
    if isinstance(data.get("entities"), list):
        data["entities"] = data["entities"][:entityLimit]
        
    # 2. Truncate Evidence (Graph context)
    if data.get("evidence"):
        evidence = data["evidence"]
        if isinstance(evidence.get("directRelationships"), list):
            evidence["directRelationships"] = evidence["directRelationships"][:directRelLimit]
        if isinstance(evidence.get("extendedRelationships"), list):
            evidence["extendedRelationships"] = evidence["extendedRelationships"][:extendedRelLimit]
            
    # 3. Truncate flat relationships list (for backward compatibility)
    if isinstance(data.get("relationships"), list):
        data["relationships"] = data["relationships"][:directRelLimit + extendedRelLimit]
        
    # 4. Remove embeddings and chunkIds from output (agents don't need internal IDs)
    if isinstance(data.get("chunks"), list):
        for chunk in data["chunks"]:
            if isinstance(chunk, dict):
                chunk.pop("embedding", None)
                chunk.pop("chunkId", None)
    
    # 5. Clean up entities - remove internal bookkeeping, keep only semantic data
    if isinstance(data.get("entities"), list):
        for entity in data["entities"]:
            if isinstance(entity, dict):
                entity.pop("id", None)              # UUID - not needed
                entity.pop("description", None)     # GLiNER extraction metadata - not semantic
                entity.pop("sourceChunks", None)    # UUID list - not needed
                
    # 6. Clean up relationships - remove UUIDs, keep semantic triples
    def cleanRelationships(relList):
        if isinstance(relList, list):
            for rel in relList:
                if isinstance(rel, dict):
                    rel.pop("id", None)         # UUID - not needed
                    rel.pop("source", None)     # UUID - we have sourceName
                    rel.pop("target", None)     # UUID - we have targetName
                    rel.pop("weight", None)     # Always 1.0 - noise
    
    # Clean both flat relationships and evidence relationships
    cleanRelationships(data.get("relationships"))
    if data.get("evidence"):
        cleanRelationships(data["evidence"].get("directRelationships"))
        cleanRelationships(data["evidence"].get("extendedRelationships"))
                
    # 7. Update Metadata counts to match final output
    if data.get("metadata"):
        meta = data["metadata"]
        if isinstance(data.get("entities"), list):
            meta["entityCount"] = len(data.get("entities", []))
        if isinstance(data.get("relationships"), list):
            meta["relationshipCount"] = len(data.get("relationships", []))
        if data.get("evidence"):
            if isinstance(data["evidence"].get("directRelationships"), list):
                meta["directRelationshipCount"] = len(data["evidence"].get("directRelationships", []))
            if isinstance(data["evidence"].get("extendedRelationships"), list):
                meta["extendedRelationshipCount"] = len(data["evidence"].get("extendedRelationships", []))
            
    return data


def _formatMcpResponse(data: Any, error: str = None, topK: int = DEFAULT_TOP_K) -> str:
    # Standardized high-signal JSON response for AI agents.
    dumpArgs = {"default": str}
    if TOGGLE_MINIFIED_OUTPUT:
        dumpArgs["separators"] = (',', ':')
    else:
        dumpArgs["indent"] = 2
    
    if error:
        return json.dumps({"error": error}, **dumpArgs)
    
    # Apply agent-specific truncation before preprocessing
    truncatedData = _truncateResults(data, topK)
    processedData = _preprocessData(truncatedData)
    
    return json.dumps(processedData, **dumpArgs)


def _getParams(args: tuple, fieldMap: Dict[str, int]) -> Dict[str, Any]:
    # Extract parameters from either a single dict or positional args.
    if len(args) == 1 and isinstance(args[0], dict):
        return args[0]
    
    params = {}
    for field, index in fieldMap.items():
        if len(args) > index:
            params[field] = args[index]
    return params


def routeCommand(commandString: str) -> str:
    # Parse and route agent command string (search, explore_entity_graph, get_corpus_stats).
    
    # Match pattern: functionName(args)
    match = re.match(r"(\w+)\((.*)\)", commandString, re.DOTALL)
    if not match:
        return _formatMcpResponse(None, error=f"Invalid command format: '{commandString}'")
    
    functionName = match.group(1)
    argsString = match.group(2)
    
    try:
        # Parse arguments safely
        if argsString.strip():
            # Handle JSON-style lowercase booleans/null
            processedArgs = re.sub(r'\btrue\b', 'True', argsString)
            processedArgs = re.sub(r'\bfalse\b', 'False', processedArgs)
            processedArgs = re.sub(r'\bnull\b', 'None', processedArgs)
            
            args = ast.literal_eval(f"({processedArgs})")
            if not isinstance(args, tuple):
                args = (args,)
        else:
            args = ()
    except Exception as e:
        return _formatMcpResponse(None, error=f"Failed to parse arguments: {str(e)}")
    
    # --- Command Registry (Streamlined: 3 tools) ---
    engine = _getQueryEngine()
    
    # Mode mapping for the unified search tool
    MODE_TO_SEARCH_TYPE = {
        "entity_connections": "find_connections",
        "thematic_overview": "explore_thematic", 
        "keyword_lookup": "keyword_search",
    }
    
    # The primary search tool - routes to local/global/fusion based on mode
    if functionName == "search":
        fieldMap = {"query": 0, "mode": 1, "topK": 2}
        params = _getParams(args, fieldMap)
        query = params.get("query")
        
        if not query or not isinstance(query, str):
            return _formatMcpResponse(None, error="search expects a 'query' string")
        
        mode = params.get("mode", "entity_connections")
        searchType = MODE_TO_SEARCH_TYPE.get(mode, "find_connections")
        topK = params.get("topK", DEFAULT_TOP_K)
        
        result = engine.search(query, searchType=searchType, topK=topK)
        return _formatMcpResponse(result, topK=topK)
    
    # Direct graph traversal from a known entity
    elif functionName == "explore_entity_graph":
        fieldMap = {"entityName": 0, "hops": 1}
        params = _getParams(args, fieldMap)
        entityName = params.get("entityName")
        
        if not entityName or not isinstance(entityName, str):
            return _formatMcpResponse(None, error="explore_entity_graph expects an 'entityName' string")
        
        hops = min(params.get("hops", DEFAULT_HOPS), 3)  # Cap at 3 to prevent explosion
        result = engine.getEntityNeighborhood(entityName, hops=hops)
        return _formatMcpResponse(result)
    
    # Database health and scale check
    elif functionName == "get_corpus_stats":
        dbName = os.environ.get("GRAPHRAG_DATABASE")
        settings = getSettingsForDatabase(dbName)
        store = getStore(settings.DUCKDB_PATH)
        stats = store.getCorpusStats()
        return _formatMcpResponse(stats)
    
    else:
        return _formatMcpResponse(None, error=f"Unknown command: {functionName}. Available: search, explore_entity_graph, get_corpus_stats")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(_formatMcpResponse(None, error="No command provided"))
        sys.exit(1)
    
    # Concatenate all arguments in case shell split the command string
    commandString = " ".join(sys.argv[1:])
    print(routeCommand(commandString))
