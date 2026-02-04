## Setup

### 1. Clone the repo

`git clone https://github.com/T-NhanNguyen/graphRAG-LlamaIndex.git`

### 2. Copy .env.example to .env

`cp .env.example .env`

### 3. Edit .env and set their data directory

> GRAPHRAG_DATA_DIR=/path/to/your/documents

(You can copy and paste the windows address directly)

### 4. Shell Alias Setup (Optional but Recommended for ease of use)

To simplify command usage, load the appropriate alias file for your shell:

1. Edit the `graphrag-alias.sh` and `graphrag-alias.ps1` to replace the placeholder path
   with your correct path to this repo
2. Copy the alias over to the bottom of your bashrc and $PROFILE
3. source `.graphrag-alias.sh` in your linux wsl, and `.graphrag-alias.ps1` in your powershell

**For WSL/Bash:**

```bash
# Append the source command to the end of .bashrc
# (Replace the path with your actual WSL project path)
echo "source /graphRAG-LlamaIndex/.graphrag-alias.sh" >> ~/.bashrc
# Source it
source ~/.bashrc
```

**For PowerShell:**

```powershell
# 1. Create the profile file (and its folder if missing)
New-Item -Path $PROFILE -Type File -Force
# 2. Open it for editing
code $PROFILE
# 3. copy the alias to the bottom of your $PROFILE
. "E:\ai-workspace\projects\graphRAG-LlamaIndex\.graphrag-alias.ps1"
# 4. Restart terminal
```

This enables you to use `graphrag <command>` instead of the full `docker compose run --rm graphrag python graphrag_cli.py <command>`. Because you need this repo around to use it, doing it like this is easier to manage.

**Important Note for WSL Users:**

- The alias automatically sets `GRAPHRAG_REGISTRY_DIR` to your Windows user profile's .graphrag folder.
- This ensures WSL uses the same registry as PowerShell (your Windows user profile)
- Without this, WSL would create a separate registry in `/home/<username>/.graphrag`, causing a "split-brain" issue

### 5. Create a database

```
docker compose run --rm graphrag python graphrag_cli.py start my-docs \
 --input /app/data/<subfolder>
```

Your .env settings `GRAPHRAG_DATA_DIR=E:/ai-workspace/analysis-docs` maps to docker as `/app/data`,
so you Just replace SUBFOLDER with whatever folder exists in your analysis-docs directory!

```
E:/ai-workspace/analysis-docs/
├── converted_md/
│   └── Documents/          ← Your investment docs
├── research-papers/        ← Another collection
└── quarterly-reports/      ← Another collection

# Investment analysis (your current one)
docker compose run --rm graphrag python graphrag_cli.py start investment-analysis `
  --input /app/data/converted_md/Documents

# Research papers
docker compose run --rm graphrag python graphrag_cli.py start research `
  --input /app/data/research-papers

# Quarterly reports
docker compose run --rm graphrag python graphrag_cli.py start quarterly `
  --input /app/data/quarterly-reports
```

### 5.5 Moving database

**Adding an entry to ~/.graphrag/registry.json and pointing to your existing file**:

```
docker compose run --rm graphrag python graphrag_cli.py register my-database \
  --db-path /app/.DuckDB/graphrag.duckdb \
  --input /app/data/<located-in-another-subfolder>
```

- Immediate Access: You can now run status, search, or index using that name (e.g., graphrag search my-database "...").
- No Data Loss: It doesn't move or modify your actual .duckdb file; it just "bookmarks" it for the CLI.

### 6. Index and query

TIP: Search keywords first then use the output to search for thematic or connection with better yields... I may look into a feature for Recurssion-LLM (Local) to automate this...

```
docker compose run --rm graphrag python graphrag_cli.py start my-database --input /app/input
docker compose run --rm graphrag python graphrag_cli.py index my-database
docker compose run --rm graphrag python graphrag_cli.py search my-database "query"
docker compose run --rm graphrag python graphrag_cli.py list
```

Guide for Window Users:

- Opening the folder in File Expolorer:
  `explorer $env:USERPROFILE\.graphrag`
- View the registry file:
  `cat $env:USERPROFILE\.graphrag\registry.json`
- See all registered databases:
  `ls $env:USERPROFILE\.graphrag\databases`

### If you want to physically move it to the new "Managed" folder:

- Create a folder for your database in your defined `GRAPHRAG_DATA_DIR`
- Move the .duckdb file into that folder and rename it to match
- Register it:

```
docker compose run --rm graphrag python graphrag_cli.py register my-project \
  --db-path /app/data/my-project/my-project.duckdb
```

This design should be portable. it uses Path.home() in `workspace_config.py` to automatically resolves to:

- C:\Users\<username> on Windows
- /home/<username> on Linux
- /Users/<username> on macOS

## Parent Directory & Design Limitations

Because this is designed with docker container for portability, the current setup with a single hardcoded mount `/app/input` means all databases share the same input directory. So my advice is to make a folder somewhere on your PC and organize multiple different topics and interests input folder within.

If you need complete flexibility without predefined slots, look into creating a docker-compose.override to establish a multi drive support.

## Command Cheat-sheet

```
graphrag start <db> [--source <path>]    # Create database/update a database's source folder
graphrag index <db> [--prune]            # Index documents
graphrag search <db> <query> [--type]    # Query knowledge graph
graphrag list                            # List all databases
graphrag status <db>                     # Show stats
graphrag delete <db>                     # Remove database
graphrag register <db> --db-path /root/.graphrag/<index-vault>/<path>  # Import existing .duckdb.
# If the host folder is C:\Users\name\.graphrag
# you're replacing that section with /root/.graphrag.
```

## Troubleshooting

### WSL Search Returns No Results (PowerShell Works)

**Symptom**: Running the same search command in WSL returns empty results, but PowerShell returns data.

**Cause**: Docker Compose resolves `~` differently in each environment:

- PowerShell: `~` → `C:\Users\<username>` ✓
- WSL: `~` → `/home/<username>` (wrong location)

**Solution**: Use the provided alias files which automatically set the correct registry path, or manually export:

```bash
export GRAPHRAG_REGISTRY_DIR=/mnt/c/Users/<your-windows-username>/.graphrag
```

### MCP Config Path Format Error

**Symptom**: The MCP server fails to initialize with an error like:

```
Error: docker: open /mnt/e/.../.env: The system cannot find the path specified.
```

**Cause**: Your `mcp_config.json` uses WSL-style paths (`/mnt/e/...`) but Docker Desktop for Windows requires Windows-style paths (`E:/...`). This happens when your AI agent runs from a different environment than where the MCP server executes.

| Environment | Path Format      | Example                    |
| ----------- | ---------------- | -------------------------- |
| WSL/Linux   | `/mnt/e/project` | Used by Gemini CLI in WSL  |
| Windows     | `E:/project`     | Required by Docker Desktop |

**Solution**: Update your `mcp_config.json` volume mounts to use Windows paths:

```json
// Before (WSL paths - won't work)
"-v", "/mnt/e/ai-workspace/projects/graphRAG-LlamaIndex:/app",
"--env-file", "/mnt/e/ai-workspace/projects/graphRAG-LlamaIndex/.env",

// After (Windows paths - works)
"-v", "E:/ai-workspace/projects/graphRAG-LlamaIndex:/app",
"--env-file", "E:/ai-workspace/projects/graphRAG-LlamaIndex/.env",
```

Also ensure the registry directory is mounted:

```json
"-v", "C:/Users/<username>/.graphrag:/root/.graphrag",
```
