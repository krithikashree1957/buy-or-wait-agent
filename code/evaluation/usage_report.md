# Usage Report — Final Full-Dataset Run

Run command: `python code/main.py` on all 250 requests in `dataset/requests.csv`.

## Model providers and names

- Deterministic decision layer: none (pure Python, no model calls).
- Explanation layer (Stage 5.2): OpenAI-compatible chat-completions client is
  wired in `code/judgment.py` (model `gpt-4o-mini` via `EXPLANATION_MODEL`,
  temperature 0). For this final run no `OPENAI_API_KEY` was configured in the
  environment, so **no LLM calls were made**: every `decision_explanation` was
  produced by the deterministic grounded template over already-computed fields.

## Token usage (from client response usage fields)

- Total LLM calls: 0
- Total input tokens: 0
- Total output tokens: 0
- Average tokens per request: 0 (0 calls / 250 requests)

## Cost

- Estimated total cost: $0.00 (no model calls in this run).
- Per-request cost: $0.00.

Raw per-call usage records (empty for this run) are stored in
`code/evaluation/usage_data.json`. When `OPENAI_API_KEY` is set, `main.py`
populates this file from the API's usage fields and this report should be
regenerated from those real numbers.

