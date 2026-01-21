# Thesis headlines

**Core Issue:**
Language models lose track of case essentials in large legal cases, especially as cases evolve over extended multi-turn conversations.

**Proposed Theme:**
Context Preservation in Multi-Turn LLM Conversations for Legal Case Management

**Proposed Problem Description:**
Does maintaining a structured state representation of case essentials (FactSheet) improve LLM agents' ability to preserve context and maintain accuracy across multi-turn conversations in complex legal cases?

**Research Questions:**

- How does explicit state management (FactSheet) compare to baseline RAG in maintaining contextual accuracy over extended conversations?
- What is the degradation rate of contextual accuracy as conversation length increases?
- Which case elements (parties, claims, timeline) are most susceptible to context loss?
- How does state update frequency affect performance?

**Methods:**

- Foundation Model via official UI (baseline)
- Foundation Model API + RAG only
- Foundation Model API + FactSheet
- Cross-model comparison (GPT-4, Claude, Gemini)

**Metrics:**

- Automatic metrics
    - **Efficiency:** Token usage / compression rate (input tokens)
    - **Cost** : Total cost
    - **Accuracy:** Factual correctness, hallucination rate
    - **Consistency: A**nd from this, stastistical modeling, confidence interval, certainty etc.
- Manual metrics
    - **Quality:** Expert evaluation (lawyers from Bahr)
    - **Relevance**:

**Alternative Research Direction / Trade-off Analysis:**
Can smaller/cheaper models (or open-source models) combined with FactSheet match the performance of larger models? This explores:

- Cost savings potential
- Viability of open-source models for client-attorney privilege/NDA compliance

Additional metrics:

- Correlation analsysis for each factsheet attribute
- Formal hypothesis testing and statistical significance? how?