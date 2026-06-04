# Lightchain Protocol GitHub Report
**Date:** May 23, 2026
**Monitor run:** Automated daily scan — lightchain-protocol org (all 8 repos)

---

## 🔥 Top Findings (most important first)

- **⚠️ ZERO GitHub activity in the last 24 hours** across all 8 repos. The most recent commit to any repo is ~32 days old (lcai-chat-v2, April 21, 2026). This is a meaningful signal — the org has been quiet for over a month.
- **LightDEX is NOT live.** No swap contracts, DEX router/pool contracts, or LightDEX frontend code detected in any repo. The mainnet itself has not launched, which means LightDEX cannot go live yet. OrcaScreener development should stay in planning mode.
- **Mainnet remains delayed.** Originally scheduled July 31, 2025, pushed to Q4 2025, then H2 2026. As of April 2026 reporting, no confirmed mainnet date has been published. A May 7, 2026 date circulated in one source — no GitHub evidence confirms it was met.
- **Memecoin Launchpad is NOT live.** No launchpad contracts or frontend code found; all references are marketing/press releases.
- **Smart contracts are on testnet v2 only.** `lcai-smart-contract` repo is tagged `ready-to-audit` and has a comprehensive suite of Solidity contracts (AIVM inference, PoI, DAO governance), but all deployments target `lcai_testnet_v2` — no mainnet deployment scripts or addresses found.

---

## Repository Activity (last 24h)

### ❌ No repos had any activity in the last 24 hours.

The table below summarizes the full org:

| Repo | Last Updated | Language | PRs Open | Notes |
|------|-------------|----------|----------|-------|
| lcai-chat-v2 | Apr 21, 2026 | TypeScript | 0 | Most recently updated repo |
| bridge-ui | Apr 17, 2026 | TypeScript | 0 | Apache-2.0 license |
| LCAI-dao-frontend | Apr 16, 2026 | TypeScript | **2** | DAO governance UI; Next.js + OpenZeppelin |
| lcai-dev-portal | Mar 3, 2026 | TypeScript | **1** | Developer documentation portal |
| lcai-smart-contract | Jan 28, 2026 | Solidity | 0 | 128 commits; tagged `ready-to-audit` |
| chat-api-service-stress-tester | Oct 22, 2025 | TypeScript | 0 | k6 performance test suite |
| chain-node | Aug 29, 2025 | Shell | 0 | Node setup scripts |
| lcai-ide | Jul 21, 2025 | TypeScript | 0 | Apache-2.0 license |

**Total repos:** 8 (not 9 — previous reports may have been counting a now-removed or private repo)

### LCAI-dao-frontend — 2 Open PRs (last activity Apr 16, 2026)
The only repo with open pull requests. PR content is not publicly visible without authentication but their presence suggests some DAO frontend work is pending merge. No new activity in 37 days.

### lcai-dev-portal — 1 Open PR (last activity Mar 3, 2026)
One unmerged PR sitting open for ~81 days. Likely documentation or portal update.

### lcai-smart-contract — Detailed Findings
This is the most architecturally significant repo for OrcaScreener/LightDEX monitoring:
- **128 total commits** as of last update (Jan 28, 2026)
- Tagged `ready-to-audit` and `dao`
- **No DEX/swap contracts found** — the contract suite covers AIVM inference, PoI attestation, model registries, node staking, DAO governance, chat payments/subscriptions
- Notable contracts: `AIVMInferenceV2.sol`, `AIVMModelRegistry.sol`, `NodeOnboarding.sol`, `NodeStaking.sol`, `LCAIGovernor.sol`, `LCAIChatSubscription.sol`
- Deployment target: `lcai_testnet_v2` (confirmed via Makefile and deployment scripts)
- **Roadmap items still marked ☐ (not started):** BLS attestation verification on-chain, TEE quote binding, batch merkle roots, spot-check VRF, validator reward settlement, and more
- CertiK audit (July 2025) identified **23 unresolved issues** (0 critical, 4 major, 4 medium); status of fixes not confirmed in public repos

---

## 🚀 LightDEX Status

**Status: NOT LIVE — No evidence of imminent launch**

- No LightDEX contracts (router, factory, pool, or AMM contracts) exist in any public repo
- No LightDEX frontend code in `bridge-ui` or other repos
- Press releases from March 2025 announced LightDEX "launching next week" — this did not materialize on schedule
- LightDEX is architecturally dependent on the Lightchain mainnet, which has not launched
- Mainnet history: scheduled Jul 31, 2025 → delayed to Q4 2025 (CertiK audit issues) → delayed to H2 2026 → status as of May 2026 unclear; no GitHub evidence of mainnet launch
- **For OrcaScreener:** The blocking dependency is mainnet launch. Watch `lcai-smart-contract` for any new commits mentioning `dex`, `swap`, `router`, `pool`, `liquidity`, or `amm` — none exist today.

---

## 🪙 Memecoin Launchpad Status

**Status: NOT LIVE — Marketing stage only**

- No launchpad contracts or frontend in any public repo
- All references are press releases (Bitcoin.com, Bitget) describing the launchpad as "coming soon"
- Dependent on mainnet launch like all other ecosystem products
- No code, no contracts, no deployment artifacts

---

## 📡 API / Contract Intel

**LCAI ERC-20 token (Ethereum mainnet):**
- Contract: `0x9cA8530CA349c966Fe9ef903Df17a75B8A778927`
- Trading live on Uniswap V3 (LCAI/WETH pair, ~$268–273K/day volume as of mid-April 2026)
- Maximum supply: 10 billion tokens
- Note: This is a pre-mainnet ERC-20 bridge token, NOT the native Lightchain mainnet token

**Testnet v2 contract addresses:**
- Deployment artifacts live in `lcai-smart-contract/data/deployments/` — directory exists but files are not readable without authentication
- Deployment scripts write addresses to: `lcai-testnet-v2/genesis/genesis_v2.json`, `lcai-testnet-v2/network/rpc/config/consensus.yaml`
- No mainnet contract addresses published anywhere in public repos

**AIVM inference endpoints:**
- `AIVMInferenceV2.sol` implements `requestInferenceV2` → `commitInference` → `revealInference` flow (on testnet)
- Off-chain consensus API (task submission, PoI orchestration) exists but is in a private/unreleased repo — not present in the public org
- No REST API endpoint URLs found in any public code

**Governance parameters (from `LCAIGovernor.sol`):**
- Voting delay: 7,200 blocks
- Voting period: 100,800 blocks
- Proposal threshold: 140,000 LCAI
- Quorum: 3% (governance can adjust to 3–15%)

---

## ⚠️ Context & Risk Notes

1. **Development pace concern:** No commits to any repo in 32+ days is notable for a project claiming imminent mainnet launch. Either development is happening in private repos (likely for consensus layer) or momentum has slowed significantly.

2. **CertiK audit:** 23 unresolved issues were flagged in July 2025. No public evidence in GitHub that these were all resolved before the token began trading on Uniswap in January 2026.

3. **Community skepticism:** Per TheHolyCoins (Aug 2025) reporting, Reddit community (r/LightChainAI) showed significant frustration after the July 2025 delay, with some members calling the project a scam. Relevant context for risk assessment.

4. **Off-chain development:** The PoI consensus engine, AIVM execution layer, and Geth-based node software are explicitly described in the `lcai-smart-contract` README as separate off-chain repos — these are likely private and not visible in the public org.

---

## No Activity (no commits in last 24h)
All 8 repos: lcai-chat-v2, bridge-ui, LCAI-dao-frontend, lcai-dev-portal, lcai-smart-contract, chat-api-service-stress-tester, chain-node, lcai-ide

---

*Report generated by automated monitor. Sources: github.com/lightchain-protocol, news.bitcoin.com, coingabbar.com, theholycoins.com*
