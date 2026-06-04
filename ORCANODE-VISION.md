# OrcaNode — Project Vision & Notes
**Started: 2026-05-25 (session 27)**
**Status: v1 built — AIVM backend + hosting pending**

---

## The Idea

"Node in a Day" — a guided web wizard that takes anyone from zero to running a Lightchain AI worker node, with no developer background required.

Every command is copy-paste ready. Every common mistake is called out before you hit it. An AI assistant (powered by Lightchain AIVM — the very network you're setting up) answers your questions in plain English. Built from real experience running a node on Lightchain mainnet.

---

## Why This Exists

When Keiko set up her node, there was no guide like this. The official docs are technical and incomplete. The gotchas that trip people up — the bare model alias, the MODELS_MAP trap, the VPN requirement, the slash risk if you deregister — none of that is documented anywhere. She learned it all the hard way, across weeks of sessions.

Now that knowledge lives in OrcaNode.

As of launch day, there are only 6 active community nodes on Lightchain. The barrier to entry is too high. OrcaNode fixes that.

---

## Strategic Value

- **For the network:** More community nodes = more decentralization = more legitimate
- **For Keiko:** Every AI question in the wizard = AIVM inference job through her node = LCAI earned
- **For governance:** More node operators Keiko helped set up = more community goodwill = more governance support
- **For delegation:** When staking delegation launches, operators she helped may delegate tokens to her node for routing priority

---

## What's Built (v1 — session 27)

File: `~/Desktop/orcanode/index.html`
Assets: `orca.gif`, `orca-hero.png`, `orca-icon.png`

### 13-step wizard covering:
0. Welcome & gate check (do you have 50,001+ LCAI? compatible hardware?)
1. Hardware requirements (spec table, Keiko's setup as reference)
2. Operating system (Ubuntu recommended)
3. Prerequisites (NVIDIA drivers, Docker, Foundry/cast, Redis, VPN check)
4. Generate worker key (separate from funder — critical)
5. Resolve contract addresses on-chain
6. Install Ollama & pull models
7. Pull worker Docker image
8. Import key & generate ECDH encryption key
9. Fund worker wallet
10. Register on-chain
11. Run the worker (full Docker command + 6 healthy startup lines)
12. Health checks (all 10 commands)
13. Resources & links (all Lightchain URLs, contract addresses)

### Keiko's operator wisdom baked in:
- UPS recommendation (power outage = slash risk)
- Phone hotspot tip (ISP outage backup)
- ISP/VPN gate check (Cox blocks Lightchain RPC)
- The bare alias step (`ollama cp llama3:8b llama3-8b`) — most common new operator mistake
- MODELS_MAP must NOT be set (community confirmed)
- SUPPORTED_MODELS uses dash not colon
- Don't deregister to escape problems — ~7,500 LCAI slash penalty
- WebSocket EOF every ~1 hour is NORMAL auth token refresh
- `worker_ollama_up=0` is COSMETIC — not a real error
- `scheduler: batch release succeeded` = payouts processing = good sign
- What the 6 healthy startup lines look like

### Design:
- Dark navy theme (#080c18) with cyan (#00d4ff) accents
- Orca brand: orca-hero.png on welcome, orca.gif in chat panel
- Fixed sidebar with all 13 steps (progress indicator)
- Progress bar at top
- Code blocks with one-click copy buttons
- Warning (red), tip (cyan), success (green) callouts
- "Ask the Wizard" pill button — chat panel powered by AIVM

---

## What's Pending (session 28)

### 1. AIVM Assistant Backend
Same pattern as Smart Contract Explainer:
- dApp wallet pays for inference jobs
- System prompt = all correct configs + known gotchas + health check info from briefing files
- User types question → goes to AIVM → Keiko's node earns LCAI → answer returned

### 2. GitHub Pages Hosting
- Create repo: `Keiko-Dev-LCAI/orcanode`
- Push `index.html` + assets
- Enable GitHub Pages (like OrcaLearn)
- Free, always on, no server needed, auto-deploys on push

### 3. Domain (optional)
- `orcanode.ai` — clean, on-brand
- Point via Cloudflare DNS A records to GitHub Pages IPs (same as OrcaLearn)

### 4. Changelog system
- Visible "Last updated" date already in header
- Add a changelog section so people can see what's new
- Update when team drops new staking info, new whitelisted models, config changes

---

## Content Update Protocol

When the Lightchain team puts out new information:
1. Upload the announcement to Claude
2. Claude identifies what sections of OrcaNode need updating
3. Edit `index.html` and push to GitHub Pages
4. Update the "Last updated" date in the header

The wizard stays current in a way that static documentation never can. That's the competitive advantage over the official docs.

---

## Key URLs (for future reference)

- Official setup guide: https://workers.lightchain.ai/run-node
- Worker explorer: https://workers.lightchain.ai
- Subgraph API: https://workers-api.mainnet.lightchain.ai/graphql
- Worker toolkit: https://github.com/lightchain-protocol/lightchain-worker-toolkit
- Smart contracts: https://github.com/lightchain-protocol/lcai-smart-contract
- Discord support: https://discord.gg/lightchain

---

## Key Operator Configs (verified working on mainnet)

```
SUPPORTED_MODELS=llama3-8b      ← dash, not colon
# NO MODELS_MAP                 ← do not set this variable
OLLAMA_URL=http://host.docker.internal:11434
CHAIN_ID=9200
RPC_URL=https://rpc.mainnet.lightchain.ai
BEACON_API_URL=https://beacon.mainnet.lightchain.ai
WORKER_REGISTRY_ADDRESS=0x0000000000000000000000000000000000001002
WORKER_GATEWAY_URL=https://worker-gateway.mainnet.lightchain.ai
```

Ollama bare alias (CRITICAL):
```
ollama cp llama3:8b llama3-8b
```

6 healthy startup lines to look for in logs:
```
worker registration validated — on-chain key matches local key
blob mode: eip-4844 (beacon)
authenticated with worker-gateway
worker service initialized (gateway mode)
worker sidecar running (gateway mode)
websocket connected to gateway
```
