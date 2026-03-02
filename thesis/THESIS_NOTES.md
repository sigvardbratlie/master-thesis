% Thesis Assistant Notes
% ======================
% 
% Master Thesis: Legal Case Management Agent
% Author: Sigvard Bratlie
% 
% TOPIC
% -----
% Context Compression Techniques for Legal Document Analysis
% - LLM-powered agent for lawyers to analyze cases, manage factsheets, process legal documents
% - Focus: handling large-scale document attachments in multi-turn conversations
% - Problem: context window limitations with large legal document volumes
% 
% TECH STACK
% -----------
% - LangGraph (StateGraph) for agent orchestration
% - LLM: Google Gemini (primary), OpenAI GPT (secondary)
% - Backend: FastAPI + SSE streaming
% - Frontend: Streamlit
% - Database: Supabase (PostgreSQL)
% - Vector store: BigQuery + ChromaDB
% - Auth: Supabase JWT
% 
% KEY CONCEPTS
% ------------
% - FactSheet: Structured legal case summary (parties, claims, damages, timeline, governing law)
% - Rolling summarization every 8 messages
% - Multi-phase async pipeline for project initialization
% 
% CHAPTER STRUCTURE
% ------------------
% 1. Introduction (TODO)
% 2. Theory/Background (TODO - theory.tex exists with placeholder)
% 3. Method (TODO - method.tex exists with placeholder)
% 4. Results (TODO - results.tex exists)
% 5. Discussion (TODO - discussion.tex exists)
% 6. Conclusion (TODO - conclusion.tex exists)
% 
% AVAILABLE SOURCES (sample.bib)
% -------------------------------
% - munkhdalai2024leave: Infini-attention for infinite context
% - hsieh2024ruler: RULER - Real context size evaluation
% - liu2025hoprag: Multi-hop reasoning for RAG
% - jiang2024longllmlingua: Prompt compression for long context
% - jiang2023llmlingua: LLMlingua compression
% - xu2023recomp: Recomp - selective augmentation for RAG
% 
% REFERENCES
% -----------
% Use \cite{key} to cite sources from sample.bib
