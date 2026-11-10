# Codebase RAG Assistant — Architecture

```mermaid
flowchart TD
    UI[React + Vite UI] -->|HTTP localhost| API[FastAPI local API]
    API --> SAFE[Repository path guard + safe inspection]
    SAFE --> TS[Tree-sitter chunking]
    TS --> EMB[Sentence Transformers]
    EMB --> DB[(ChromaDB local index)]
    API --> SEARCH[Semantic search]
    SEARCH --> RAG[RAG context + evidence validator]
    RAG --> OLLAMA[Ollama + Qwen 2.5]
    RAG --> UI
    API --> REPORT[Repository report service]
    REPORT --> INSPECT[Repository inspection + bounded manifest reads]
    REPORT --> TS
    REPORT -->|optional summary| OLLAMA
    REPORT --> STORE[(backend/data/reports)]
    STORE --> UI
    MCP[MCP stdio server] --> SAFE
    MCP --> SEARCH
    MCP --> RAG
```

## Trust and data boundaries

- The FastAPI backend binds to loopback by default.
- Source repositories, embedding model, ChromaDB, Ollama and generated reports remain on the user's computer.
- A hosted frontend is optional and still calls the local backend; browser local-network restrictions apply.
- Report generation reuses repository inspection and Tree-sitter chunking. Dependency and security observations use bounded reads. The optional narrative summary calls only the local Ollama service.
- Repository text is untrusted input. It is never executed. Security pattern matches are heuristic review prompts, not proof of vulnerabilities.
- MCP uses stdio and does not expose a network listener.
