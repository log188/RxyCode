# validation/ - Result Validation

## What Is This Module?
Validates execution results against user requirements. Triggers re-planning when results are insufficient.

## Key Files
| File | Purpose |
|------|---------|
| validator.py | Validator - deterministic evidence checks plus structured scoring |
| side_effects.py | Detects tasks/claims that require WRITE/DANGER evidence |
| final_output.py | Verifies claim-to-evidence grounding and live artifacts |
| reflection.py | `Reflector` / `ReflectionResult` / `FailureType` - post-validation reflection (planning_error/reasoning_error/tool_error/verification_error/unknown) feeding `reflection_node` |
| re_planner.py | RePlanner - generates new plans when validation fails |

## Core Code: validator.py

**Classes:**
- ValidationResult(BaseModel): Contains passed, three scores, issues, and suggestion
- Validator: deterministic evidence validation followed by LLM scoring

**Validation Flow:**
1. Reject failed/malformed tool evidence and abnormal executor sentinels
2. Require an executed, successful WRITE/DANGER `ToolEvidence` whenever
   `TaskEffect` is `write`/`danger`, or when `auto` plus hints/intent/claims
   indicate a side effect
3. Only then ask the LLM for completeness, relevance, and format scores
4. All three scores must meet `pass_threshold` (default 0.7)
5. After synthesis, require every final claim to be a verbatim excerpt from a
   passed leaf result or successful tool evidence; required side-effect
   evidence must be cited, and artifact existence/size/SHA-256 is rechecked

**Key Methods:**
- validate(title, description, requirement, result, evidence, tools_hint, effect) -> ValidationResult

## Core Code: re_planner.py

**Purpose:** Generates revised plans when validation fails.

**Key Methods:**
- replan(tree, task_id) -> bool: Remove the failed task from the tree, run
  node/retry budget checks, and re-decompose it into a retry plan (inserted back
  into the tree). Returns `False` when the replan budget is exhausted and the
  task must be cancelled.
- Reflection precedes replanning: `Reflector.reflect(...)` classifies the
  failure (`planning_error` / `reasoning_error` / `tool_error` /
  `verification_error` / `unknown`) and `route_after_reflection` decides whether
  to retry, replan, or terminate.
