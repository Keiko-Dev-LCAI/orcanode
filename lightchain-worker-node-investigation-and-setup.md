# LightChain Worker Node — Investigation Report & Correct-Setup / Troubleshooting Guide

> **How to use this document.** Hand this entire file to Claude (or any
> coding/ops assistant) running **on the worker machine**. Part 1 is the
> evidence-based diagnosis of what went wrong. Part 2 ranks the root causes.
> Parts 3–5 are the canonical setup, a step-by-step troubleshooting runbook
> Claude can execute command-by-command, and the decision on whether to
> recover or cut losses. Every constant here was verified live against the
> LightChain mainnet subgraph and the official node page on
> **2026-05-15** — do not assume, re-verify with the queries in the Appendix.
>
> **Instruction to the assistant:** Work top-down. Confirm the root cause from
> Part 2 *on the actual machine* before changing anything. The single most
> likely cause (model-tag mismatch) is officially documented and matches the
> observed failure exactly — check it first. Do not register/relaunch until
> the end-to-end self-test in Part 4 passes.

---

## Subject

| | |
|---|---|
| Worker address | `0x1F899FaD2C8BD70b6eF356ae6cC3c0abDbB15EB5` |
| Network | LightChain **mainnet**, chain ID **9200** |
| Explorer | `https://mainnet.lightscan.app/address/0x1F899FaD2C8BD70b6eF356ae6cC3c0abDbB15EB5` |
| Investigated | 2026-05-15 21:25 UTC |

---

# PART 1 — Investigation findings

## 1.1 On-chain registration: VALID, but never productive

Pulled from `https://workers-api.mainnet.lightchain.ai/graphql`:

| Field | Value | Reading |
|---|---|---|
| `status` | `active` | Registered & not deregistered |
| `stake` | 50,000 LCAI | Exactly `min_worker_stake` — fully bonded, no buffer |
| `created_at` | 2026-05-09 16:59:50 UTC | Registered ~6.2 days before investigation |
| `workermodels` | `llama3-8b` (`0xf4a4…428848`) only | Correct model, correct digest |
| `offense_count` | 0 | No recorded offenses **yet** |
| `suspended_until` | 0 | Not suspended |
| `jobs_completed` | **0** | Has never completed a single job |
| `jobs_timed_out` | 0 | No timeout recorded **yet** |
| `disputes_lost` | 0 | — |
| `total_earned` | **0 LCAI** | Has never earned anything |
| `last_seen_at` | **2026-05-13 16:07:08 UTC** | **No heartbeat for ~53 hours** |

Registration, model binding, and stake are all correct. The problem is
operational, not configuration-of-registration.

## 1.2 Job history: exactly one job, stuck

He has handled **one job in his entire existence**:

| | |
|---|---|
| Job ID | **#359** |
| Session ID | 257 (`status: Active`, requester `0x06440FEE…aD3e`) |
| Model | `llama3-8b` (`0xf4a4…428848`) |
| Escrowed fee | 0.02 LCAI (locked) |
| `submitted_at` | 2026-05-13 16:06:56 UTC |
| `ack_at` | 2026-05-13 16:07:08 UTC |
| `completed_at` | **0 (never)** |
| `released_at` | 0 |
| `worker_share` | 0 |
| `state` | **`Acknowledged`** |

## 1.3 Timeline reconstruction — the smoking gun

```
2026-05-09 16:59:50  Worker registers on-chain (status=active, 50k stake)
        … ~3.96 days of NOTHING — no jobs assigned, fine, the network is quiet …
2026-05-13 16:05:20  Session 257 opened by a user
2026-05-13 16:06:56  Job #359 submitted to this worker
2026-05-13 16:07:08  Worker ACKNOWLEDGES job #359   (ack latency 12s — healthy!)
2026-05-13 16:07:08  ← last_seen_at and updated_at FREEZE here, to the second
        … ~53 hours of complete silence …
2026-05-15 21:25:00  Investigation. Job still "Acknowledged". 0 completed.
```

The decisive fact: **`last_seen_at` equals `ack_at` to the exact second.**
The worker was alive and responsive long enough to perform the on-chain
acknowledgement, and then produced *zero* further activity — no response
frames, no heartbeat, nothing — from that instant onward.

This is not "the host died randomly." If the box had simply crashed at a
random time you would not expect the freeze to land *exactly* on the ack of
its very first job. The signature **"acks one job, then instantly and
permanently goes silent"** points at the worker process failing *while trying
to serve that job* — the on-chain ack path (which never touches the model)
succeeded, but the very next step (call the local model, stream the encrypted
answer back over the relay) failed and the process never recovered.

## 1.4 Penalty exposure — pending, not avoided

Protocol config (global, verified live):

| Param | Value | Meaning |
|---|---|---|
| `resolution_timeout` | 172,800 s = **48 h** | Deadline to complete an ack'd job |
| `timeout_slash_bps` | 750 = **7.5%** | Slash for never acking |
| `completion_timeout_slash_bps` | 1500 = **15%** | Slash for **acking then not completing** |
| `dispute_slash_bps` | 2500 = 25% | Slash for losing a dispute |
| `suspension_threshold` | 3 | Offenses before suspension |
| `suspension_cooldown` | 604,800 s = **7 days** | Suspension length |
| `min_worker_stake` | 50,000 LCAI | Stake floor |

Job #359 has been `Acknowledged`-but-not-completed for ~53 h, **past the 48 h
`resolution_timeout`**. It therefore qualifies for the **15% completion-timeout
slash = ~7,500 LCAI** (the harsher tier, because it ack'd then failed — not the
7.5% no-ack tier). The slash/offense is not yet reflected in the subgraph
(`offense_count` still 0) because it is applied lazily — typically when a
keeper, the disputer, or the next session interaction sweeps the expired job.
**It is pending, not escaped.** Once it lands it is also offense #1 of 3 toward
a 7-day suspension.

> **Conclusion of Part 1:** The worker is correctly *registered* but is a
> non-functional node. It served zero jobs, earned zero, and is one lazy
> on-chain sweep away from a ~7,500 LCAI slash and offense #1. The failure
> mode is "ack then permanent silence on its first job."

---

# PART 2 — Root-cause hypotheses (ranked, with confirm/fix)

> Check in this order. #1 is the most likely because it is **officially
> documented as a pitfall**, it produces *exactly* the observed signature, and
> it matches the Discord chatter about `llama3-8b` vs `llama3-8b:latest`.

### #1 — Model tag/alias mismatch (`llama3-8b` vs `llama3-8b:latest` / `llama3:8b`) — PRIMARY

**Why it fits perfectly:** The network's on-chain model registry calls the
model **exactly `llama3-8b`** (digest `0xf4a414fa…428848`). The official
node setup requires you to create an Ollama alias named **exactly `llama3-8b`**
via `ollama cp llama3:8b llama3-8b`, and the page explicitly warns the alias
must be `llama3-8b` **and not `llama3-8b:latest`**. Ollama internally tags
models as `name:tag`; a bare `ollama pull llama3:8b` or a copy can end up
served as `llama3:8b` or `llama3-8b:latest`. If the worker advertises
`SUPPORTED_MODELS=llama3-8b` and accepts the job (on-chain ack — *no model
call yet*), then calls its local Ollama for model `llama3-8b` but Ollama only
has `llama3:8b` / `llama3-8b:latest`, the generate call fails with
model-not-found. **Result: ack succeeds, inference never produces output, job
hangs until timeout.** This is the 1.3 signature, exactly.

**Confirm on the machine:**
```bash
ollama list                       # what tags actually exist locally?
curl -s http://localhost:11434/api/tags | python3 -m json.tool   # ground truth
# Does an inference for the EXACT advertised name work?
curl -s http://localhost:11434/api/generate \
  -d '{"model":"llama3-8b","prompt":"ping","stream":false}' | head -c 400
```
If `ollama list` shows `llama3:8b` or `llama3-8b:latest` but **not** a plain
`llama3-8b`, or the `/api/generate` call with `"model":"llama3-8b"` returns an
error → **this is the root cause.**

**Fix:**
```bash
ollama pull llama3:8b
ollama cp llama3:8b llama3-8b          # creates the EXACT alias the network expects
ollama list                            # verify a row named exactly "llama3-8b"
curl -s http://localhost:11434/api/generate \
  -d '{"model":"llama3-8b","prompt":"ping","stream":false}'   # must return text
```
Ensure the worker env is `SUPPORTED_MODELS=llama3-8b` (no tag suffix) and that
this string is byte-identical to the Ollama alias and to the registry name.

### #2 — No process supervision / the host went down and never recovered

**Why it could fit:** If the worker container wasn't launched with
`--restart always` (or systemd/keeper), a crash or reboot after the ack leaves
it permanently down — consistent with the flat-line after 16:07:08 UTC.

**Confirm:**
```bash
docker ps -a --filter name=lightchain-worker        # is it running? exited? when?
docker inspect -f '{{.HostConfig.RestartPolicy.Name}}' lightchain-worker
uptime                                              # did the host reboot 2026-05-13?
last reboot | head -3
```
**Fix:** relaunch with `-d --restart always` (Part 3 Phase 08) and add the
monitoring in Part 4.6 so `last_seen_at` can never silently flat-line again.

### #3 — Ollama unreachable from the worker container

**Why:** The worker runs in Docker and reaches Ollama via
`OLLAMA_URL=http://host.docker.internal:11434` with
`--add-host=host.docker.internal:host-gateway`. If Ollama isn't running, is
bound only to `127.0.0.1`, the host-gateway flag is missing, or a firewall
blocks 11434, the worker acks then can't infer.

**Confirm:**
```bash
systemctl status ollama 2>/dev/null || pgrep -a ollama
ss -lntp | grep 11434                                  # is it listening, on what addr?
docker exec lightchain-worker sh -c 'wget -qO- http://host.docker.internal:11434/api/tags' \
  || echo "container CANNOT reach Ollama"
```
**Fix:** run `ollama serve` as a supervised service, ensure it listens on a
host-reachable interface (`OLLAMA_HOST=0.0.0.0:11434`), keep
`--add-host=host.docker.internal:host-gateway` on the container.

### #4 — GPU/VRAM exhaustion on llama3-8b

**Why:** Minimum spec is 8 GB VRAM for llama3-8b. If VRAM is short, the first
real generate after ack can OOM/hang the Ollama backend.

**Confirm:**
```bash
nvidia-smi                                  # VRAM free vs used; any zombie procs
journalctl -u ollama --since "2026-05-13 16:00" --no-pager | tail -50
docker logs lightchain-worker 2>&1 | grep -iE "oom|cuda|vram|killed|memory" | tail
```
**Fix:** free VRAM / use a ≥8 GB GPU (recommended ≥24 GB), or run a smaller
quantization, then re-test the generate call from #1.

### #5 — Relay/worker-gateway WebSocket dropped with no reconnect

**Why:** After ack, the worker must stream the encrypted answer back over a
WebSocket to `worker-gateway.mainnet.lightchain.ai`. A dropped socket with no
auto-reconnect would also produce ack-then-silence.

**Confirm:**
```bash
docker logs lightchain-worker 2>&1 \
  | grep -iE "websocket|ws_|gateway|reconnect|disconnect|auth" | tail -40
```
Look for "websocket connected" / "authenticated with worker-gateway" and
whether it ever logged a disconnect around 2026-05-13 16:07 without a
reconnect. **Fix:** run the current `worker:latest` image with
`--restart always`; ensure `WORKER_GATEWAY_URL` and `BEACON_API_URL` are set
exactly as in Part 3.

> In practice, run the Part 4 runbook — it checks #1→#5 in order and most of
> the time stops at #1.

---

# PART 3 — Canonical correct setup (mainnet)

Source: official `https://workers.lightchain.ai/run-node`, cross-checked
against the live chain on 2026-05-15. **Verified constants:**

| Item | Value |
|---|---|
| Chain ID | `9200` |
| RPC | `https://rpc.mainnet.lightchain.ai` |
| Beacon API | `https://beacon.mainnet.lightchain.ai` |
| Worker gateway | `https://worker-gateway.mainnet.lightchain.ai` |
| `WorkerRegistry` (precompile) | `0x0000000000000000000000000000000000001002` |
| `JobRegistry` (proxy) | `0xfB15F90298e4CcD7106E76fFB5e520315cC42B0b` |
| Worker Docker image | `us-central1-docker.pkg.dev/lightchain/lightchain-mainnet-public-docker/worker:latest` |
| **Required model name** | **`llama3-8b`** (Ollama alias, `SUPPORTED_MODELS`, and on-chain registry name must all be byte-identical) |
| Model digest (must match registry) | `0xf4a414fa51803433e9197f32cda96d5cb2ac8269c481eb0262fe2dd11f428848` |
| Model fee / max output | 0.02 LCAI / 2048 tokens |
| Min stake | 50,000 LCAI (fund ≥ **50,001** for gas headroom) |

**Hardware:** min 4 cores / 16 GB RAM / 512 GB NVMe / **8 GB VRAM** / 100 Mbps.
Recommended 16 cores / 64 GB / 2 TB / 24 GB VRAM / 1 Gbps. Software: Docker,
Foundry (`cast`), Ollama, a funder wallet with ≥ 50,001 LCAI.

### Phase 00 — Worker key
```bash
cast wallet new
export WORKER_PRIVKEY=0x...                       # from output — keep secret
export WORKER_ADDR=$(cast wallet address --private-key "$WORKER_PRIVKEY")
echo "$WORKER_ADDR"
```

### Phase 01 — Resolve mainnet addresses from chain
```bash
export RPC_URL=https://rpc.mainnet.lightchain.ai
export WORKER_REGISTRY_ADDRESS=0x0000000000000000000000000000000000001002
export AI_CONFIG_ADDRESS=$(cast call $WORKER_REGISTRY_ADDRESS "aiConfig()(address)" --rpc-url $RPC_URL)
export JOB_REGISTRY_ADDRESS=$(cast call $WORKER_REGISTRY_ADDRESS "jobRegistry()(address)" --rpc-url $RPC_URL)
echo "AIConfig=$AI_CONFIG_ADDRESS  JobRegistry=$JOB_REGISTRY_ADDRESS"
# Sanity: JobRegistry MUST equal 0xfB15F90298e4CcD7106E76fFB5e520315cC42B0b
```

### Phase 02 — Ollama + model (THE STEP THAT BIT THIS WORKER)
```bash
curl -fsSL https://ollama.com/install.sh | sh
# run Ollama as a supervised service (NOT a bare backgrounded process):
sudo systemctl enable --now ollama 2>/dev/null || (OLLAMA_HOST=0.0.0.0:11434 ollama serve &)

ollama pull llama3:8b
ollama cp  llama3:8b llama3-8b          # ← create the EXACT alias "llama3-8b"

# MANDATORY verification — all three must agree on the literal string "llama3-8b":
ollama list | grep -E '^llama3-8b\b'    # a row whose NAME is exactly llama3-8b
curl -s http://localhost:11434/api/generate \
  -d '{"model":"llama3-8b","prompt":"Say OK","stream":false}' | python3 -m json.tool
```
> ⚠️ **Do not skip the verification.** If `ollama list` only shows
> `llama3:8b` or `llama3-8b:latest`, the worker will acknowledge jobs and then
> fail every inference → exactly the failure in Part 1. The advertised name
> (`SUPPORTED_MODELS`), the Ollama alias, and the on-chain registry name must
> be the identical string `llama3-8b` with **no tag suffix**.

### Phase 03 — Pull the worker image
```bash
docker pull us-central1-docker.pkg.dev/lightchain/lightchain-mainnet-public-docker/worker:latest
```

### Phase 04 — Import the key
```bash
mkdir -p ~/lightchain-worker/keys
docker run --rm -v ~/lightchain-worker/keys:/data \
  --entrypoint /bin/lightchain-worker \
  us-central1-docker.pkg.dev/lightchain/lightchain-mainnet-public-docker/worker:latest \
  import-key --private-key "$WORKER_PRIVKEY" --password "$KS_PASS" \
  --output /data/eth-keystore
```

### Phase 05 — Generate the ECDH encryption key
```bash
docker run --rm -v ~/lightchain-worker/keys:/data \
  -e WORKER_KEYSTORE_PATH=/data/eth-keystore/$(ls ~/lightchain-worker/keys/eth-keystore/ | head -1) \
  -e WORKER_KEYSTORE_PASSWORD="$KS_PASS" \
  -e ENCRYPTION_KEYSTORE_PATH=/data/worker-encryption.key \
  -e RPC_URL=https://rpc.mainnet.lightchain.ai -e CHAIN_ID=9200 \
  -e WORKER_REGISTRY_ADDRESS=0x0000000000000000000000000000000000001002 \
  -e AI_CONFIG_ADDRESS=$AI_CONFIG_ADDRESS \
  -e SUPPORTED_MODELS=llama3-8b \
  --entrypoint /bin/lightchain-worker \
  us-central1-docker.pkg.dev/lightchain/lightchain-mainnet-public-docker/worker:latest keygen
```

### Phase 06 — Fund the worker (≥ 50,001 LCAI)
```bash
export FUNDER_PRIVKEY=0x...
cast send "$WORKER_ADDR" --value 50005ether --rpc-url "$RPC_URL" --private-key "$FUNDER_PRIVKEY"
cast balance "$WORKER_ADDR" --rpc-url "$RPC_URL" | awk '{printf "%.4f LCAI\n",$1/1e18}'
```

### Phase 07 — Register on-chain
```bash
docker run --rm -v ~/lightchain-worker/keys:/data \
  -e WORKER_KEYSTORE_PATH=/data/eth-keystore/$(ls ~/lightchain-worker/keys/eth-keystore/ | head -1) \
  -e WORKER_KEYSTORE_PASSWORD="$KS_PASS" \
  -e ENCRYPTION_KEYSTORE_PATH=/data/worker-encryption.key \
  -e RPC_URL=https://rpc.mainnet.lightchain.ai -e CHAIN_ID=9200 \
  -e WORKER_REGISTRY_ADDRESS=0x0000000000000000000000000000000000001002 \
  -e AI_CONFIG_ADDRESS=$AI_CONFIG_ADDRESS \
  -e SUPPORTED_MODELS=llama3-8b \
  --entrypoint /bin/lightchain-worker \
  us-central1-docker.pkg.dev/lightchain/lightchain-mainnet-public-docker/worker:latest register
```

### Phase 08 — Run persistently (auto-restart)
```bash
docker run -d --restart always --user root --name lightchain-worker \
  --add-host=host.docker.internal:host-gateway \
  -v ~/lightchain-worker/keys:/data \
  -e WORKER_KEYSTORE_PATH=/data/eth-keystore/$(ls ~/lightchain-worker/keys/eth-keystore/ | head -1) \
  -e WORKER_KEYSTORE_PASSWORD="$KS_PASS" \
  -e ENCRYPTION_KEYSTORE_PATH=/data/worker-encryption.key \
  -e RPC_URL=https://rpc.mainnet.lightchain.ai -e CHAIN_ID=9200 \
  -e WORKER_REGISTRY_ADDRESS=0x0000000000000000000000000000000000001002 \
  -e AI_CONFIG_ADDRESS=$AI_CONFIG_ADDRESS \
  -e JOB_REGISTRY_ADDRESS=$JOB_REGISTRY_ADDRESS \
  -e SUPPORTED_MODELS=llama3-8b \
  -e OLLAMA_URL=http://host.docker.internal:11434 \
  -e BEACON_API_URL=https://beacon.mainnet.lightchain.ai \
  -e BLOB_MODE=beacon \
  -e SESSION_KEY_FILE=/data/session-keys.enc \
  -e WORKER_GATEWAY_URL=https://worker-gateway.mainnet.lightchain.ai \
  us-central1-docker.pkg.dev/lightchain/lightchain-mainnet-public-docker/worker:latest
```

**Healthy startup logs** (must see all three):
`registration validated` · `authenticated with worker-gateway` · `websocket connected`

---

# PART 4 — Troubleshooting runbook (execute in order)

> For Claude/operator, run on the worker host. Stop at the first step that
> fails — that is the fault. Do **not** re-register/relaunch until 4.5 passes.

### 4.0 Snapshot the on-chain truth (no host access needed)
```bash
curl -s -X POST -H 'content-type: application/json' \
  --data '{"query":"{ worker(id:\"0x1F899FaD2C8BD70b6eF356ae6cC3c0abDbB15EB5\"){ status stake offense_count suspended_until jobs_completed jobs_timed_out last_seen_at } jobs(first:5,orderBy:submitted_at,orderDirection:desc,where:{worker:\"0x1F899FaD2C8BD70b6eF356ae6cC3c0abDbB15EB5\"}){ id state submitted_at ack_at completed_at } }"}' \
  https://workers-api.mainnet.lightchain.ai/graphql | python3 -m json.tool
```
Note `offense_count`/`suspended_until` — if the slash already landed, the
recovery decision (Part 5) changes.

### 4.1 Is the worker process even alive?
```bash
docker ps -a --filter name=lightchain-worker
docker inspect -f 'restart={{.HostConfig.RestartPolicy.Name}} exitcode={{.State.ExitCode}} started={{.State.StartedAt}} finished={{.State.FinishedAt}}' lightchain-worker
uptime; last reboot | head -3
```
Container exited / no `restart=always` / host rebooted 2026-05-13 → cause #2.

### 4.2 Ollama reachable + correct model (the #1 check)
```bash
ollama list
curl -s http://localhost:11434/api/tags | python3 -m json.tool
curl -s http://localhost:11434/api/generate \
  -d '{"model":"llama3-8b","prompt":"ping","stream":false}' | head -c 500
docker exec lightchain-worker sh -c 'wget -qO- http://host.docker.internal:11434/api/tags' \
  | python3 -m json.tool || echo "CONTAINER CANNOT REACH OLLAMA (cause #3)"
```
No exact `llama3-8b` row, or generate errors → **cause #1** → fix per Part 2 #1.
Container can't reach Ollama → cause #3.

### 4.3 Worker logs around the failure
```bash
docker logs lightchain-worker 2>&1 | tail -120
docker logs lightchain-worker 2>&1 | grep -iE "error|model|not found|websocket|gateway|oom|cuda|panic|fatal" | tail -60
```
"model not found / unknown model llama3-8b" → cause #1. WebSocket
disconnect with no reconnect → cause #5. OOM/CUDA → cause #4.

### 4.4 GPU / resources
```bash
nvidia-smi
free -h; df -h ~ /var/lib/docker
journalctl -u ollama --since "2026-05-13 16:00" --no-pager | tail -40
```

### 4.5 End-to-end self-test BEFORE going live again
After applying the fix and starting Ollama (Part 3 Phase 02), confirm the full
local path works:
```bash
# exact-name model call returns generated text:
curl -s http://localhost:11434/api/generate \
  -d '{"model":"llama3-8b","prompt":"Reply with the single word OK.","stream":false}' \
  | python3 -c "import sys,json;print(json.load(sys.stdin).get('response','NO RESPONSE'))"
# worker status subcommand reports healthy:
docker run --rm -v ~/lightchain-worker/keys:/data \
  -e WORKER_KEYSTORE_PATH=/data/eth-keystore/$(ls ~/lightchain-worker/keys/eth-keystore/ | head -1) \
  -e WORKER_KEYSTORE_PASSWORD="$KS_PASS" \
  -e ENCRYPTION_KEYSTORE_PATH=/data/worker-encryption.key \
  -e RPC_URL=https://rpc.mainnet.lightchain.ai -e CHAIN_ID=9200 \
  -e WORKER_REGISTRY_ADDRESS=0x0000000000000000000000000000000000001002 \
  -e AI_CONFIG_ADDRESS=$AI_CONFIG_ADDRESS -e SUPPORTED_MODELS=llama3-8b \
  --entrypoint /bin/lightchain-worker \
  us-central1-docker.pkg.dev/lightchain/lightchain-mainnet-public-docker/worker:latest status
```
Only relaunch (Phase 08) when **both** succeed.

### 4.6 Make the silent-failure impossible to repeat

1. **Always** launch with `-d --restart always` (Phase 08).
2. **Ollama under systemd**, not a bare `&` job:
   `sudo systemctl enable --now ollama`.
3. **Liveness watchdog** — `last_seen_at` must never silently flat-line again.
   Cron every 10 min; alert if stale > 20 min:
   ```bash
   #!/usr/bin/env bash
   W=0x1F899FaD2C8BD70b6eF356ae6cC3c0abDbB15EB5
   LS=$(curl -s -X POST -H 'content-type: application/json' \
     --data "{\"query\":\"{ worker(id:\\\"$W\\\"){ last_seen_at status } }\"}" \
     https://workers-api.mainnet.lightchain.ai/graphql \
     | python3 -c "import sys,json;print(json.load(sys.stdin)['data']['worker']['last_seen_at'])")
   AGE=$(( $(date -u +%s) - LS ))
   if [ "$AGE" -gt 1200 ]; then
     echo "ALERT: worker $W last_seen ${AGE}s ago — investigate NOW"
     docker restart lightchain-worker
   fi
   ```
4. **Job-log monitor** (run after relaunch):
   ```bash
   docker logs -f --tail=0 lightchain-worker \
     | grep -E "ws_job_received|stage [1-8]|job completed|job failed"
   ```
   First real job: confirm you see `ws_job_received` → stages → `job completed`,
   then check the subgraph shows `jobs_completed: 1` and `total_earned > 0`.

---

# PART 5 — Recover or cut losses?

Job #359 ack'd 2026-05-13 16:07 UTC; `resolution_timeout` is 48 h; by
investigation it was ~53 h → **past the deadline**. The ~7,500 LCAI
(15%) completion-timeout slash for #359 is almost certainly already
unavoidable; the open question is *future* offenses (3 → 7-day suspension).

- **Option A — Fix & keep running (recommended if the host is reliable).**
  Apply the Part 2 #1 fix, pass the Part 4.5 self-test, relaunch Phase 08
  with `--restart always` + the Part 4.6 watchdog. Remaining stake keeps
  earning. Re-run 4.0 first: if `offense_count` is still 0 you may even dodge
  the #359 slash if a fast fix beats the lazy sweep (do not count on it).
- **Option B — Graceful deregister (if the host can't be made reliable).**
  Run the `deregister` subcommand (same env as Phase 07) to recover remaining
  stake rather than accruing offense #2/#3 and a 7-day suspension. Note any
  pending #359 slash + the locked 0.02 LCAI escrow are still applied on exit.

**Recommendation:** Option A — the root cause is almost certainly the
documented model-alias mismatch (Part 2 #1), which is a 3-command fix. Verify
with 4.2/4.5, relaunch with supervision + watchdog, and confirm the next job
produces `jobs_completed: 1` and nonzero `total_earned`.

---

# Appendix A — Live verification queries

```bash
GQL=https://workers-api.mainnet.lightchain.ai/graphql
W=0x1F899FaD2C8BD70b6eF356ae6cC3c0abDbB15EB5

# Worker full state
curl -s -X POST -H 'content-type: application/json' \
  --data "{\"query\":\"{ worker(id:\\\"$W\\\"){ status stake suspended_until offense_count active_job_count jobs_completed jobs_timed_out disputes_lost total_earned last_seen_at created_at } }\"}" $GQL | python3 -m json.tool

# This worker's jobs
curl -s -X POST -H 'content-type: application/json' \
  --data "{\"query\":\"{ jobs(first:25,orderBy:submitted_at,orderDirection:desc,where:{worker:\\\"$W\\\"}){ id session_id state submitted_at ack_at completed_at released_at worker_share } }\"}" $GQL | python3 -m json.tool

# Slash / dispute history
curl -s -X POST -H 'content-type: application/json' \
  --data "{\"query\":\"{ slashevents(where:{worker:\\\"$W\\\"}){ id } disputes(where:{worker:\\\"$W\\\"}){ id } }\"}" $GQL | python3 -m json.tool

# Canonical model registry (name MUST be 'llama3-8b')
curl -s -X POST -H 'content-type: application/json' \
  --data '{"query":"{ modelinfos{ id name fee max_output_tokens is_whitelisted is_enabled active_worker_count } }"}' $GQL | python3 -m json.tool

# Protocol slash/timeout config
curl -s -X POST -H 'content-type: application/json' \
  --data '{"query":"{ protocolconfigs{ id timeout_slash_bps completion_timeout_slash_bps dispute_slash_bps resolution_timeout suspension_threshold suspension_cooldown min_worker_stake } }"}' $GQL | python3 -m json.tool
```

# Appendix B — Constants (verified 2026-05-15)

| Constant | Value |
|---|---|
| Chain ID | 9200 |
| RPC | https://rpc.mainnet.lightchain.ai |
| Beacon API | https://beacon.mainnet.lightchain.ai |
| Worker gateway | https://worker-gateway.mainnet.lightchain.ai |
| Workers subgraph | https://workers-api.mainnet.lightchain.ai/graphql |
| Explorer | https://mainnet.lightscan.app |
| WorkerRegistry precompile | 0x0000000000000000000000000000000000001002 |
| JobRegistry proxy | 0xfB15F90298e4CcD7106E76fFB5e520315cC42B0b |
| Worker image | us-central1-docker.pkg.dev/lightchain/lightchain-mainnet-public-docker/worker:latest |
| Model name (exact) | `llama3-8b` |
| Model digest | 0xf4a414fa51803433e9197f32cda96d5cb2ac8269c481eb0262fe2dd11f428848 |
| Model fee / max tokens | 0.02 LCAI / 2048 |
| Min stake | 50,000 LCAI (fund ≥ 50,001) |
| resolution_timeout | 48 h |
| Slash: no-ack / ack-no-complete / dispute | 7.5% / 15% / 25% |
| Suspension | 3 offenses → 7 days |

# Appendix C — Glossary

- **Acknowledged** — worker confirmed receipt of a job on-chain; the model has
  *not* run yet. Ack ≠ work done.
- **resolution_timeout** — wall-clock window to complete an ack'd job (48 h).
  Miss it → 15% completion-timeout slash + an offense.
- **last_seen_at** — last worker heartbeat. A frozen `last_seen_at` = a dead
  node even if `status` still reads `active`.
- **SUPPORTED_MODELS** — the model name string the worker advertises. Must be
  byte-identical to the Ollama alias *and* the on-chain registry name
  (`llama3-8b`, no tag).

---

*Primary finding: registration is valid; the node ack'd one job then went
permanently silent — signature of the documented `llama3-8b` model-alias
mismatch. Fix the alias (Part 2 #1), pass the Part 4.5 self-test, relaunch
with supervision + the Part 4.6 watchdog.*
