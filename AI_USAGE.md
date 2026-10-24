# AI Coding Tools Disclosure

## Summary

I used **Claude Code** (Anthropic) in VS Code as a pair programmer for this
assignment. I set the scope, the constraints and the architecture direction. I made
the key decisions and reviewed the output. The AI sped up the parts that are mostly
typing: scaffolding, first drafts of modules and tests, boilerplate configuration and
documentation drafts. I treated its output as a draft to review, never as finished
work.

## How I worked

1. **Plan before code.** Before any code was written, I asked for a full
   implementation plan: services, data model, RAG pipeline, error model, rate
   limiting and run modes. I reviewed it, changed several points (below), and only
   then allowed implementation to start.
2. **Small, reviewable increments.** Work was split into feature branches (setup →
   ingestion → RAG → rate limiting → UI). Each was tested and merged into
   `development` on its own, so every change stayed small enough to review properly.
3. **Unit tests alone don't count as working.** The full Docker stack was run end to
   end in both GPU and CPU mode. Dependencies (LLM, database, Redis) were stopped on
   purpose to check that the failure behaviour matches what `ARCHITECTURE.md` claims.
   Fixes went through `bugfix/*` branches, with regression tests where it made sense.
4. **Measured numbers, not guesses.** Documented figures come from runs on my
   machine: the retrieval threshold, latency, cold vs warm model start.
5. **Documentation reviewed last, by me.** I deliberately kept the docs out of the
   automated workflow and reviewed and edited them myself before committing.

## Decisions I made

These came from my own requirements and judgement, not from the tool:

| Decision | Reasoning |
|---|---|
| **Everything runs locally in Docker**: no hosted LLM, no API keys | The reviewer should be able to clone and run the project with one command, with no accounts, cost or secrets |
| **Use the GPU when present, fall back to CPU automatically** | I develop on an RTX 4060, but the reviewer may not have a GPU. The app must work on both without code changes. Detection happens in the start script (can Docker pass the GPU through?) *and* at runtime in code (`torch.cuda.is_available()`) |
| **No nginx**; Vite serves and proxies the UI | See the rejected suggestion below |
| **Branching model**: `main` / `staging` / `development` / `feature/*` / `bugfix/*` with `--no-ff` merges | It mirrors how I work on a team, and keeps the history readable as a sequence of features and fixes |
| **Model and infrastructure choices**: `llama3.2:3b`, in-process `bge-small` embeddings, Redis-backed rate limiting, TypeScript | Picked from options with stated trade-offs. A 3B model is usable on a reviewer's CPU, where a 7B one is not. Embeddings in the backend keep the GPU check in our code. Redis makes the rate limit correct across multiple instances |

## Suggestions I reviewed, changed or rejected

1. **Rejected: nginx for the frontend.** The initial plan served the React build with
   nginx and proxied `/api` through it, which is a typical production setup. I
   rejected it. This project only runs on a local machine for me and the reviewer,
   so an extra web server adds configuration and another moving part without adding
   value. Vite's built-in server (`vite preview` in Docker, `vite` natively) now
   serves the UI with the same `/api` proxy. The browser still talks to a single
   origin, so no CORS setup is needed.

2. **Changed: retry logic that was hard to read.** The first draft of the LLM client
   marked non-retryable errors by setting a private attribute on exception objects,
   and packed the HTTP 429 handling into one nested conditional expression. It
   worked, but code I can't explain quickly is code I can't maintain. It was
   rewritten so that each attempt returns an explicit
   `_Failure(error, retryable, delay_s)`, and the retry loop reads top to bottom.

3. **Changed: an over-broad exception handler.** A draft mapped *every* `OSError` to
   `503 DATABASE_UNAVAILABLE`. That would mislabel unrelated failures as database
   outages and hide the real cause, so it was narrowed to database-specific errors.
   A later outage test showed that the narrowing had missed one real case (see
   below), and that was fixed precisely rather than by widening the handler again.

4. **Changed twice: the relevance threshold.** The similarity cut-off that decides
   "nothing relevant, don't call the LLM" started as a round guess (0.6). It was then
   calibrated from measured scores on the seed data (0.62). My own manual testing then
   showed that this still dropped real questions such as "explain the escalation
   policy" (0.617), while an unrelated question scored 0.641. No single cut-off
   separates them. The threshold is now a lenient pre-filter (0.55), and the decision
   is left to the grounded prompt, which was re-tuned and measured for exactly that
   (see below).

5. **Kept after checking the reasoning: no retries on LLM read timeouts.** Retrying
   only connection errors, 5xx and 429 initially looked like an omission. I kept it:
   a model that is too slow to answer once is usually still too slow, and retrying
   triples the load on an already overloaded dependency.

## Issues found through verification

Each of these passed unit tests and was caught only by running the real stack or by
reviewing behaviour against the design. That is why I don't accept "tests pass" as
done.

| Issue | How it surfaced | Fix |
|---|---|---|
| Backend crashed on startup in Docker (`No module named app`) | First container run. Migrations had only been run on the host via `python -m alembic`, which adds the working directory to `sys.path`; the plain `alembic` CLI in the container does not | `prepend_sys_path` in `alembic.ini` |
| `/ask` held a DB connection for the whole LLM call | Code review against the "no connection held during slow work" claim in the design | End the read transaction after retrieval. Regression test with a single-connection pool, which fails without the fix |
| Database outage returned `500` instead of `503` | Stopping the database container on purpose | Translate connect-time network errors in the engine's connection factory, the one place they can only mean "database unreachable" |
| First question after startup took ~37 s | Timing the first answer after a fresh start | Warm up the model after pulling it. The first answer now takes 0.3 s |
| Slow image rebuilds, duplicated layers | Timing rebuilds after small code changes | A recursive `chown` layer re-ran on every source change; replaced with `COPY --chown` |
| **Answerable questions declined depending on punctuation**: "when can i request a refund policy" got "couldn't find information", but the same text with a trailing "." was answered | **My manual testing in the UI.** The question history table showed the right article had been retrieved (score 0.79), so the LLM, not retrieval, was at fault | Built a 55-question evaluation (with an unseen hold-out set) before changing anything. Rewrote the prompt as an explicit decision procedure, made generation deterministic, lowered the pre-filter threshold, added an answer cue and guards for paraphrased declines and empty replies. Result: 0 failures on relevant questions (was 4 of 15 unseen), unrelated questions still declined |

## Where I did not rely on AI

- **Scope and priorities.** What to build, what to leave out, and what "done" means
  for this assignment.
- **Security-relevant choices.** No secrets in the repository, no internal details in
  error responses, and treating retrieved document text as data rather than
  instructions in the prompt.
- **Final review.** Every change was reviewed before it was merged. I can explain the
  design decisions, trade-offs and failure behaviour in this repository without the
  tool.

I remain fully responsible for the correctness, security and maintainability of the
submitted code.
