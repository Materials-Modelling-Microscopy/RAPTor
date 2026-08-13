# Alloy Research Assistant

This directory is RAPTor's provenance-aware knowledge workspace. It ingests
reviewed structured data and documents into a local DuckDB database, exposes
parameterized read-only queries, and supports lexical and semantic retrieval,
tool routing, citation-preserving evidence, and answer synthesis.

The assistant complements the thermodynamic calculation engine; it does not
replace live PyCalphad, spinodal, or SymPlex calculations. Use the repository
[README](../README.md) and the [calculation-engine guide](../external/Rapid_Phase_Field_Prediction/README.md)
for computational workflows. Use this directory when the task is to organize,
query, retrieve, or cite stored research evidence.

## Directory roles

- `data/inbox/`: landing area for scattered files; no cleaning is required.
- `data/raw/`: registered, unchanged copies of source material.
- `data/curated/`: normalized documents, tables, and metadata.
- `data/generated/`: disposable indexes, embeddings, and caches.
- `catalog/`: source registry, terminology, and field definitions.
- `evaluation/`: questions and expected evidence used to test the assistant.
- `src/`: database initialization, ingestion, and reviewed query code.

## Evidence classes

1. Published literature: external scientific evidence.
2. Published work by the researcher: established methods and interpretations.
3. Manuscripts and dissertation: private or developing scientific insights.
4. Experimental validation: observations and benchmark labels.
5. Computational results: numerical predictions and model outputs.
6. RPFP Web source code: implementation details and calculation pathways.
7. Research notes: hypotheses and developing ideas, not established conclusions.

Generated answers should identify their evidence class and preserve a route
back to the original file, table row, page, or code location.

## Data safety

The contents of `inbox`, `raw`, and `generated` are ignored by Git by default.
This reduces the risk of committing private manuscripts, licensed papers,
unpublished results, or large generated artifacts. Only placeholder files are
tracked.

Do not place credentials, API keys, passwords, or access tokens anywhere in
this directory.

## First intake

Begin with a small representative collection:

- two to five publications;
- one dissertation chapter or manuscript;
- one experimental-validation table;
- one computational-results table; and
- five research questions the first prototype should answer.

Files can initially be placed in the appropriate `data/inbox` subdirectories
without renaming or reorganizing them.

## Structured database

From the repository root, activate the project environment and initialize the
database once:

```bash
source .venv/bin/activate
python -m alloy_assistant.src.initialize_database
```

Ingest every reviewed structured source:

```bash
python -m alloy_assistant.src.ingest_all_structured
```

The ingestion command is idempotent: sources are identified by SHA-256
checksum, so running it again does not duplicate unchanged data. The loaders
preserve source rows in staging tables and write normalized records to the
`alloy` schema. Run the automated checks with:

```bash
python -m unittest discover -s alloy_assistant/tests -v
```

## Reviewed queries

The read-only query command supports both human-readable output and JSON:

```bash
python -m alloy_assistant.src.query_database summary
python -m alloy_assistant.src.query_database overview W-Ta-Nb-Mo
python -m alloy_assistant.src.query_database miscibility W-Ta-Nb-Mo
python -m alloy_assistant.src.query_database pmr W-Ta-Nb-Mo
python -m alloy_assistant.src.query_database phases W-Ta-Nb-Mo
python -m alloy_assistant.src.query_database experiments W-Ta-Nb-Mo
python -m alloy_assistant.src.query_database tdb W-Ta-Nb-Mo
python -m alloy_assistant.src.query_database rank-tmisc --components 4
```

Place `--json` before the subcommand for machine-readable output. These
commands call typed, parameterized functions in `src/queries.py`; the same
functions will later be exposed as safe tools to the RAG agent.

## Prototype PDF pipeline

The first document pipeline uses PyPDF to extract every PDF page, remove
obvious repeated margins and comment noise, and create sentence-aware chunks
that never cross page boundaries:

```bash
python -m alloy_assistant.src.ingest_pdf_documents
```

The default chunk target is 350 words with up to 40 words of sentence overlap.
Each chunk retains its document, page, detected section, parser version, and
automatically recognized alloy, phase, method, and concept entities. Ingestion
is checksum-aware and idempotent. To deliberately regenerate chunks after
changing extraction settings:

```bash
python -m alloy_assistant.src.ingest_pdf_documents \
  --rebuild \
  --max-words 350 \
  --overlap-words 40
```

Inspect the document collection and try the pre-embedding lexical retriever:

```bash
python -m alloy_assistant.src.query_database documents
python -m alloy_assistant.src.query_database \
  search-text "spinodal decomposition mixing enthalpy"
```

Lexical search is intentionally transparent and limited. It establishes the
retrieval contract and citation path before semantic embeddings are added.

## Local vector embeddings

Generate normalized 384-dimensional vectors for every chunk with the pinned
`BAAI/bge-small-en-v1.5` model:

```bash
python -m alloy_assistant.src.embeddings
```

The model is downloaded once into `data/generated/models`. Vectors are stored
in DuckDB with the exact model revision and SHA-256 checksum of the chunk text.
Unchanged chunks are skipped on later runs; use `--rebuild` to regenerate all
vectors deliberately.

Run semantic retrieval:

```bash
python -m alloy_assistant.src.query_database search-semantic \
  "What pair interaction drives phase separation?" \
  --limit 5
```

DuckDB calculates cosine similarity directly over the stored `FLOAT[384]`
arrays. This is an exact scan, which is simple and appropriate for the current
761-chunk corpus. Lexical and semantic search remain separate so their results
can be evaluated before a hybrid ranker is introduced.

## Hybrid evidence retrieval

Fuse the lexical and semantic candidate lists into one citation-ready packet:

```bash
python -m alloy_assistant.src.query_database search-hybrid \
  "What pair interaction controls spinodal decomposition?" \
  --limit 6
```

The hybrid layer uses reciprocal-rank fusion rather than mixing incompatible
keyword and cosine scores. A small authority weight distinguishes first-party
research from supporting literature without overwhelming relevance. It also
removes reference-list noise and near duplicates, defaults to at most three
chunks from one document, and keeps the evidence packet below 1,800 words.
When the router recognizes an alloy system, it also passes that canonical
system name to retrieval. Chunks annotated with the exact system receive a
small, reported relevance weight; this is a ranking signal rather than a claim
that every matching passage explains the requested property.

Each result reports its lexical and semantic ranks, raw scores, fusion score,
retrieval channels, authority weight, source identity, and page citation. The
main tuning controls are:

```bash
--candidate-pool 30
--max-per-document 3
--max-total-words 1800
--source-class manuscript
--system-name Mo-Nb-Ta-W
```

## Question routing and reviewed tools

Inspect the retrieval plan before any tool executes:

```bash
python -m alloy_assistant.src.route_question \
  "What is the PMR of MoNbTaW at 1000 K, and why is it high?"
```

The deterministic router extracts recognized systems and Kelvin temperatures,
identifies structured and explanatory intent, and proposes only names present
in `src/tool_registry.py`. Each tool is a reviewed Python capability, not an
arbitrary SQL statement. A plan reports missing arguments and known coverage
gaps explicitly.

The example above plans `get_pmr_for_system` plus `hybrid_search`. By contrast,
asking which system has the highest PMR reports that no reviewed global PMR
ranking tool exists; the planner does not invent SQL. This deterministic
planner is the validation boundary for a future LLM-proposed plan.

Execute a complete plan through the strict registry-to-function whitelist:

```bash
python -m alloy_assistant.src.tool_executor \
  "What is the PMR of MoNbTaW at 1000 K?"
```

Execution stops before querying when required arguments are missing or a
structured intent has no reviewed tool. The executor never accepts raw SQL or
an unregistered Python function name.

The answer command adds a constrained hybrid planning layer. Simple,
unambiguous structured questions retain the deterministic fast path. Named
alloy assessments, compound questions, and other nontrivial requests ask the
Groq model to propose an evidence plan. Python then rejects invented tools,
unexpected arguments, missing required values, and plans exceeding eight
calls. Deterministically extracted systems, temperatures, and the original
document query override model-proposed values.

Candidate-assessment questions have an additional scientific safeguard. They
always inspect the system overview, PMR profile, equimolar miscibility result,
all stored pairwise mixing enthalpies, experimental observations, and document
context—even if the model omits one of those sources or planning is
unavailable. Use `--deterministic-router` to bypass LLM planning when debugging
or comparing behavior.

## Grounded answer synthesis

Build the exact evidence packet that will be handed to an answer model:

```bash
python -m alloy_assistant.src.evidence_bundle \
  "What is the PMR of MoNbTaW at 1000 K, and why is it high?"
```

The assembler assigns stable IDs to structured records (`S1`, `S2`, ...) and
document passages (`D1`, `D2`, ...), keeps their provenance, and reports empty
or truncated result sets. The provider-independent contract in
`src/answer_synthesis.py` instructs a model to treat reviewed structured values
as authoritative for exact numbers, use passages for explanation, state
conflicts and uncertainty, and cite only supplied evidence IDs.

Generated answers pass a mechanical grounding check: unknown citations,
answers with no citations, and answers that ignore available structured
evidence are rejected. A hosted or local model adapter is deliberately separate
from this layer so changing providers does not change retrieval, provenance, or
validation behavior.

### Groq prototype adapter

The first hosted adapter uses Groq with a local input cap, bounded completions,
low reasoning effort, and no automatic retries or provider-side model tools.
Exact structured questions use one synthesis request. Nontrivial questions may
first use a separate structured planning request. Both stages request strict
JSON Schema output: planning is constrained to reviewed tool names, while
synthesis is constrained to evidence IDs in the current packet. Python
validates the plan, executes tools locally, renders the answer, and validates
the visible inline citations. Install the pinned SDK with the rest of the
project:

```bash
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Create a key at `https://console.groq.com/keys`, enable Zero Data Retention in
Groq Data Controls, and expose the key only to the current shell:

```bash
read -s "GROQ_API_KEY?Groq API key: "
export GROQ_API_KEY
echo
```

Never put the real key in source code, a committed file, a notebook, or chat.
Ask a question:

```bash
python -m alloy_assistant.src.answer_question \
  "What is the PMR of MoNbTaW at 1000 K, and why is it high?"
```

The configurable default model is `openai/gpt-oss-120b`; override it with
`GROQ_MODEL` or `--model`. Add `--json` to retain the complete plan evidence,
grounding report, model name, and provider-reported token usage.
