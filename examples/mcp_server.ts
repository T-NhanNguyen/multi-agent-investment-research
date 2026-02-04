/**
 * GraphRAG MCP Server - Model Context Protocol interface for knowledge graph queries.
 * 
 * Exposes GraphRAG tools to AI agents via the MCP standard:
 * - search: Unified search with mode-based strategies
 * - explore_entity_graph: Graph traversal from a known entity
 * - get_corpus_stats: Database health and scale statistics
 */

import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
    ListToolsRequestSchema,
    CallToolRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";
import { exec } from "child_process";
import { promisify } from "util";

const execAsync = promisify(exec);

const server = new Server({
    name: "graphrag-mcp",
    version: "1.0.0"
}, {
    capabilities: { tools: {} }
});

const tools = [
    {
        name: "search",
        description: "Search the GraphRAG knowledge base with THREE distinct modes:\n\n**CRITICAL: For ticker symbols (ASTS, RKLB, NBIS) or acronyms, ALWAYS use 'keyword_lookup' FIRST.**\nSemantic search (entity_connections/thematic_overview) can MISS exact ticker matches.\n\nWorkflow:\n1. Ticker/Acronym Query → Use 'keyword_lookup' to find raw mentions\n2. If found → Extract entity names from results\n3. Then use 'entity_connections' or 'thematic_overview' with full entity names for deeper analysis\n\nMode Selection Guide:\n- 'keyword_lookup': Direct BM25 retrieval for EXACT terms (tickers, acronyms, specific names)\n  → Returns: Raw text chunks containing the literal search term\n  → Use for: ASTS, NYSE:RKLB, \"Direct-to-Cell\", specific product names\n\n- 'entity_connections': Find entities and their knowledge graph relationships\n  → Returns: Entities + relationships + supporting chunks\n  → Use for: Company relationships, competitive landscape, partnerships\n  → Example: After finding 'AST SpaceMobile' via keyword_lookup, search 'AST SpaceMobile competitors partners'\n\n- 'thematic_overview': High-level patterns and trends across corpus\n  → Returns: Broad thematic context\n  → Use for: Industry trends, macro narratives, sector analysis\n  → Example: 'satellite telecommunications market trends'",
        inputSchema: {
            type: "object",
            properties: {
                query: { 
                    type: "string", 
                    description: "Search query string" 
                },
                mode: { 
                    type: "string", 
                    enum: ["entity_connections", "thematic_overview", "keyword_lookup"],
                    description: "**IMPORTANT**: Use 'keyword_lookup' for ticker symbols and acronyms. Use 'entity_connections' for relationships. Use 'thematic_overview' for broad patterns. Default: 'entity_connections'" 
                },
                topK: { 
                    type: "integer", 
                    description: "Number of results (default: 10)" 
                }
            },
            required: ["query"]
        }
    },
    {
        name: "explore_entity_graph",
        description: "Traverse the knowledge graph starting from a specific entity. Returns the entity, its direct connections (other entities), and the relationships between them. Use this to build reasoning chains or verify facts about a known entity.",
        inputSchema: {
            type: "object",
            properties: {
                entityName: { 
                    type: "string", 
                    description: "Exact name of the entity to explore (e.g., 'Microsoft', 'Vistra')" 
                },
                hops: { 
                    type: "integer", 
                    description: "How many relationship hops to traverse (default: 1, max: 3)" 
                }
            },
            required: ["entityName"]
        }
    },
    {
        name: "get_corpus_stats",
        description: "Get statistics about the indexed knowledge base. Returns counts of documents, chunks, entities, and relationships. Use for corpus health checks or to understand the scale of available data.",
        inputSchema: {
            type: "object",
            properties: {}
        }
    }
];

server.setRequestHandler(ListToolsRequestSchema, async () => ({ tools }));

server.setRequestHandler(CallToolRequestSchema, async (request) => {
    const { name, arguments: args } = request.params;

    // Build Python command string
    // Convert JS object to Python-parseable format
    const pythonArgs = JSON.stringify(args || {}).replace(/"/g, "'");
    const pythonCmd = `${name}(${pythonArgs})`;

    try {
        // Execute mcp.py with the command
        // Using double quotes for outer shell argument to allow inner single quotes
        const { stdout, stderr } = await execAsync(`python mcp.py "${pythonCmd}"`);

        if (stderr && stderr.trim()) {
            // Some libraries write to stderr on success, check if stdout is empty
            if (!stdout.trim()) {
                return { content: [{ type: "text", text: stderr }], isError: true };
            }
        }

        return { content: [{ type: "text", text: stdout }] };
    } catch (error: any) {
        return { content: [{ type: "text", text: error.message }], isError: true };
    }
});

const transport = new StdioServerTransport();
await server.connect(transport);
console.error("GraphRAG MCP Server started");
