# LightChain v2 — AI Worker Network Integration Guide (Mainnet)

> **Purpose of this document.** Hand this entire file to Claude (or any coding
> assistant). It contains *everything* needed to write code that connects a
> project to the LightChain mainnet decentralized AI worker network and runs
> LLM inference through it. It is self-contained: network constants, the
> on-chain ABI, the full HTTP API, exact cryptographic wire formats, the
> ordered algorithm, a complete working TypeScript reference implementation,
> error handling, and a build checklist.
>
> **Instruction for the assistant:** Implement an inference client per the
> "Algorithm" and "Reference implementation" sections. Preserve the exact
> ordering, the exact `createSession` argument mapping, and the exact byte
> layouts — these are protocol requirements, not stylistic choices. Do not
> "fix" the argument mapping in step 7. Adapt language/stack as the user
> requests; the crypto primitives (P-256 ECDH + AES-256-GCM) are available in
> every mainstream language.

---

## 1. What this network is

LightChain v2 is a **gateway-mediated decentralized inference network**. You
never connect to a worker directly. The flow:

1. A **consumer gateway** (HTTP) authenticates you with a wallet signature
   (permissionless SIWE — any Ethereum keypair, no API key, no registration).
2. The gateway assigns you a **staked worker** and brokers an encrypted key
   exchange between you, the worker, and a "disputer" (arbitration role).
3. You open a session and submit the job **on-chain** via a `JobRegistry`
   contract (this is also how you pay the worker fee).
4. The encrypted prompt is uploaded as a blob; the worker runs the model.
5. The model output streams back to you over an **encrypted WebSocket relay**,
   AES-GCM-encrypted under a key only you (and the worker/disputer) hold.
6. The worker signs an on-chain `JobCompleted` event — a public, tamper-evident
   audit trail of exactly which worker answered and a hash of what it returned.

Trust model: workers are economically staked and slashable. The dispatcher
signs session authorizations. Plaintext is end-to-end encrypted; the gateway
and chain only ever see ciphertext and hashes.

---

## 2. Network constants — MAINNET (chain ID 9200)

| Resource | Value |
|---|---|
| Chain ID | `9200` |
| JSON-RPC | `https://rpc.mainnet.lightchain.ai` |
| Archive RPC | `https://archive.mainnet.lightchain.ai` |
| Block explorer | `https://mainnet.lightscan.app` |
| Consumer gateway (HTTP API) | `https://chat-api.mainnet.lightchain.ai` |
| Encrypted relay (WebSocket) | `wss://relay.mainnet.lightchain.ai/ws` |
| **`JobRegistry` (proxy)** | `0xfB15F90298e4CcD7106E76fFB5e520315cC42B0b` |
| Workers subgraph (GraphQL) | `https://workers-api.mainnet.lightchain.ai/graphql` |
| Native currency | `LCAI` (18 decimals) |
| Job fee (paid as `msg.value` on `submitJob`) | `0.02 LCAI` |
| Fee split | 80% worker / 15% treasury / 5% protocol pool |

**Models** (the `modelId` is a 32-byte digest passed as `bytes32`):

| Model | `modelId` digest | Status |
|---|---|---|
| `llama3-8b` | `0xf4a414fa51803433e9197f32cda96d5cb2ac8269c481eb0262fe2dd11f428848` | **live** |
| `llama3-70b` | `0x665d85c3b24f6a5cb91f90ec2e215d6155531158ff7ba81dfd182ecfab1dd4cf` | registered, gateway routing not yet enabled |

In practice, call `GET /api/models` and use the entry whose `name` is
`llama3-8b`. The `id` field from that response is what you pass everywhere a
`modelId` is required.

> To target the **testnet** instead, swap every URL's `mainnet` → `testnet`
> and use chain ID `8200` and `JobRegistry` `0x531b3a87c5d785441b9cf55b98169f20fd9056a7`. The protocol is identical. Testnet has a faucet (`https://lightfaucet.ai`); mainnet does not.

---

## 3. Prerequisites

1. **An Ethereum EOA (private key).** Any secp256k1 keypair. No registration.
2. **Native mainnet LCAI in that wallet.** Each inference costs ~`0.022 LCAI`
   (0.02 worker fee + ~0.002 gas). **There is no mainnet faucet** — fund the
   wallet by bridging LCAI (Hyperlane Warp Route), an exchange, or a transfer.
3. **Runtime deps** (for the TypeScript reference): `ethers` v6, `ws`, and the
   Node.js built-in `crypto` module. No other dependencies.

```bash
npm install ethers@^6 ws
```

Configuration should be environment-driven (never hardcode the key):

```
LIGHTCHAIN_RPC=https://rpc.mainnet.lightchain.ai
LIGHTCHAIN_CHAIN_ID=9200
LIGHTCHAIN_GATEWAY=https://chat-api.mainnet.lightchain.ai
LIGHTCHAIN_RELAY=wss://relay.mainnet.lightchain.ai/ws
LIGHTCHAIN_JOB_REGISTRY=0xfB15F90298e4CcD7106E76fFB5e520315cC42B0b
LIGHTCHAIN_JOB_FEE_LCAI=0.02
PRIVATE_KEY=0x...           # funded mainnet EOA — keep out of source control
```

---

## 4. On-chain interface — `JobRegistry` ABI

This is the only contract you interact with. Human-readable ABI:

```
function createSession(bytes32 paramsHash, address worker, bytes encWorkerKey, bytes ephemeralPubKey, bytes initState, uint256 expiry) payable returns (uint256 sessionId)
function submitJob(uint256 sessionId, bytes32 promptHash) payable returns (uint256 jobId)
event SessionCreated(uint256 indexed sessionId, address indexed user, bytes32 indexed paramsHash, address worker, bytes encWorkerKey, bytes ephemeralPubKey)
event JobSubmitted(uint256 indexed jobId, uint256 indexed sessionId, address worker)
event JobCompleted(uint256 indexed jobId, address indexed worker, bytes32 responseHash, bytes32 ciphertextHash)
```

- `createSession` is `payable` (send `0` value; the fee is paid on
  `submitJob`). Suggested gas limit: `1_000_000`.
- `submitJob` is `payable` — send exactly the job fee (`0.02 LCAI`) as
  `value`. Suggested gas limit: `500_000`.
- You obtain `sessionId` by parsing the `SessionCreated` event from the
  `createSession` receipt, and `jobId` from the `JobSubmitted` event in the
  `submitJob` receipt.
- The final answer is signalled by `JobCompleted` (filter logs by `jobId`).

---

## 5. HTTP API (consumer gateway)

Base URL = the gateway URL. Auth = `Authorization: Bearer <JWT>` header on
every endpoint **except** `GET /api/models` and the two `/api/auth/*`
endpoints. Acquire the JWT via the SIWE handshake (5.1). Cache it and reuse
until ~30s before expiry, then re-handshake.

### 5.1 `GET /api/auth/challenge?address=<0xADDR>`
Unauthenticated. Returns a ready-to-sign message.
```json
{ "nonce": "string", "message": "string-to-sign" }
```
Sign `message` verbatim with the wallet using EIP-191 `personal_sign`
(`wallet.signMessage(message)` in ethers). Do **not** reconstruct the SIWE
string yourself — sign exactly what the gateway returned.

### 5.2 `POST /api/auth/verify`
Unauthenticated. Body:
```json
{ "message": "<the message from 5.1>", "signature": "0x<sig>" }
```
Returns:
```json
{ "token": "<JWT>", "expiresAt": "<ISO-8601 timestamp>" }
```
Use `token` as the Bearer JWT. `expiresAt` is when it dies (~24h typical).

### 5.3 `GET /api/models`
Unauthenticated.
```json
{ "models": [ { "id": "0x<bytes32 digest>", "name": "llama3-8b" }, ... ] }
```

### 5.4 `POST /api/sessions/select`  *(auth required)*
Body: `{ "modelId": "<id from 5.3>" }`. Returns the worker assignment + the
public keys you must wrap your session key for:
```json
{
  "worker": "0x<workerAddress>",
  "workerEncryptionKey": "<base64 of 65-byte uncompressed P-256 pubkey>",
  "disputerEncryptionKey": "<hex of 65-byte uncompressed P-256 pubkey>",
  "nonce": 0,
  "expiry": 1788000000
}
```
Note `workerEncryptionKey` is base64 and `disputerEncryptionKey` is hex — your
pubkey decoder must accept **both** encodings (see 6).

### 5.5 `POST /api/sessions/prepare`  *(auth required)*
Body:
```json
{
  "modelId": "<id>",
  "encWorkerKey": "<base64 of ECDH-wrapped session key for the worker>",
  "encDisputerKey": "<base64 of ECDH-wrapped session key for the disputer>"
}
```
Returns a dispatcher-signed authorization:
```json
{
  "worker": "0x<workerAddress>",
  "workerEncryptionKey": "...",
  "signature": "0x<65-byte ECDSA signature>",
  "nonce": 0,
  "expiry": 1788000000
}
```
`signature` and `expiry` are passed straight into `createSession`.

### 5.6 `POST /api/blobs`  *(auth required)*
Body: `{ "data": "<base64 of the AES-GCM-encrypted prompt>" }`. Returns:
```json
{ "blobHashes": [ "0x<EIP-4844 versioned blob hash>" ] }
```
`blobHashes[0]` is the `promptHash` argument for `submitJob`.

### 5.7 `GET /api/sessions/:sessionId/token`  *(auth required)*
Poll this after `createSession`. While the session is still activating it
returns HTTP `202`, or `200` with `{ "status": "pending", "message": "..." }`,
or `401` transiently. Once active it returns `200`:
```json
{ "token": "<relay JWT>", "expiresAt": "<ISO>" }
```
Poll at ~1s intervals with a ~30s timeout. Connect the WebSocket to
`wss://relay.mainnet.lightchain.ai/ws?token=<URL-encoded relay JWT>`.

---

## 6. Cryptography (exact)

- **Key agreement:** ECDH on curve **P-256 / prime256v1 / secp256r1**. The
  raw ECDH shared secret (the 32-byte X-coordinate) is used **directly** as the
  AES-256 key. **No HKDF, no hashing, no salt.**
- **Symmetric cipher:** **AES-256-GCM**. 12-byte random nonce, 16-byte auth tag.
- **Public keys:** 65-byte **uncompressed** P-256 points (`0x04 || X || Y`).
  Gateway sends them base64 *or* hex (with or without `0x`). Decoder must
  accept all three.
- **Session key:** a fresh **32 random bytes** per session (your AES-256 key).

Wire formats (byte concatenation, no length prefixes):

```
ECDH-wrapped key blob :  ephemeralPubKey(65) || nonce(12) || ciphertext || tag(16)
AES-GCM payload       :  nonce(12) || ciphertext || tag(16)
```

To **wrap** the session key for a peer pubkey: generate an ephemeral P-256
keypair, ECDH against the peer pubkey → 32-byte shared secret → AES-256-GCM
encrypt the 32-byte session key under that shared secret → output
`ephemeralPub || nonce || ct || tag`.

To **decrypt a relay frame**: each inbound WS message is JSON; the field
`payload` is base64 of `nonce(12) || ct || tag(16)`. AES-GCM-decrypt with the
session key. Some control frames may not be decryptable — skip those silently.

---

## 7. Algorithm — one inference, end to end

Execute in this exact order. Ordering callouts marked ⚠️ are mandatory.

1. **SIWE auth.** `GET /api/auth/challenge?address=<addr>` → sign `message` →
   `POST /api/auth/verify` → cache `{ jwt, expiresAt }`.
2. **List models.** `GET /api/models` → pick the `llama3-8b` entry; remember
   its `id` as `modelId`.
3. **Select worker.** `POST /api/sessions/select { modelId }` → get `worker`,
   `workerEncryptionKey`, `disputerEncryptionKey`.
4. **Session key.** Generate 32 random bytes = `sessionKey`.
5. **Wrap.** `encWorker = ecdhWrap(sessionKey, workerPub)`;
   `encDisputer = ecdhWrap(sessionKey, disputerPub)`.
6. **Prepare.** `POST /api/sessions/prepare { modelId, encWorkerKey:
   base64(encWorker), encDisputerKey: base64(encDisputer) }` → get
   `signature`, `expiry`, `worker`.
7. **`createSession` on-chain.** ⚠️ **Exact argument mapping (do not
   reorder/rename):**
   - `paramsHash`     ← `modelId` (the bytes32 digest)
   - `worker`         ← `prepared.worker`
   - `encWorkerKey`   ← `hexlify(encWorker)`
   - `ephemeralPubKey`← `hexlify(encDisputer)`  *(yes — the disputer-wrapped blob goes in the `ephemeralPubKey` slot; this is the protocol's expected layout)*
   - `initState`      ← `prepared.signature`
   - `expiry`         ← `BigInt(prepared.expiry)`
   - value `0`, gas limit `1_000_000`.
   Parse `sessionId` from the `SessionCreated` event in the receipt.
8. **Open the relay BEFORE submitting the job.** ⚠️ Poll
   `GET /api/sessions/:sessionId/token` until `200 {token}`; open the WS to
   `wss://.../ws?token=<token>`; attach the message handler that decrypts
   `payload` frames and appends plaintext to a buffer. Frames are live —
   if you submit the job before the socket is listening you lose output.
9. **Encrypt + upload prompt.** `cipher = aesEncrypt(sessionKey, utf8(prompt))`;
   `POST /api/blobs { data: base64(cipher) }` → `promptHash = blobHashes[0]`.
10. **`submitJob` on-chain.** `submitJob(sessionId, promptHash)` with
    `value = 0.02 LCAI`, gas limit `500_000`. Parse `jobId` from the
    `JobSubmitted` event.
11. **Await completion.** Poll `eth_getLogs` on `JobRegistry` for topic
    `JobCompleted` filtered by `jobId` (topic1 = `0x` + jobId hex, left-padded
    to 64). Loop ~every 5s, up to ~5 min. When found: wait a ~4s grace period
    for the final relay frame, close the WS, and the concatenated decrypted
    buffer is your **model output (string)**. The event's `responseHash` /
    `ciphertextHash` are the worker's on-chain commitments (keep for audit).

---

## 8. Reference implementation (TypeScript, Node, ethers v6)

Drop-in, dependency-light. Two logical parts: a gateway client (auth + crypto
+ HTTP) and a `runInference` orchestrator. Adapt as needed.

```ts
// lightchain-client.ts
import crypto from "node:crypto";
import WebSocket from "ws";
import {
  JsonRpcProvider, Wallet, Contract, Interface,
  parseEther, hexlify, type Log,
} from "ethers";

// ─────────────────────────── config ───────────────────────────
const RPC      = process.env.LIGHTCHAIN_RPC      ?? "https://rpc.mainnet.lightchain.ai";
const GATEWAY  = (process.env.LIGHTCHAIN_GATEWAY ?? "https://chat-api.mainnet.lightchain.ai").replace(/\/+$/, "");
const RELAY    = process.env.LIGHTCHAIN_RELAY    ?? "wss://relay.mainnet.lightchain.ai/ws";
const JOB_REG  = process.env.LIGHTCHAIN_JOB_REGISTRY ?? "0xfB15F90298e4CcD7106E76fFB5e520315cC42B0b";
const JOB_FEE  = parseEther(process.env.LIGHTCHAIN_JOB_FEE_LCAI ?? "0.02");

const JOB_REG_ABI = [
  "function createSession(bytes32 paramsHash, address worker, bytes encWorkerKey, bytes ephemeralPubKey, bytes initState, uint256 expiry) payable returns (uint256 sessionId)",
  "function submitJob(uint256 sessionId, bytes32 promptHash) payable returns (uint256 jobId)",
  "event SessionCreated(uint256 indexed sessionId, address indexed user, bytes32 indexed paramsHash, address worker, bytes encWorkerKey, bytes ephemeralPubKey)",
  "event JobSubmitted(uint256 indexed jobId, uint256 indexed sessionId, address worker)",
  "event JobCompleted(uint256 indexed jobId, address indexed worker, bytes32 responseHash, bytes32 ciphertextHash)",
];

// ─────────────────────────── crypto ───────────────────────────
function decodePubKey(s: string): Buffer {
  if (/^0x[0-9a-fA-F]{130}$/.test(s)) return Buffer.from(s.slice(2), "hex");
  if (/^[0-9a-fA-F]{130}$/.test(s))   return Buffer.from(s, "hex");
  const b = Buffer.from(s, "base64");
  if (b.length !== 65) throw new Error(`pubkey base64 -> ${b.length}B (need 65)`);
  return b;
}
/** ephemeralPub(65) || nonce(12) || ct || tag(16) */
function ecdhWrap(sessionKey: Buffer, peerPub: Buffer): Buffer {
  if (sessionKey.length !== 32) throw new Error("sessionKey must be 32 bytes");
  if (peerPub.length !== 65)    throw new Error("peer pubkey must be 65 bytes");
  const e = crypto.createECDH("prime256v1"); e.generateKeys();
  const ephemPub = e.getPublicKey(null, "uncompressed");
  const shared   = e.computeSecret(peerPub);              // 32-byte X coord
  const nonce    = crypto.randomBytes(12);
  const c        = crypto.createCipheriv("aes-256-gcm", shared, nonce);
  const ct       = Buffer.concat([c.update(sessionKey), c.final()]);
  return Buffer.concat([ephemPub, nonce, ct, c.getAuthTag()]);
}
/** nonce(12) || ct || tag(16) */
function aesEncrypt(key: Buffer, pt: Buffer): Buffer {
  const nonce = crypto.randomBytes(12);
  const c = crypto.createCipheriv("aes-256-gcm", key, nonce);
  const ct = Buffer.concat([c.update(pt), c.final()]);
  return Buffer.concat([nonce, ct, c.getAuthTag()]);
}
function aesDecrypt(key: Buffer, blob: Buffer): Buffer {
  if (blob.length < 12 + 16) throw new Error("ciphertext too short");
  const nonce = blob.subarray(0, 12);
  const tag   = blob.subarray(blob.length - 16);
  const ct    = blob.subarray(12, blob.length - 16);
  const d = crypto.createDecipheriv("aes-256-gcm", key, nonce);
  d.setAuthTag(tag);
  return Buffer.concat([d.update(ct), d.final()]);
}

// ─────────────────────────── gateway ──────────────────────────
class Gateway {
  private jwt: { token: string; expMs: number } | null = null;
  constructor(private wallet: Wallet) {}

  private async token(): Promise<string> {
    if (this.jwt && this.jwt.expMs - Date.now() > 30_000) return this.jwt.token;
    const ch = await (await fetch(
      `${GATEWAY}/api/auth/challenge?address=${this.wallet.address}`,
      { headers: { Accept: "application/json" } },
    )).json() as { message: string };
    const signature = await this.wallet.signMessage(ch.message);
    const v = await (await fetch(`${GATEWAY}/api/auth/verify`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: ch.message, signature }),
    })).json() as { token: string; expiresAt: string };
    if (!v.token) throw new Error("auth: no token returned");
    this.jwt = { token: v.token, expMs: new Date(v.expiresAt).getTime() };
    return v.token;
  }
  private async req<T>(path: string, init: RequestInit = {}, auth = true): Promise<T> {
    const headers: Record<string,string> = { Accept: "application/json", ...(init.headers as any) };
    if (init.body) headers["Content-Type"] = "application/json";
    if (auth) headers.Authorization = `Bearer ${await this.token()}`;
    const r = await fetch(`${GATEWAY}${path}`, { ...init, headers });
    const t = await r.text();
    if (!r.ok) throw new Error(`gateway ${path} ${r.status}: ${t.slice(0,300)}`);
    return JSON.parse(t) as T;
  }
  listModels() {
    return this.req<{ models: { id: string; name: string }[] }>("/api/models", {}, false);
  }
  selectSession(modelId: string) {
    return this.req<{ worker: string; workerEncryptionKey: string; disputerEncryptionKey: string; nonce: number; expiry: number }>(
      "/api/sessions/select", { method: "POST", body: JSON.stringify({ modelId }) });
  }
  prepareSession(b: { modelId: string; encWorkerKey: string; encDisputerKey: string }) {
    return this.req<{ worker: string; signature: string; expiry: number }>(
      "/api/sessions/prepare", { method: "POST", body: JSON.stringify(b) });
  }
  uploadBlob(base64: string) {
    return this.req<{ blobHashes: string[] }>(
      "/api/blobs", { method: "POST", body: JSON.stringify({ data: base64 }) });
  }
  async waitForRelayToken(sessionId: bigint, timeoutMs = 30_000): Promise<string> {
    const start = Date.now();
    while (Date.now() - start < timeoutMs) {
      const r = await fetch(`${GATEWAY}/api/sessions/${sessionId}/token`, {
        headers: { Accept: "application/json", Authorization: `Bearer ${await this.token()}` } });
      const t = await r.text();
      if (r.status === 200) {
        const p = JSON.parse(t);
        if (p?.token) return p.token as string;
      } else if (r.status !== 202 && r.status !== 401) {
        throw new Error(`relay token ${r.status}: ${t.slice(0,200)}`);
      }
      await new Promise(res => setTimeout(res, 1000));
    }
    throw new Error("relay token not ready in time");
  }
}

// ─────────────────────── orchestrator ─────────────────────────
export interface InferenceResult {
  output: string;
  worker: string;
  jobId: bigint;
  sessionId: bigint;
  responseHash: string;
  ciphertextHash: string;
  txs: { createSession: string; submitJob: string; jobCompleted: string };
}

export async function runInference(
  prompt: string,
  privateKey: string,
  log: (m: string) => void = () => {},
): Promise<InferenceResult> {
  const provider = new JsonRpcProvider(RPC);
  const wallet   = new Wallet(privateKey, provider);
  const gw       = new Gateway(wallet);
  const reg      = new Contract(JOB_REG, JOB_REG_ABI, wallet);
  const iface    = new Interface(JOB_REG_ABI);

  // 1-2. auth + model
  const { models } = await gw.listModels();
  const model = models.find(m => m.name === "llama3-8b") ?? models[0];
  if (!model) throw new Error("no models available");
  log(`model=${model.name}`);

  // 3. worker
  const sel = await gw.selectSession(model.id);
  log(`worker=${sel.worker}`);

  // 4-5. session key + wrap
  const sessionKey  = crypto.randomBytes(32);
  const encWorker   = ecdhWrap(sessionKey, decodePubKey(sel.workerEncryptionKey));
  const encDisputer = ecdhWrap(sessionKey, decodePubKey(sel.disputerEncryptionKey));

  // 6. prepare
  const prep = await gw.prepareSession({
    modelId: model.id,
    encWorkerKey:   encWorker.toString("base64"),
    encDisputerKey: encDisputer.toString("base64"),
  });

  // 7. createSession  (exact arg mapping — do not change)
  const tx1 = await reg.createSession(
    model.id, prep.worker,
    hexlify(encWorker), hexlify(encDisputer),
    prep.signature, BigInt(prep.expiry),
    { gasLimit: 1_000_000n },
  );
  const r1 = await tx1.wait(1);
  if (!r1 || r1.status !== 1) throw new Error("createSession reverted");
  const sessionId = parseEvent(r1.logs, iface, "SessionCreated", "sessionId") as bigint;
  log(`sessionId=${sessionId}`);

  // 8. OPEN RELAY BEFORE submitJob
  const relayToken = await gw.waitForRelayToken(sessionId);
  const ws = new WebSocket(`${RELAY}?token=${encodeURIComponent(relayToken)}`);
  await new Promise<void>((res, rej) => { ws.once("open", res); ws.once("error", rej); });
  const chunks: string[] = [];
  ws.on("message", (data) => {
    let frame: any;
    try { frame = JSON.parse(Buffer.from(data as any).toString("utf8")); } catch { return; }
    if (!frame?.payload) return;
    try { chunks.push(aesDecrypt(sessionKey, Buffer.from(frame.payload, "base64")).toString("utf8")); }
    catch { /* skip non-decryptable control frames */ }
  });
  log("relay connected");

  // 9. encrypt + upload prompt
  const cipher = aesEncrypt(sessionKey, Buffer.from(prompt, "utf8"));
  const { blobHashes } = await gw.uploadBlob(cipher.toString("base64"));
  if (!blobHashes?.length) throw new Error("no blob hash returned");

  // 10. submitJob (pay the fee)
  const tx2 = await reg.submitJob(sessionId, blobHashes[0], { value: JOB_FEE, gasLimit: 500_000n });
  const r2 = await tx2.wait(1);
  if (!r2 || r2.status !== 1) throw new Error("submitJob reverted");
  const jobId = parseEvent(r2.logs, iface, "JobSubmitted", "jobId") as bigint;
  log(`jobId=${jobId}`);

  // 11. await JobCompleted
  const topic   = iface.getEvent("JobCompleted")!.topicHash;
  const jobTop  = "0x" + jobId.toString(16).padStart(64, "0");
  let done: Log | null = null;
  for (let i = 0; i < 60 && !done; i++) {
    await new Promise(r => setTimeout(r, 5000));
    const head = await provider.getBlockNumber();
    const logs = await provider.getLogs({
      address: JOB_REG, fromBlock: r2.blockNumber!, toBlock: head, topics: [topic, jobTop],
    });
    if (logs.length) done = logs[0];
  }
  if (!done) throw new Error("timeout waiting for JobCompleted");
  await new Promise(r => setTimeout(r, 4000)); // grace for last frame
  ws.close();

  const p = iface.parseLog(done)!;
  return {
    output: chunks.join(""),
    worker: p.args.worker,
    jobId, sessionId,
    responseHash:   p.args.responseHash,
    ciphertextHash: p.args.ciphertextHash,
    txs: { createSession: tx1.hash, submitJob: tx2.hash, jobCompleted: done.transactionHash },
  };
}

function parseEvent(logs: readonly Log[], iface: Interface, name: string, field: string): unknown {
  for (const l of logs) { try { const p = iface.parseLog(l); if (p?.name === name) return p.args[field]; } catch {} }
  throw new Error(`${name} not found in receipt`);
}

// ─────────────────────────── demo ─────────────────────────────
if (require.main === module) {
  const pk = process.env.PRIVATE_KEY;
  if (!pk) throw new Error("set PRIVATE_KEY (funded mainnet wallet)");
  runInference("Reply with a one-sentence fun fact about the ocean.", pk, m => console.log(" ·", m))
    .then(r => { console.log("\nOUTPUT:", r.output); console.log("worker:", r.worker, "jobId:", r.jobId.toString());
                 console.log("txs:", r.txs); })
    .catch(e => { console.error("FAILED:", e); process.exit(1); });
}
```

Run it:
```bash
PRIVATE_KEY=0x... npx tsx lightchain-client.ts
```

---

## 9. Error handling & edge cases

- **JWT expiry:** cache `expiresAt`; re-handshake when within ~30s of expiry
  or on any `401`.
- **Relay race:** never call `submitJob` before the WebSocket `open` event and
  the message handler are attached — frames are live and unbuffered.
- **Undecryptable frames:** the relay may interleave control frames; skip any
  `payload` that fails AES-GCM auth instead of throwing.
- **`JobCompleted` timeout:** budget ~5 min (60 × 5s). If it never arrives the
  worker stalled — surface an error; the spend is the on-chain fee only.
- **Insufficient funds:** `submitJob` reverts if the wallet can't cover
  `0.02 LCAI` + gas. Check balance before submitting; there is no mainnet
  faucet.
- **Idempotency / retries:** a new attempt = a new session + new fee. Don't
  blindly auto-retry a paid job; treat `JobCompleted` (by `jobId`) as the
  single source of truth.
- **Output parsing:** the model returns free text. If you need structured
  output, instruct the model in the prompt and parse defensively
  (LLMs are not perfectly deterministic).

---

## 10. Pre-flight: confirm the worker pool is live

Before integrating, verify there are active workers (no auth needed):

```bash
curl -s -X POST -H 'content-type: application/json' \
  --data '{"query":"{ workers(first:20){ id stake status active_job_count jobs_completed } }"}' \
  https://workers-api.mainnet.lightchain.ai/graphql
```

Expect entries with active `status` and nonzero `stake`. If the pool is empty,
`selectSession` will fail or assign an unresponsive worker.

---

## 11. Cost summary

| Item | Cost (LCAI) |
|---|---|
| Worker fee (`submitJob` value) | 0.020 |
| `createSession` gas | ~0.0006 |
| `submitJob` gas | ~0.0003 |
| **Per inference** | **~0.022** |

---

## 12. Caveats & provenance

- These mainnet endpoints were verified live and are stable, but the
  gateway/relay/subgraph hostnames are **not in LightChain's public docs** —
  they were discovered via certificate-transparency enumeration and confirmed
  against LightChain's own open-source reference client (`lcai-chat-v2`) and
  on-chain bytecode. If a hostname changes, only the constants in §2 need
  updating; the protocol is unchanged.
- The crypto is intentionally simple (raw ECDH secret as the AES key, no KDF)
  to stay wire-compatible with the network's worker/relay implementation. Do
  not "harden" it with an HKDF — that breaks interop.
- Mainnet ↔ testnet differ only by the §2 constants. Develop against testnet
  (it has a faucet at `https://lightfaucet.ai`); ship against mainnet.

---

*End of integration guide. Everything required to implement a working client
is contained above.*
