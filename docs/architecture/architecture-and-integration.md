# How the Chatbot and the Edge Advisor Are Seamed Together
### (Architecture + integration, in plain language)

## 1. The one-sentence idea

The **documentation chatbot is a "house"**, and the **edge-resource advisor is a
"room" inside it** — the room stays dark and silent until someone asks an
edge-hardware question, at which point it lights up, produces a recommendation,
and hands it to the chatbot to weave into its answer. To the user it's a single
assistant, not two tools.

---

## 2. The two systems (what each one is)

**The house — `RAG-docs-chameleon` (the chatbot).**
A retrieval-augmented question-answering app. When you ask a question it:
1. searches a database of Chameleon documentation for the most relevant passages,
2. pastes those passages into a prompt as "context",
3. asks a large language model to answer *using only that context*,
4. shows you the answer plus the source links.

**The room — `chi-edge-advisor` (the advisor).**
A specialist pipeline that answers one narrow question well: *"For this edge
computing task, which CHI@Edge device should I reserve, and how?"* It has its own
catalog of edge devices ("artifacts"), matches your task to the right one, and
produces a concrete device + lease recommendation.

Both were built separately. The integration makes the second run *inside* the
first, without either losing its independence.

---

## 3. The key design decision: the room is a library, not a service

There were three ways we could have connected them. We chose the simplest.

| Option | What it means | Why we did / didn't use it |
|---|---|---|
| Separate microservice (HTTP/API) | Run the advisor as its own server the chatbot calls over the network | Rejected — extra moving part, more to deploy and break |
| MCP / model-invoked tool | Let the language model *decide* to call the advisor as a "tool" | Rejected — the chatbot has no tool-calling layer; adding one is a big change |
| **In-process library (chosen)** | The advisor is imported directly into the chatbot's Python process and called like any function | **Chosen** — no network, no new infrastructure, one process to run |

So the "seam" is literally one Python import. The chatbot process loads the
advisor's code and calls it in-memory. That's what makes it a *room in the house*
rather than a *separate building next door*.

---

## 4. The seam, step by step (what happens on every question)

A small wrapper file, **`advisor_room.py`**, sits between the two and exposes just
two things the chatbot needs: *"should the room fire?"* and *"give me the
recommendation."* Here is the full lifecycle of one question:

```
        ┌─────────────────────────────────────────────────────────────┐
        │  USER types a question in the Streamlit chat box             │
        └───────────────────────────┬─────────────────────────────────┘
                                     ▼
        ┌─────────────────────────────────────────────────────────────┐
        │  CHATBOT retrieves matching documentation passages           │
        │  → builds the "context" (PRIMARY + SUPPLEMENTARY sections)   │
        └───────────────────────────┬─────────────────────────────────┘
                                     ▼
                    ┌────────────────────────────────┐
                    │  THE GATE  (advisor_room.       │
                    │  should_fire)                   │
                    │                                 │
                    │  Does the question contain an   │
                    │  edge CUE word (edge, camera,   │
                    │  sensor, container, Pi, GPIO…)  │
                    │            AND                  │
                    │  score the edge topic high      │
                    │  enough (router ≥ threshold)?   │
                    └───────┬─────────────────┬───────┘
                       NO   │                 │   YES
             ┌──────────────┘                 └──────────────┐
             ▼                                               ▼
   ┌───────────────────┐              ┌──────────────────────────────────────┐
   │ Room stays DARK.  │              │  ROOM LIGHTS UP (advisor_room.advise) │
   │ Context is        │              │  • picks the right edge device        │
   │ unchanged.        │              │  • asks the local LLM to reason        │
   └─────────┬─────────┘              │  • returns a device + lease rec        │
             │                        └───────────────────┬──────────────────┘
             │                                            ▼
             │                        ┌──────────────────────────────────────┐
             │                        │ Recommendation is APPENDED to the     │
             │                        │ context as a new labelled section:    │
             │                        │   === EDGE RESOURCE ADVISORY ===      │
             │                        └───────────────────┬──────────────────┘
             └───────────────────────────┬────────────────┘
                                          ▼
        ┌─────────────────────────────────────────────────────────────┐
        │  CHATBOT sends context → LOCAL LLM → writes the final answer  │
        │  (the advisory, if present, is just more context to use)      │
        └───────────────────────────┬─────────────────────────────────┘
                                     ▼
        ┌─────────────────────────────────────────────────────────────┐
        │  USER sees ONE answer + sources. If it was an edge question,  │
        │  the answer now contains a concrete device + lease rec.       │
        └─────────────────────────────────────────────────────────────┘
```

**The three parts of the seam, named:**

1. **The gate** — `should_fire(question)`. A cheap check that runs on *every*
   question but almost always says "no". It requires **both** an edge cue word
   **and** a high topic score, so general documentation questions never wake the
   room. This is why a normal "How do I use object storage?" question is answered
   exactly as it was before the integration.

2. **The recommendation** — `advise(question)`. Only runs when the gate says yes.
   This is the advisor's full pipeline producing a real, grounded device + lease
   recommendation.

3. **The injection** — the recommendation text is appended to the context under a
   clearly-labelled `=== EDGE RESOURCE ADVISORY ===` header, matching the same
   style the chatbot already uses for its `PRIMARY` and `SUPPLEMENTARY` sections.
   The language model then treats it as just another trusted piece of context and
   folds it naturally into the answer.

Everything above is wrapped behind a single on/off switch, **`ADVISOR_ENABLED`**.
Turn it off and the chatbot behaves exactly as the original — the room simply
isn't there.

---

## 5. Why the two fit together cleanly (the shared foundations)

Two technical facts made this integration honest rather than a hack:

- **Same "language of meaning" (embeddings).** Both systems represent text as
  vectors using the *same* model (`BAAI/bge-large-en-v1.5`). This means the
  advisor's notion of "what a question is about" lives in the same mathematical
  space as the chatbot's. The gate's relevance scores are therefore meaningful,
  not comparing apples to oranges. (We assert this at startup and fail loudly if
  the advisor ever falls back to a different embedder.)

- **Same brain (one local LLM).** After losing access to the hosted Llama-3.3-70B,
  we run our own model. *Both* the chatbot's answering step *and* the advisor's
  reasoning step call the **same local model** through one shared, OpenAI-style
  endpoint. There is only one "brain" in the house, and both the house and the
  room use it.

---

## 6. The updated architecture (the whole picture)

```
   ┌──────────────────────────────────────────────────────────────────────┐
   │              CHAMELEON GPU NODE  (2× NVIDIA P100, 16GB each)          │
   │                                                                      │
   │   ┌────────────────────────────────────────────────────────────┐    │
   │   │   THE HOUSE  —  Streamlit chatbot (one Python process)      │    │
   │   │                                                            │    │
   │   │   • Web UI (chat box, answers, source links)               │    │
   │   │   • Retrieval:  FAISS doc index + bge embeddings + reranker │    │
   │   │   • Prompt assembly (PRIMARY / SUPPLEMENTARY context)       │    │
   │   │                                                            │    │
   │   │   ┌──────────────────────────────────────────────────┐     │    │
   │   │   │  THE ROOM  —  chi-edge-advisor (imported library) │     │    │
   │   │   │  gate → pick device → reason → recommendation     │     │    │
   │   │   │  (fires only on edge questions)                   │     │    │
   │   │   └──────────────────────────────────────────────────┘     │    │
   │   └───────────────────────────┬────────────────────────────────┘    │
   │                               │ (both call the same local brain)     │
   │                               ▼                                      │
   │   ┌────────────────────────────────────────────────────────────┐    │
   │   │   THE BRAIN  —  Ollama serving Qwen2.5-32B (local LLM)      │    │
   │   │   OpenAI-compatible endpoint, runs on the two P100 GPUs     │    │
   │   └────────────────────────────────────────────────────────────┘    │
   │                                                                      │
   │   Embeddings + reranker run on CPU (to leave GPU memory for the LLM).│
   └──────────────────────────────────────────────────────────────────────┘
```

**What changed vs. the original chatbot:**

| Layer | Before | After |
|---|---|---|
| Language model | Hosted Llama-3.3-70B (needed a key we didn't have) | Self-hosted Qwen2.5-32B on our own GPU node |
| How the model is chosen | Hard-coded endpoint | Configurable via environment variables (clean, reversible) |
| Edge questions | Answered from docs only | Also get a concrete device + lease recommendation from the room |
| General questions | Answered from docs | **Unchanged** — the room never fires |
| Deploy | Docker container | Runs directly on the node as a background service |

---

## 7. The single most important sentence for your report

> The edge advisor is embedded **inside** the documentation chatbot as an
> in-process module that activates only for edge-hardware questions; when it
> activates, its recommendation is injected into the chatbot's context as a
> labelled section, so the language model produces one unified, source-grounded
> answer — and with a single switch the advisor can be turned off, leaving the
> original chatbot untouched.
