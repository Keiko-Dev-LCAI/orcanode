#!/usr/bin/env python3
"""
Node Builder – "Node in a Day" Wizard Backend
Port 8185 | AI chat via Lightchain AIVM decentralized inference

Answers questions about setting up a Lightchain AI worker node.
Every question costs ~0.02 LCAI (paid by dApp wallet), node earns back ~0.016.
Set LIGHTCHAIN_PRIVATE_KEY env var (same dApp wallet as other Orca apps).

Run: python3 ~/Desktop/orcanode/orcanode-server.py
"""

import sys
sys.path.insert(0, '/home/keiko/pylibs')

from http.server import HTTPServer, BaseHTTPRequestHandler
import json, os, threading, time, secrets, base64
from urllib.parse import urlparse, quote as url_quote

PORT = 8185

# ════════════════════════════════════════════════════════════════════════
# SYSTEM PROMPT — Full Node Builder knowledge base
# ════════════════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """You are the Node Builder Wizard, an AI assistant built specifically to help people set up and operate a Lightchain AI worker node. You have deep, verified knowledge of the entire setup process from a real operator who runs a node on Lightchain mainnet.

Answer questions clearly and practically. Use copy-paste ready commands where helpful. Be concise — most people asking questions are mid-setup and want direct answers.

== VERIFIED WORKING CONFIGURATION (Lightchain Mainnet) ==

SUPPORTED_MODELS=llama3-8b        ← use DASH, not colon (llama3-8b NOT llama3:8b)
OLLAMA_URL=http://host.docker.internal:11434
CHAIN_ID=9200
RPC_URL=https://rpc.mainnet.lightchain.ai
BEACON_API_URL=https://beacon.mainnet.lightchain.ai
WORKER_REGISTRY_ADDRESS=0x0000000000000000000000000000000000001002
WORKER_GATEWAY_URL=https://worker-gateway.mainnet.lightchain.ai
DO NOT SET MODELS_MAP — community confirmed it breaks things

== CRITICAL OLLAMA STEP (Most Common Mistake) ==

After pulling the llama3 model, you MUST create a bare alias:
  ollama cp llama3:8b llama3-8b

Without this step, the worker will fail to find the model. This is the #1 reason nodes fail to pick up jobs after correct setup. The SUPPORTED_MODELS env var uses the dash format (llama3-8b), so Ollama must have a model with that exact name.

== HARDWARE REQUIREMENTS ==

Minimum:
- CPU: 8+ cores recommended
- RAM: 32 GB recommended
- GPU: NVIDIA with 8+ GB VRAM (RTX 3080 or better)
- Storage: 100+ GB SSD
- Network: 100+ Mbps, stable connection

The official node on Lightchain uses NVIDIA H200s. Community nodes can run on consumer hardware like RTX 3080, 3090, 4080, 4090, 5070, 5080, 5090.

== STEP-BY-STEP SETUP OVERVIEW ==

0. Prerequisites check: Do you have 50,001+ LCAI to stake?
1. Hardware: NVIDIA GPU with 8+ GB VRAM, 32+ GB RAM, 100+ GB SSD
2. OS: Ubuntu 22.04 LTS recommended
3. Prerequisites: NVIDIA drivers + CUDA, Docker + nvidia-container-toolkit, Foundry (cast), Redis, Mullvad VPN
4. Generate worker key (SEPARATE from your funder wallet):
   cast wallet new
   Save the private key and address securely.
5. Resolve contract addresses on-chain (verify they haven't changed):
   cast call 0x0000000000000000000000000000000000001000 "getAddress(string)(address)" "WorkerRegistry" --rpc-url https://rpc.mainnet.lightchain.ai
6. Install Ollama and pull model:
   curl -fsSL https://ollama.ai/install.sh | sh
   ollama pull llama3:8b
   ollama cp llama3:8b llama3-8b   ← CRITICAL bare alias step
7. Pull worker Docker image:
   docker pull lightchain/lcai-worker:latest
8. Import key and generate ECDH encryption key:
   cast wallet import worker --private-key YOUR_WORKER_PRIVATE_KEY
   openssl ecparam -name prime256v1 -genkey -noout -out worker-ecdh.pem
   openssl ec -in worker-ecdh.pem -pubout -out worker-ecdh-pub.pem
9. Fund worker wallet with ~100 LCAI for gas (send from funder wallet)
10. Register on-chain (costs ~7,500 LCAI stake):
    cast send 0x0000000000000000000000000000000000001002 "registerWorker(string,bytes)" "llama3-8b" $(cat worker-ecdh-pub.pem | base64 -w0) --private-key YOUR_WORKER_PRIVATE_KEY --value 7500000000000000000000 --rpc-url https://rpc.mainnet.lightchain.ai --chain-id 9200
11. Run the worker:
    docker run -d --name lcai-worker --gpus all --network host \\
      --add-host=host.docker.internal:host-gateway \\
      -e PRIVATE_KEY=YOUR_WORKER_PRIVATE_KEY \\
      -e ECDH_KEY=$(cat worker-ecdh.pem | base64 -w0) \\
      -e SUPPORTED_MODELS=llama3-8b \\
      -e OLLAMA_URL=http://host.docker.internal:11434 \\
      -e CHAIN_ID=9200 \\
      -e RPC_URL=https://rpc.mainnet.lightchain.ai \\
      -e BEACON_API_URL=https://beacon.mainnet.lightchain.ai \\
      -e WORKER_REGISTRY_ADDRESS=0x0000000000000000000000000000000000001002 \\
      -e WORKER_GATEWAY_URL=https://worker-gateway.mainnet.lightchain.ai \\
      lightchain/lcai-worker:latest
12. Health checks (see below)
13. Resources: workers.lightchain.ai, Discord: discord.gg/lightchain

== HEALTHY STARTUP LOG LINES ==

When your node starts correctly, look for these 6 lines in the logs (docker logs lcai-worker):
  worker registration validated — on-chain key matches local key
  blob mode: eip-4844 (beacon)
  authenticated with worker-gateway
  worker service initialized (gateway mode)
  worker sidecar running (gateway mode)
  websocket connected to gateway

If you see all 6, your node is running correctly.

== NORMAL LOG MESSAGES (Not Errors) ==

- "WebSocket EOF" or "websocket reconnecting" every ~1 hour = NORMAL. This is the auth token refresh cycle. Expected behavior.
- "worker_ollama_up=0" in logs = COSMETIC only. Does not affect job processing. Ignore it.
- "scheduler: batch release succeeded" = payouts are being processed. This is a GOOD sign.

== 10-POINT HEALTH CHECK ==

1. Docker container status:
   docker ps | grep lcai-worker
   (should show "Up" and healthy)

2. Worker logs (last 50 lines):
   docker logs lcai-worker --tail 50

3. Redis health:
   redis-cli ping
   (should return PONG)

4. Ollama API:
   curl http://localhost:11434/api/tags
   (should list llama3-8b model — with DASH)

5. GPU status:
   nvidia-smi
   (should show your GPU and VRAM usage)

6. Disk space:
   df -h /
   (should have 20+ GB free)

7. VPN status:
   mullvad status
   (should show "Connected")

8. Docker resource usage:
   docker stats lcai-worker --no-stream

9. On-chain job count (subgraph query):
   curl -s -X POST https://workers-api.mainnet.lightchain.ai/graphql \\
     -H "Content-Type: application/json" \\
     -d '{"query":"{ workers(where:{id:\"YOUR_WORKER_ADDRESS\"}) { id jobsCompleted totalEarned offenseCount } }"}' | python3 -m json.tool

10. Worker explorer:
    https://workers.lightchain.ai
    (search your worker address)

== VPN REQUIREMENT ==

A VPN is required if your ISP blocks Lightchain RPC calls. Known ISPs that block: Cox, some Comcast configurations. If registration or running fails with connection errors, try Mullvad VPN first. Connect before starting the worker.

== SLASH RISK WARNING ==

NEVER deregister your node if you have pending jobs. The slash penalty is approximately 7,500 LCAI (your entire stake). If you have problems, restart the Docker container first. Only deregister if absolutely necessary and you have confirmed zero pending jobs.

To check pending jobs before deregistering:
  cast call 0x0000000000000000000000000000000000001002 "getWorkerJobs(address)(uint256[])" YOUR_WORKER_ADDRESS --rpc-url https://rpc.mainnet.lightchain.ai

== STAKING REQUIREMENT ==

- Minimum stake to register: 50,001 LCAI
- Stake is locked while registered
- Higher stake = higher routing priority (more jobs)
- Staking delegation is expected in a future update

== FUNDER vs WORKER WALLET ==

CRITICAL: Use TWO separate wallets:
- Funder wallet: holds your main LCAI balance, sends stake + gas to worker
- Worker wallet: separate key used only for node operations, holds small amount for gas

Never use your main wallet as the worker private key. The worker private key is stored in your Docker command/env file.

== PAYOUT INFORMATION ==

- Jobs pay approximately 0.016 LCAI each to the worker
- Payouts are batched and released periodically
- "scheduler: batch release succeeded" in logs = payout batch processed
- Check earnings: workers.lightchain.ai or subgraph API

== KEY URLS ==

- Worker explorer: https://workers.lightchain.ai
- Official setup docs: https://workers.lightchain.ai/run-node
- Subgraph API: https://workers-api.mainnet.lightchain.ai/graphql
- Worker toolkit: https://github.com/lightchain-protocol/lightchain-worker-toolkit
- Smart contracts: https://github.com/lightchain-protocol/lcai-smart-contract
- Discord support: https://discord.gg/lightchain

== HARDWARE TIPS ==

- Get a UPS (uninterruptible power supply). Power outages can interrupt jobs mid-processing, and if timed badly with deregistration, could trigger a slash.
- Keep a phone hotspot ready as ISP backup. Node going offline during job processing is bad for your stats.
- VRAM: llama3:8b requires ~5 GB VRAM. If you're running other GPU applications (like image generation), make sure you have enough headroom.

Answer the user's question below based on this knowledge. Be helpful, direct, and practical. If you don't know something, say so honestly."""


# ════════════════════════════════════════════════════════════════════════
# AIVM CLIENT (same pattern as orcalearn-server.py)
# ════════════════════════════════════════════════════════════════════════

AIVM_GATEWAY  = "https://chat-api.mainnet.lightchain.ai"
AIVM_RELAY    = "wss://relay.mainnet.lightchain.ai/ws"
AIVM_RPC      = "https://rpc.mainnet.lightchain.ai"
AIVM_JOB_REG  = "0xfB15F90298e4CcD7106E76fFB5e520315cC42B0b"
AIVM_JOB_FEE  = 20_000_000_000_000_000   # 0.02 LCAI in wei
AIVM_CHAIN_ID = 9200

AIVM_ABI = [
    {
        "name": "createSession", "type": "function", "stateMutability": "payable",
        "inputs": [
            {"name": "paramsHash",     "type": "bytes32"},
            {"name": "worker",         "type": "address"},
            {"name": "encWorkerKey",   "type": "bytes"},
            {"name": "ephemeralPubKey","type": "bytes"},
            {"name": "initState",      "type": "bytes"},
            {"name": "expiry",         "type": "uint256"},
        ],
        "outputs": [{"name": "sessionId", "type": "uint256"}],
    },
    {
        "name": "submitJob", "type": "function", "stateMutability": "payable",
        "inputs": [
            {"name": "sessionId",  "type": "uint256"},
            {"name": "promptHash", "type": "bytes32"},
        ],
        "outputs": [{"name": "jobId", "type": "uint256"}],
    },
    {
        "anonymous": False, "name": "SessionCreated", "type": "event",
        "inputs": [
            {"indexed": True,  "name": "sessionId",     "type": "uint256"},
            {"indexed": True,  "name": "user",           "type": "address"},
            {"indexed": True,  "name": "paramsHash",     "type": "bytes32"},
            {"indexed": False, "name": "worker",         "type": "address"},
            {"indexed": False, "name": "encWorkerKey",   "type": "bytes"},
            {"indexed": False, "name": "ephemeralPubKey","type": "bytes"},
        ],
    },
    {
        "anonymous": False, "name": "JobSubmitted", "type": "event",
        "inputs": [
            {"indexed": True,  "name": "jobId",     "type": "uint256"},
            {"indexed": True,  "name": "sessionId", "type": "uint256"},
            {"indexed": False, "name": "worker",    "type": "address"},
        ],
    },
    {
        "anonymous": False, "name": "JobCompleted", "type": "event",
        "inputs": [
            {"indexed": True,  "name": "jobId",          "type": "uint256"},
            {"indexed": True,  "name": "worker",          "type": "address"},
            {"indexed": False, "name": "responseHash",    "type": "bytes32"},
            {"indexed": False, "name": "ciphertextHash",  "type": "bytes32"},
        ],
    },
]


def _decode_pubkey(s):
    if isinstance(s, (bytes, bytearray)):
        return bytes(s)
    s = s.strip()
    if s.startswith('0x') or s.startswith('0X'):
        b = bytes.fromhex(s[2:])
    elif len(s) == 130 and all(c in '0123456789abcdefABCDEF' for c in s):
        b = bytes.fromhex(s)
    else:
        b = base64.b64decode(s)
    if len(b) != 65:
        raise ValueError(f"pubkey decode: expected 65 bytes, got {len(b)}")
    return b


def _ecdh_wrap(session_key: bytes, peer_pub_bytes: bytes) -> bytes:
    from cryptography.hazmat.primitives.asymmetric.ec import (
        generate_private_key, ECDH, EllipticCurvePublicNumbers, SECP256R1
    )
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.backends import default_backend

    x = int.from_bytes(peer_pub_bytes[1:33], 'big')
    y = int.from_bytes(peer_pub_bytes[33:65], 'big')
    peer_pub = EllipticCurvePublicNumbers(x, y, SECP256R1()).public_key(default_backend())
    ephem_priv = generate_private_key(SECP256R1(), default_backend())
    shared = ephem_priv.exchange(ECDH(), peer_pub)
    pub_nums = ephem_priv.public_key().public_numbers()
    ephem_pub_bytes = (b'\x04' +
                       pub_nums.x.to_bytes(32, 'big') +
                       pub_nums.y.to_bytes(32, 'big'))
    nonce  = secrets.token_bytes(12)
    ct_tag = AESGCM(shared).encrypt(nonce, session_key, None)
    return ephem_pub_bytes + nonce + ct_tag


def _aes_encrypt(key: bytes, plaintext: bytes) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    nonce = secrets.token_bytes(12)
    return nonce + AESGCM(key).encrypt(nonce, plaintext, None)


def _aes_decrypt(key: bytes, blob: bytes) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    if len(blob) < 28:
        raise ValueError("ciphertext too short")
    return AESGCM(key).decrypt(blob[:12], blob[12:], None)


class AIVMClient:
    def __init__(self, private_key: str):
        import requests as _req
        from web3 import Web3
        from eth_account import Account

        self._req     = _req
        self._w3      = Web3(Web3.HTTPProvider(AIVM_RPC))
        self._account = Account.from_key(private_key)
        self._registry = self._w3.eth.contract(
            address=Web3.to_checksum_address(AIVM_JOB_REG),
            abi=AIVM_ABI,
        )
        self._jwt     = None
        self._jwt_exp = 0
        print(f"  [AIVM] wallet: {self._account.address}")

    def _get_jwt(self) -> str:
        from eth_account.messages import encode_defunct
        if self._jwt and time.time() < self._jwt_exp - 30:
            return self._jwt
        r = self._req.get(
            f"{AIVM_GATEWAY}/api/auth/challenge",
            params={"address": self._account.address}, timeout=15,
        )
        r.raise_for_status()
        message = r.json()["message"]
        sig = self._account.sign_message(encode_defunct(text=message))
        r2 = self._req.post(
            f"{AIVM_GATEWAY}/api/auth/verify",
            json={"message": message, "signature": "0x" + sig.signature.hex()},
            timeout=15,
        )
        r2.raise_for_status()
        v = r2.json()
        self._jwt = v["token"]
        exp_str = v["expiresAt"][:19].replace("T", " ")
        self._jwt_exp = time.mktime(time.strptime(exp_str, "%Y-%m-%d %H:%M:%S"))
        return self._jwt

    def _auth_headers(self):
        return {
            "Authorization": f"Bearer {self._get_jwt()}",
            "Accept":        "application/json",
            "Content-Type":  "application/json",
        }

    def run_inference(self, prompt: str, timeout_secs: int = 360) -> str:
        import websocket as _ws
        from web3 import Web3

        req = self._req
        print(f"  [AIVM] starting inference ({len(prompt)} chars)")

        r = req.get(f"{AIVM_GATEWAY}/api/models", timeout=15)
        r.raise_for_status()
        models = r.json().get("models", [])
        model  = next((m for m in models if m["name"] == "llama3-8b"), models[0] if models else None)
        if not model:
            raise RuntimeError("No models available from AIVM gateway")
        model_id = model["id"]
        print(f"  [AIVM] model: {model['name']} id={model_id[:10]}...")

        # Try to route to Keiko's own worker node first
        MY_WORKER = "0x1F899FaD2C8BD70b6eF356ae6cC3c0abDbB15EB5"
        sel = None
        for attempt_body in [
            {"modelId": model_id, "workerAddress": MY_WORKER},
            {"modelId": model_id, "worker": MY_WORKER},
            {"modelId": model_id},  # fallback: any available worker
        ]:
            try:
                r = req.post(
                    f"{AIVM_GATEWAY}/api/sessions/select",
                    json=attempt_body,
                    headers=self._auth_headers(), timeout=15,
                )
                if r.ok:
                    sel = r.json()
                    break
            except Exception:
                continue
        if not sel:
            raise RuntimeError("Worker selection failed")
        routed_to = sel.get('worker', '?')
        if routed_to.lower() == MY_WORKER.lower():
            print(f"  [AIVM] worker: {routed_to} (OUR NODE ✓)")
        else:
            print(f"  [AIVM] worker: {routed_to} (not our node)")

        session_key  = secrets.token_bytes(32)
        enc_worker   = _ecdh_wrap(session_key, _decode_pubkey(sel["workerEncryptionKey"]))
        enc_disputer = _ecdh_wrap(session_key, _decode_pubkey(sel["disputerEncryptionKey"]))

        r = req.post(
            f"{AIVM_GATEWAY}/api/sessions/prepare",
            json={
                "modelId":        model_id,
                "encWorkerKey":   base64.b64encode(enc_worker).decode(),
                "encDisputerKey": base64.b64encode(enc_disputer).decode(),
            },
            headers=self._auth_headers(), timeout=15,
        )
        r.raise_for_status()
        prep = r.json()

        def _h(s): return s[2:] if isinstance(s, str) and s[:2].lower() == '0x' else s
        params_hash = bytes.fromhex(_h(model_id).zfill(64))
        sig_bytes   = bytes.fromhex(_h(prep["signature"]))
        gas_price   = self._w3.eth.gas_price
        nonce_val   = self._w3.eth.get_transaction_count(self._account.address)

        tx = self._registry.functions.createSession(
            params_hash,
            Web3.to_checksum_address(prep["worker"]),
            enc_worker,
            enc_disputer,
            sig_bytes,
            prep["expiry"],
        ).build_transaction({
            "from":     self._account.address,
            "nonce":    nonce_val,
            "gas":      1_000_000,
            "gasPrice": gas_price,
            "value":    0,
            "chainId":  AIVM_CHAIN_ID,
        })
        signed  = self._account.sign_transaction(tx)
        tx_hash = self._w3.eth.send_raw_transaction(signed.raw_transaction)
        print(f"  [AIVM] createSession tx: {tx_hash.hex()}")
        receipt1 = self._w3.eth.wait_for_transaction_receipt(tx_hash, timeout=90)
        if receipt1.status != 1:
            raise RuntimeError("createSession reverted on-chain")

        session_id = None
        for log in receipt1.logs:
            try:
                evt = self._registry.events.SessionCreated().process_log(log)
                session_id = evt["args"]["sessionId"]
                break
            except Exception:
                pass
        if session_id is None:
            raise RuntimeError("SessionCreated event not found in receipt")
        print(f"  [AIVM] sessionId: {session_id}")

        relay_token = None
        deadline = time.time() + 120
        while time.time() < deadline:
            r = req.get(
                f"{AIVM_GATEWAY}/api/sessions/{session_id}/token",
                headers=self._auth_headers(), timeout=10,
            )
            if r.status_code == 200:
                d = r.json()
                if d.get("token"):
                    relay_token = d["token"]
                    break
            time.sleep(1)
        if not relay_token:
            raise RuntimeError("Relay token not ready within 120s")

        chunks   = []
        ws_ready = threading.Event()
        ws_err   = [None]

        def _on_message(ws_obj, message):
            try:
                frame   = json.loads(message)
                payload = frame.get("payload")
                if not payload:
                    return
                blob = base64.b64decode(payload)
                try:
                    pt = _aes_decrypt(session_key, blob)
                    chunks.append(pt.decode("utf-8", errors="replace"))
                except Exception:
                    pass
            except Exception:
                pass

        def _on_open(ws_obj):
            ws_ready.set()

        def _on_error(ws_obj, err):
            ws_err[0] = err
            ws_ready.set()

        ws = _ws.WebSocketApp(
            f"{AIVM_RELAY}?token={url_quote(relay_token)}",
            on_message=_on_message,
            on_open=_on_open,
            on_error=_on_error,
        )
        ws_thread = threading.Thread(target=ws.run_forever, daemon=True)
        ws_thread.start()
        ws_ready.wait(timeout=15)
        if ws_err[0]:
            raise RuntimeError(f"WebSocket failed: {ws_err[0]}")
        print("  [AIVM] relay connected")

        cipher = _aes_encrypt(session_key, prompt.encode("utf-8"))
        r = req.post(
            f"{AIVM_GATEWAY}/api/blobs",
            json={"data": base64.b64encode(cipher).decode()},
            headers=self._auth_headers(), timeout=15,
        )
        r.raise_for_status()
        blob_hashes = r.json().get("blobHashes", [])
        if not blob_hashes:
            raise RuntimeError("No blob hash returned from gateway")
        prompt_hash = bytes.fromhex(_h(blob_hashes[0]).zfill(64))

        nonce_val2 = self._w3.eth.get_transaction_count(self._account.address)
        tx2 = self._registry.functions.submitJob(
            session_id,
            prompt_hash,
        ).build_transaction({
            "from":     self._account.address,
            "nonce":    nonce_val2,
            "gas":      500_000,
            "gasPrice": gas_price,
            "value":    AIVM_JOB_FEE,
            "chainId":  AIVM_CHAIN_ID,
        })
        signed2  = self._account.sign_transaction(tx2)
        tx_hash2 = self._w3.eth.send_raw_transaction(signed2.raw_transaction)
        print(f"  [AIVM] submitJob tx: {tx_hash2.hex()}")
        receipt2 = self._w3.eth.wait_for_transaction_receipt(tx_hash2, timeout=90)
        if receipt2.status != 1:
            raise RuntimeError("submitJob reverted — check LCAI balance")

        job_id = None
        for log in receipt2.logs:
            try:
                evt = self._registry.events.JobSubmitted().process_log(log)
                job_id = evt["args"]["jobId"]
                break
            except Exception:
                pass
        if job_id is None:
            raise RuntimeError("JobSubmitted event not found in receipt")
        print(f"  [AIVM] jobId: {job_id}")

        # Fix: Web3.keccak().hex() returns WITHOUT 0x — must add it manually
        job_completed_topic = "0x" + Web3.keccak(
            text="JobCompleted(uint256,address,bytes32,bytes32)"
        ).hex()
        job_id_topic = "0x" + hex(job_id)[2:].zfill(64)

        done     = False
        deadline = time.time() + timeout_secs
        while time.time() < deadline and not done:
            time.sleep(5)

            # Return early if relay already delivered the answer
            if chunks:
                print(f"  [AIVM] relay data arrived ({len(chunks)} chunks), returning early")
                done = True
                break

            try:
                head = self._w3.eth.block_number
                logs = self._w3.eth.get_logs({
                    "address":   Web3.to_checksum_address(AIVM_JOB_REG),
                    "fromBlock": receipt2.blockNumber,
                    "toBlock":   head,
                    "topics":    [job_completed_topic, job_id_topic],
                })
                if logs:
                    done = True
                    print(f"  [AIVM] JobCompleted on-chain!")
            except Exception as e:
                print(f"  [AIVM] log poll error (retrying): {e}")

        time.sleep(2)  # grace period for final relay frames
        ws.close()

        result = "".join(chunks)
        if result:
            print(f"  [AIVM] inference done ({len(result)} chars)")
            return result

        if not done:
            raise RuntimeError(f"Timeout after {timeout_secs}s waiting for JobCompleted")

        print(f"  [AIVM] inference done, {len(result)} chars")
        return result


_aivm_client = None


def get_aivm_client():
    global _aivm_client
    pk = os.environ.get("LIGHTCHAIN_PRIVATE_KEY", "").strip()
    if not pk:
        return None
    if _aivm_client is None:
        try:
            _aivm_client = AIVMClient(pk)
        except Exception as e:
            print(f"  [AIVM] init failed: {e}")
            return None
    return _aivm_client


def run_inference(question: str, timeout: int = 300) -> str:
    full_prompt = SYSTEM_PROMPT + "\n\nUser question: " + question
    client = get_aivm_client()
    if client:
        try:
            return client.run_inference(full_prompt, timeout_secs=timeout)
        except Exception as e:
            print(f"  [AIVM] failed: {e}")
            raise
    raise RuntimeError("AI unavailable — LIGHTCHAIN_PRIVATE_KEY not set or AIVM unreachable")


# ════════════════════════════════════════════════════════════════════════
# HTTP SERVER
# ════════════════════════════════════════════════════════════════════════

SERVER_START = time.time()

# Node compare (reference profile diff)
try:
    from node_compare import compare_to_reference
except ImportError:
    compare_to_reference = None

# In-flight job tracking
_jobs      = {}
_jobs_lock = threading.Lock()


class Handler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        pass  # suppress default logs

    def _send_json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, msg, code=400):
        self._send_json({"error": msg}, code)

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length))
        except Exception:
            return {}

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def _serve_html(self, filename):
        html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)
        try:
            with open(html_path, "rb") as f:
                body = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except FileNotFoundError:
            self._send_error(filename + " not found", 404)

    def do_GET(self):
        parsed = urlparse(self.path)
        path   = parsed.path.rstrip("/")

        # Serve HTML from the local server so AI chat + health checks work
        # (avoids HTTPS→HTTP mixed-content block from GitHub Pages)
        if path == "" or path == "/":
            self._serve_html("index.html")
            return

        if path in ("/compare", "/compare.html"):
            self._serve_html("compare.html")
            return

        if path == "/api/health":
            uptime = int(time.time() - SERVER_START)
            h, rem = divmod(uptime, 3600)
            m = rem // 60
            client = get_aivm_client()
            self._send_json({
                "ok":     True,
                "uptime": uptime,
                "uptimeLabel": f"{h}h {m}m",
                "aivm":  bool(client),
            })
            return

        if path == "/api/job":
            from urllib.parse import parse_qs
            qs     = parse_qs(parsed.query)
            job_id = qs.get("id", [""])[0].strip()
            with _jobs_lock:
                job = _jobs.get(job_id)
            if not job:
                self._send_error("Job not found", 404)
                return
            self._send_json(job)
            return

        if path == "/api/node-check":
            self._handle_node_check()
            return

        if path == "/api/hardware-check":
            self._handle_hardware_check()
            return

        if path == "/api/compare":
            self._handle_compare_get(parsed)
            return

        self._send_error("Not found", 404)

    def _handle_hardware_check(self):
        """Check hardware against Lightchain worker minimum requirements."""
        import subprocess, re

        def run(cmd, timeout=8):
            try:
                r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
                return {"ok": r.returncode == 0, "output": (r.stdout + r.stderr).strip()}
            except Exception as e:
                return {"ok": False, "output": str(e)}

        result = {}

        # GPU — name + VRAM
        r = run("nvidia-smi --query-gpu=name,memory.total --format=csv,noheader")
        if r["ok"] and r["output"]:
            lines = [l.strip() for l in r["output"].splitlines() if l.strip()]
            gpus = []
            total_vram = 0
            for line in lines:
                parts = line.split(",")
                name = parts[0].strip() if parts else "Unknown GPU"
                vram_str = parts[1].strip() if len(parts) > 1 else "0 MiB"
                vram_mb = int(re.search(r'\d+', vram_str).group()) if re.search(r'\d+', vram_str) else 0
                vram_gb = round(vram_mb / 1024, 1)
                total_vram += vram_gb
                gpus.append({"name": name, "vram_gb": vram_gb})
            ok = total_vram >= 8
            result["gpu"] = {
                "label": "GPU (min 8 GB VRAM)",
                "ok": ok,
                "gpus": gpus,
                "total_vram_gb": total_vram,
                "output": f"{', '.join(g['name'] for g in gpus)} — {total_vram} GB VRAM total",
                "tip": None if ok else f"You have {total_vram} GB VRAM. Minimum is 8 GB for llama3-8b.",
            }
        else:
            result["gpu"] = {
                "label": "GPU (min 8 GB VRAM)",
                "ok": False,
                "output": "nvidia-smi not found — NVIDIA drivers may not be installed.",
                "tip": "Install NVIDIA drivers: sudo apt install nvidia-driver-535 then reboot.",
            }

        # RAM
        r = run("free -m | awk '/^Mem:/ {print $2}'")
        ram_mb = int(r["output"]) if r["ok"] and r["output"].isdigit() else 0
        ram_gb = round(ram_mb / 1024, 1)
        ok = ram_gb >= 16
        result["ram"] = {
            "label": "RAM (min 16 GB)",
            "ok": ok,
            "ram_gb": ram_gb,
            "output": f"{ram_gb} GB installed",
            "tip": None if ok else f"You have {ram_gb} GB RAM. Minimum is 16 GB, recommended 32 GB.",
        }

        # CPU cores
        r = run("nproc")
        cores = int(r["output"]) if r["ok"] and r["output"].isdigit() else 0
        ok = cores >= 4
        result["cpu"] = {
            "label": "CPU (min 4 cores)",
            "ok": ok,
            "cores": cores,
            "output": f"{cores} logical cores",
            "tip": None if ok else f"You have {cores} cores. Minimum is 4 cores.",
        }

        # Disk space (free GB on /)
        r = run("df -BG / | awk 'NR==2 {print $4}' | tr -d 'G'")
        disk_free = int(r["output"]) if r["ok"] and r["output"].isdigit() else 0
        ok = disk_free >= 100
        result["disk"] = {
            "label": "Disk space (min 100 GB free)",
            "ok": ok,
            "free_gb": disk_free,
            "output": f"{disk_free} GB free on /",
            "tip": None if ok else f"Only {disk_free} GB free. You need at least 100 GB free for Docker images and model files.",
        }

        passed = sum(1 for c in result.values() if c["ok"])
        total = len(result)
        meets_min = passed == total
        self._send_json({
            "ok": True,
            "passed": passed,
            "total": total,
            "meets_minimum": meets_min,
            "summary": "✅ Your machine meets all requirements!" if meets_min else f"⚠️ {passed}/{total} requirements met",
            "checks": result,
        })

    def _handle_node_check(self):
        """Run all 10 health checks and return results as JSON."""
        import subprocess, json as _json
        try:
            self._run_node_check()
        except Exception as e:
            self._send_json({"ok": False, "error": f"Check failed: {e}", "checks": {}, "passed": 0, "total": 0, "summary": "Error running checks"})

    def _run_node_check(self):
        import subprocess, json as _json

        def run(cmd, timeout=10):
            try:
                r = subprocess.run(
                    cmd, shell=True, capture_output=True, text=True, timeout=timeout
                )
                out = (r.stdout + r.stderr).strip()
                ok  = r.returncode == 0
                return {"ok": ok, "output": out[:800]}
            except subprocess.TimeoutExpired:
                return {"ok": False, "output": f"Timed out after {timeout}s"}
            except Exception as e:
                return {"ok": False, "output": str(e)}

        checks = {}

        # 1. Docker container status
        r = run("docker ps --filter name=lcai-worker --filter name=lightchain-worker --format '{{.Names}} | {{.Status}}'")
        checks["docker_status"] = {
            "label": "Worker container running",
            "ok": r["ok"] and "Up" in r["output"],
            "output": r["output"] or "(no container found)",
        }

        # 2. Worker logs (last 20 lines)
        r = run("docker logs lcai-worker --tail 20 2>&1 || docker logs lightchain-worker --tail 20 2>&1")
        checks["worker_logs"] = {
            "label": "Recent worker logs",
            "ok": r["ok"],
            "output": r["output"],
        }

        # 3. Redis
        r = run("redis-cli ping")
        checks["redis"] = {
            "label": "Redis running",
            "ok": "PONG" in r["output"].upper(),
            "output": r["output"],
        }

        # 4. Ollama API + llama3-8b alias
        r = run("curl -sf http://localhost:11434/api/tags")
        if r["ok"]:
            try:
                models = [m.get("name","?") for m in _json.loads(r["output"]).get("models", [])]
                ollama_out = "Models: " + ", ".join(models) if models else "No models found"
            except Exception:
                ollama_out = r["output"][:300]
        else:
            ollama_out = r["output"] or "Ollama not reachable"
        checks["ollama"] = {
            "label": "Ollama running + llama3-8b alias",
            "ok": r["ok"] and "llama3" in r["output"],
            "output": ollama_out,
        }

        # 5. GPU
        r = run("nvidia-smi --query-gpu=name,memory.used,memory.total,temperature.gpu --format=csv,noheader")
        checks["gpu"] = {
            "label": "GPU (nvidia-smi)",
            "ok": r["ok"],
            "output": r["output"],
        }

        # 6. Disk space
        r = run("df -h / | tail -1")
        checks["disk"] = {
            "label": "Disk space",
            "ok": r["ok"],
            "output": r["output"],
        }

        # 7. VPN
        r = run("mullvad status 2>/dev/null || echo 'mullvad not found'")
        checks["vpn"] = {
            "label": "VPN (Mullvad)",
            "ok": "Connected" in r["output"],
            "output": r["output"],
        }

        # 8. Docker stats (1-shot)
        r = run("docker stats lcai-worker --no-stream --format 'CPU: {{.CPUPerc}} | MEM: {{.MemUsage}}' 2>/dev/null || docker stats lightchain-worker --no-stream --format 'CPU: {{.CPUPerc}} | MEM: {{.MemUsage}}' 2>/dev/null", timeout=15)
        checks["docker_stats"] = {
            "label": "Container resource usage",
            "ok": r["ok"],
            "output": r["output"] or "(container not running)",
        }

        # 9. Lightchain RPC reachable
        r = run("curl -sf --max-time 5 https://rpc.mainnet.lightchain.ai", timeout=8)
        checks["rpc"] = {
            "label": "Lightchain RPC reachable",
            "ok": r["ok"],
            "output": "Reachable" if r["ok"] else "BLOCKED — check VPN (Cox/some ISPs block this)",
        }

        # 10. Subgraph API reachable
        r = run('curl -sf --max-time 6 -X POST https://workers-api.mainnet.lightchain.ai/graphql -H "Content-Type: application/json" -d \'{"query":"{ workers(first:1) { id } }"}\'', timeout=10)
        checks["subgraph"] = {
            "label": "Subgraph API reachable",
            "ok": r["ok"] and "data" in r["output"],
            "output": "Reachable" if (r["ok"] and "data" in r["output"]) else (r["output"][:200] or "No response"),
        }

        passed = sum(1 for c in checks.values() if c["ok"])
        total  = len(checks)
        self._send_json({
            "ok":      True,
            "passed":  passed,
            "total":   total,
            "checks":  checks,
            "summary": f"{passed}/{total} checks passed",
        })

    def do_POST(self):
        parsed = urlparse(self.path)
        path   = parsed.path.rstrip("/")

        if path == "/api/ask":
            self._handle_ask()
            return

        if path == "/api/compare":
            self._handle_compare_post()
            return

        self._send_error("Not found", 404)

    def _handle_compare_get(self, parsed):
        from urllib.parse import parse_qs
        if not compare_to_reference:
            self._send_error("Compare module not available", 500)
            return
        qs = parse_qs(parsed.query)
        addr = (qs.get("worker_address") or [""])[0].strip()
        try:
            self._send_json(compare_to_reference(addr or None))
        except Exception as e:
            self._send_json({"ok": False, "error": str(e), "issues": []}, 500)

    def _handle_compare_post(self):
        if not compare_to_reference:
            self._send_error("Compare module not available", 500)
            return
        body = self._read_body()
        addr = (body.get("worker_address") or "").strip() or None
        try:
            self._send_json(compare_to_reference(addr))
        except Exception as e:
            self._send_json({"ok": False, "error": str(e), "issues": []}, 500)

    def _handle_ask(self):
        body     = self._read_body()
        question = body.get("question", "").strip()

        if not question:
            self._send_error("question is required")
            return

        if len(question) > 2000:
            self._send_error("question too long (max 2000 chars)")
            return

        import uuid
        job_id = str(uuid.uuid4())[:12]
        with _jobs_lock:
            _jobs[job_id] = {"status": "pending", "ts": time.time()}

        def _run():
            try:
                answer = run_inference(question)
                with _jobs_lock:
                    _jobs[job_id] = {
                        "status": "done",
                        "ts":     time.time(),
                        "answer": answer,
                    }
                print(f"  [ask] done: {job_id} ({len(answer)} chars)")
            except Exception as e:
                print(f"  [ask] error: {e}")
                with _jobs_lock:
                    _jobs[job_id] = {
                        "status": "error",
                        "ts":     time.time(),
                        "error":  str(e),
                    }
            # Clean up old jobs (keep last 50)
            with _jobs_lock:
                if len(_jobs) > 50:
                    oldest = sorted(_jobs.items(), key=lambda x: x[1].get("ts", 0))
                    for k, _ in oldest[:-50]:
                        del _jobs[k]

        threading.Thread(target=_run, daemon=True).start()
        self._send_json({"ok": True, "jobId": job_id})


# ════════════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print(f"Node Builder backend starting on port {PORT}...")
    aivm = get_aivm_client()
    if aivm:
        print(f"  AI: Lightchain AIVM (wallet {aivm._account.address})")
    else:
        print("  AI: UNAVAILABLE — set LIGHTCHAIN_PRIVATE_KEY to enable Ask the Wizard")

    server = HTTPServer(("0.0.0.0", PORT), Handler)
    print(f"  Ready: http://localhost:{PORT}")
    print(f"  Compare: http://localhost:{PORT} → Health Checks → Compare with Reference Node")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
