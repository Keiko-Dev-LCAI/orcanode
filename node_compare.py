"""
Compare a local operator node profile against reference-profile.json.
Returns only differences and problems with fixes.
"""

import json
import os
import re
import subprocess
import time
from urllib import request as urlrequest
from urllib.error import URLError

_DIR = os.path.dirname(os.path.abspath(__file__))
REFERENCE_PATH = os.path.join(_DIR, "reference-profile.json")
GRAPHQL_URL = "https://workers-api.mainnet.lightchain.ai/graphql"


def _run(cmd, timeout=12):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        out = (r.stdout + r.stderr).strip()
        return {"ok": r.returncode == 0, "output": out}
    except subprocess.TimeoutExpired:
        return {"ok": False, "output": f"Timed out after {timeout}s"}
    except Exception as e:
        return {"ok": False, "output": str(e)}


def _load_reference():
    with open(REFERENCE_PATH, encoding="utf-8") as f:
        return json.load(f)


def _docker_container_name(ref):
    names = ref["docker"]["container_names"]
    r = _run(
        "docker ps -a --format '{{.Names}}' | grep -E '^(lightchain-worker|lcai-worker)$' | head -1"
    )
    if r["ok"] and r["output"]:
        return r["output"].splitlines()[0].strip()
    for n in names:
        chk = _run(f"docker ps -a --filter name=^{n}$ --format '{{{{.Names}}}}'")
        if chk["output"]:
            return chk["output"].splitlines()[0].strip()
    return None


def _docker_inspect_field(name, field):
    r = _run(f"docker inspect {name} --format '{field}' 2>/dev/null")
    return r["output"] if r["ok"] else ""


def _docker_env(name):
    r = _run(f"docker inspect {name} --format '{{{{json .Config.Env}}}}' 2>/dev/null")
    if not r["ok"] or not r["output"]:
        return {}
    try:
        items = json.loads(r["output"])
    except json.JSONDecodeError:
        return {}
    env = {}
    for item in items:
        if "=" in item:
            k, _, v = item.partition("=")
            env[k] = v
    return env


def _ollama_models():
    r = _run("curl -sf --max-time 6 http://127.0.0.1:11434/api/tags")
    if not r["ok"]:
        return []
    try:
        data = json.loads(r["output"])
        return [m.get("name", "") for m in data.get("models", [])]
    except json.JSONDecodeError:
        return []


def _worker_logs(name, lines=120):
    r = _run(f"docker logs {name} --tail {lines} 2>&1")
    return r["output"] if r["ok"] else ""


def _extract_address_from_logs(logs):
    m = re.search(r'"address"\s*:\s*"(0x[a-fA-F0-9]{40})"', logs)
    if m:
        return m.group(1)
    m = re.search(r"loaded signing key.*?(0x[a-fA-F0-9]{40})", logs)
    if m:
        return m.group(1)
    return None


def _fetch_on_chain(worker_address):
    if not worker_address or not re.fullmatch(r"0x[a-fA-F0-9]{40}", worker_address):
        return None
    q = (
        '{ worker(id: "%s") { status jobs_completed disputes_lost offense_count '
        'total_earned last_seen_at suspended_until } }'
    ) % worker_address
    body = json.dumps({"query": q}).encode()
    req = urlrequest.Request(
        GRAPHQL_URL,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlrequest.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
    except (URLError, TimeoutError, json.JSONDecodeError):
        return None
    worker = (data.get("data") or {}).get("worker")
    return worker


def _issue(issues, issue_id, severity, category, problem, fix):
    issues.append({
        "id": issue_id,
        "severity": severity,
        "category": category,
        "problem": problem,
        "fix": fix,
    })


def collect_operator_profile(worker_address=None):
    ref = _load_reference()
    profile = {
        "scanned_at": int(time.time()),
        "container": None,
        "container_running": False,
        "docker": {},
        "env": {},
        "ollama_models": _ollama_models(),
        "services": {},
        "logs_snippet": "",
        "worker_address": worker_address,
        "on_chain": None,
    }

    name = _docker_container_name(ref)
    profile["container"] = name
    if not name:
        return profile

    ps = _run(f"docker ps --filter name=^{name}$ --format '{{{{.Status}}}}'")
    profile["container_running"] = ps["ok"] and ps["output"].startswith("Up")

    profile["docker"] = {
        "network_mode": _docker_inspect_field(name, "{{.HostConfig.NetworkMode}}"),
        "restart_policy": _docker_inspect_field(name, "{{.HostConfig.RestartPolicy.Name}}"),
    }
    profile["env"] = _docker_env(name)
    logs = _worker_logs(name)
    profile["logs_snippet"] = logs[-4000:] if logs else ""

    if not profile["worker_address"]:
        profile["worker_address"] = _extract_address_from_logs(logs)

    profile["services"]["redis"] = "PONG" in _run("redis-cli ping").get("output", "").upper()
    vpn = _run("mullvad status 2>/dev/null")
    profile["services"]["vpn"] = "Connected" in vpn.get("output", "")
    profile["services"]["rpc"] = _run("curl -sf --max-time 5 https://rpc.mainnet.lightchain.ai").get("ok", False)
    gw = _run(
        "curl -s -o /dev/null -w '%{http_code}' --max-time 5 https://worker-gateway.mainnet.lightchain.ai/"
    )
    code = gw.get("output", "").strip() if gw.get("ok") else ""
    profile["services"]["gateway"] = code.isdigit() and int(code) < 500

    if profile["worker_address"]:
        profile["on_chain"] = _fetch_on_chain(profile["worker_address"])

    return profile


def compare_to_reference(worker_address=None):
    ref = _load_reference()
    op = collect_operator_profile(worker_address)
    issues = []

    name = op["container"]
    if not name:
        _issue(
            issues,
            "no_container",
            "error",
            "docker",
            "No worker container found (lightchain-worker or lcai-worker).",
            "Start the worker from Step 11, or run: docker ps -a\n"
            "If missing, re-run your docker run / start-lightchain-worker.sh script.",
        )
        return _result(ref, op, issues)

    if not op["container_running"]:
        _issue(
            issues,
            "container_stopped",
            "error",
            "docker",
            f"Container '{name}' exists but is not running.",
            f"docker start {name}\n"
            f"Then watch logs: docker logs -f {name}",
        )

    dref = ref["docker"]
    d = op["docker"]
    if d.get("network_mode") != dref["network_mode"]:
        _issue(
            issues,
            "network_mode",
            "error",
            "docker",
            f"Docker network mode is '{d.get('network_mode')}' — reference uses '{dref['network_mode']}'.",
            "Re-launch with --network host so the container can reach Ollama on localhost.",
        )

    if d.get("restart_policy") in ("no", ""):
        _issue(
            issues,
            "restart_policy",
            "warning",
            "docker",
            f"Restart policy is '{d.get('restart_policy') or 'no'}' — reference uses '{dref['restart_policy']}'.",
            "Add --restart always to docker run, or use a systemd service that restarts the container after reboot.",
        )

    env = op["env"]
    for key, expected in dref["env"].items():
        actual = env.get(key)
        if actual is None:
            _issue(
                issues,
                f"env_missing_{key}",
                "error",
                "config",
                f"Missing environment variable {key} (reference node sets it).",
                f"Add to your docker run / start script:\n  -e {key}={expected}",
            )
        elif actual.strip() != expected:
            _issue(
                issues,
                f"env_wrong_{key}",
                "error",
                "config",
                f"{key} is '{actual}' — reference uses '{expected}'.",
                f"Update your start script:\n  -e {key}={expected}",
            )

    for key in dref.get("env_required_keys", []):
        if key not in env:
            _issue(
                issues,
                f"env_required_{key}",
                "error",
                "config",
                f"Required variable {key} is not set in the container.",
                f"Add -e {key}=... to your docker run command (see Step 8–11 in the wizard).",
            )

    for key in dref.get("env_forbidden_keys", []):
        if key in env and env[key]:
            _issue(
                issues,
                f"env_forbidden_{key}",
                "warning",
                "config",
                f"{key} is set — reference node does not use this (can break routing).",
                f"Remove {key} from your docker environment. Use WORKER_KEYSTORE_PATH instead of PRIVATE_KEY.",
            )

    ollama_url = env.get("OLLAMA_URL", "")
    if ollama_url and not any(p in ollama_url for p in dref.get("ollama_url_patterns", [])):
        _issue(
            issues,
            "ollama_url",
            "warning",
            "config",
            f"OLLAMA_URL is '{ollama_url}' — may not reach Ollama from the container.",
            "Use OLLAMA_URL=http://127.0.0.1:11434 with --network host, "
            "or http://host.docker.internal:11434 with --add-host=host.docker.internal:host-gateway.",
        )

    pwd = env.get("WORKER_KEYSTORE_PASSWORD", "")
    unsafe = dref.get("keystore_password_unsafe_chars", [])
    if pwd and any(c in pwd for c in unsafe):
        _issue(
            issues,
            "keystore_password_chars",
            "warning",
            "config",
            "Keystore password contains special shell characters — this breaks many setups.",
            "Use a simple alphanumeric password when creating the keystore, or quote/escape carefully in your start script.",
        )

    models = op["ollama_models"]
    model_blob = " ".join(models).lower()
    if not any(s in model_blob for s in ref["ollama"]["required_model_substrings"]):
        _issue(
            issues,
            "ollama_alias",
            "error",
            "ollama",
            "Ollama does not have the llama3-8b alias (most common job failure).",
            "ollama pull llama3:8b\nollama cp llama3:8b llama3-8b\nollama list   # must show llama3-8b",
        )

    svc = ref["services"]
    osvc = op["services"]
    if svc.get("redis_required") and not osvc.get("redis"):
        _issue(
            issues,
            "redis_down",
            "error",
            "services",
            "Redis is not responding (worker needs it for the job queue).",
            "sudo systemctl start redis-server\nsudo systemctl enable redis-server\nredis-cli ping   # expect PONG",
        )
    if svc.get("vpn_required") and not osvc.get("vpn"):
        _issue(
            issues,
            "vpn_down",
            "error",
            "services",
            "Mullvad VPN is not connected — many ISPs block Lightchain RPC.",
            "mullvad connect\nmullvad status   # expect Connected",
        )
    if svc.get("rpc_required") and not osvc.get("rpc"):
        _issue(
            issues,
            "rpc_blocked",
            "error",
            "network",
            "Cannot reach https://rpc.mainnet.lightchain.ai from this machine.",
            "Connect Mullvad VPN first. Cox and some ISPs block this endpoint without VPN.",
        )
    if svc.get("gateway_required") and not osvc.get("gateway"):
        _issue(
            issues,
            "gateway_blocked",
            "warning",
            "network",
            "Cannot reach the worker gateway — heartbeats may fail.",
            "Check VPN and firewall. Test: curl -sf https://worker-gateway.mainnet.lightchain.ai/",
        )

    logs = op.get("logs_snippet", "").lower()
    if op["container_running"]:
        for pat in ref.get("log_patterns_required", []):
            if pat.lower() not in logs:
                _issue(
                    issues,
                    f"log_missing_{pat[:24]}",
                    "warning",
                    "logs",
                    f"Recent logs do not show '{pat}' — gateway connection may be down.",
                    f"docker logs -f {name}\n"
                    "Look for websocket/gateway errors. Restart after fixing VPN/RPC.",
                )

        if "deregistration failed" in logs or (
            "execution reverted" in logs and "deregister" in logs
        ):
            _issue(
                issues,
                "deregister_failed",
                "warning",
                "logs",
                "Logs show a failed deregister transaction.",
                "Do not keep retrying deregister if on-chain status is already deregistered — contact Lightchain Discord. "
                "This is a known stuck-state bug for some operators.",
            )

    oc = op.get("on_chain")
    addr = op.get("worker_address")
    if not addr:
        _issue(
            issues,
            "no_worker_address",
            "info",
            "on_chain",
            "Could not detect your worker wallet address (optional field helps on-chain checks).",
            "Paste your worker address in the compare box, or check docker logs for 'loaded signing key'.",
        )
    elif oc is None:
        _issue(
            issues,
            "on_chain_fetch_failed",
            "info",
            "on_chain",
            f"Could not load on-chain data for {addr[:10]}…{addr[-4:]}.",
            "Check internet/VPN and try again, or verify the address at lightnode.app",
        )
    elif oc:
        oref = ref["on_chain"]
        status = oc.get("status")
        jobs = int(oc.get("jobs_completed") or 0)
        offenses = int(oc.get("offense_count") or 0)
        disputes_lost = int(oc.get("disputes_lost") or 0)
        last_seen = int(oc.get("last_seen_at") or 0)
        age_h = (time.time() - last_seen) / 3600 if last_seen else 9999

        if status == "deregistered" and jobs > 0:
            _issue(
                issues,
                "stuck_deregistered_bug",
                "error",
                "on_chain",
                f"On-chain status is deregistered but you have {jobs} completed jobs — known stuck state.",
                "Do NOT retry deregister (it will revert). Ask in Lightchain Discord — team has a workaround in review. "
                "Your local worker may still run jobs while the chain/UI show the wrong status.",
            )
        elif status != oref["expected_status"]:
            _issue(
                issues,
                "on_chain_status",
                "error",
                "on_chain",
                f"On-chain status is '{status}' — reference active node shows '{oref['expected_status']}'.",
                "If you never registered successfully, complete Step 10 (register).\n"
                "If you deregistered intentionally, re-register requires a new stake transaction.",
            )

        if offenses > oref["max_offense_count"]:
            _issue(
                issues,
                "offenses",
                "error",
                "on_chain",
                f"offense_count is {offenses} — reference node has 0.",
                "Review slash history on lightnode.app. Three offenses can trigger 7-day suspension.",
            )

        if disputes_lost > oref["max_disputes_lost"]:
            _issue(
                issues,
                "disputes_lost",
                "warning",
                "on_chain",
                f"You have lost {disputes_lost} dispute(s) — reference node has 0.",
                "Check disputed jobs on your worker dashboard. Improve uptime and job completion consistency.",
            )

        if op["container_running"] and age_h > oref.get("fresh_last_seen_hours", 6):
            _issue(
                issues,
                "stale_heartbeat",
                "warning",
                "on_chain",
                f"Last on-chain activity was {age_h:.0f} hours ago — reference node is usually active within a few hours.",
                "Check gateway connection in logs, VPN, and WiFi. docker restart " + name,
            )

    return _result(ref, op, issues)


def _result(ref, op, issues):
    order = {"error": 0, "warning": 1, "info": 2}
    issues.sort(key=lambda x: (order.get(x["severity"], 9), x["category"]))
    return {
        "ok": True,
        "reference_label": ref.get("label"),
        "worker_address": op.get("worker_address"),
        "container": op.get("container"),
        "issue_count": len(issues),
        "issues": issues,
        "summary": (
            "No differences — your node matches the reference profile."
            if not issues
            else f"{len(issues)} difference(s) found vs reference node."
        ),
    }