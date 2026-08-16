# Response cache

This directory holds the raw experimental record: every model response, keyed by a SHA-256 hash of the complete request (namespace, model, prompt, system instruction, decoding parameters, repetition index).

**The cache is committed on purpose.** It is what makes the study reproducible without a key and without spending quota:

```bash
python -m src.run_experiment --config configs/experiment.yaml --phase main --offline
```

`--offline` serves entirely from cache and aborts on any miss, so a reader can regenerate every number in the report at zero API cost.

## Guarantees

- **No credentials are ever written here.** `ResponseCache.make_key` strips any `api_key` / `token` / `authorization` field before hashing, and the stored payload contains the response, token counts, and non-prompt request parameters only. A unit test asserts no key material reaches disk.
- **Entries are namespaced by provider.** Mock-provider responses are stored under a separate `namespace` and can never be served to a real run. Without this, a mock run followed by a real run would silently substitute synthetic data for model output.
- **Writes are atomic** (temp file plus `os.replace`), so an interrupted run cannot leave a half-written entry.
- **Corrupt entries are treated as misses** rather than propagating bad data.
- **Failed calls are cached too.** A deterministic failure should not be re-attempted on every re-run, and failures remain visible in the results file.

## Layout

Entries are sharded by the first two characters of the key to keep directory listings small:

```
cache/
  a3/a3f2....json
  7b/7b91....json
```

Each file records `text`, `ok`, `error`, token counts, `finish_reason`, the non-prompt request parameters, and a `prompt_sha256` fingerprint (the prompt itself is not duplicated in the payload).
