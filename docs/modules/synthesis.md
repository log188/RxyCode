# synthesis/ - Result Synthesis

## What Is This Module?
Combines execution results from all subtasks into a coherent final response for the user. Runs immediately before `final_verifier`, which is the actual terminal node of the LangGraph pipeline (`synthesizer -> final_verifier -> END`).

## Key Files
| File | Purpose |
|------|---------|
| synthesizer.py | OutputSynthesizer - merges subtask results into final answer |
| validation/final_output.py | `GroundedSynthesis` / `GroundedClaim` / `build_grounding_sources` / `verify_grounded_synthesis` |

## Core Code: synthesizer.py (OutputSynthesizer)

**How It Works (grounded synthesis):**
1. Builds **grounding sources** from passed leaf results and successful
   WRITE/DANGER tool evidence
2. Asks the LLM to produce a `GroundedSynthesis` (final `answer` plus explicit
   `claims[]`), instructing it that every final assertion must be a verbatim
   excerpt of a grounding source
3. `final_verifier_node` runs `verify_grounded_synthesis` (validation/final_output.py)
   to check claim-to-evidence grounding and live artifact existence/size/SHA-256
4. When no grounding source exists, returns
   `[Build incomplete: No completed tasks to synthesize...]`
5. When results are mixed, the LLM is instructed to explicitly disclose
   incomplete/cancelled tasks

**Key Methods:**
- synthesize_grounded(tree, user_input) -> str: **Main entry point**
- synthesize(tree, user_input) -> str: Backward-compatible wrapper delegating to `synthesize_grounded`
- collect_results(tree) -> list[dict]: Extract all results from tree nodes

**Output Format:**
- Preserves task structure in the response
- Never silently omits cancelled subtasks
- Maintains original user intent focus
