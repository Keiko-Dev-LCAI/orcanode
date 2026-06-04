#!/bin/bash
KEYSTORE_FILE=$(ls /home/keiko/lightchain-worker/keys/eth-keystore/ | head -1)

echo "Waiting for Ollama to be ready..."
for i in $(seq 1 60); do
  if curl -s http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
    echo "Ollama ready after ${i}s"; break
  fi
  sleep 1
done
sleep 3

docker rm -f lightchain-worker 2>/dev/null || true

docker run --name lightchain-worker \
  --network host \
  --add-host=host.docker.internal:host-gateway \
  -v /home/keiko/lightchain-worker/keys:/data \
  --user root \
  -e WORKER_KEYSTORE_PATH=/data/eth-keystore/$KEYSTORE_FILE \
  -e WORKER_KEYSTORE_PASSWORD=MyNodePass123 \
  -e ENCRYPTION_KEYSTORE_PATH=/data/worker-encryption.key \
  -e RPC_URL=https://rpc.mainnet.lightchain.ai \
  -e CHAIN_ID=9200 \
  -e WORKER_REGISTRY_ADDRESS=0x0000000000000000000000000000000000001002 \
  -e AI_CONFIG_ADDRESS=0x24D11533C354092ed6E18b964257819cE78Ce77D \
  -e JOB_REGISTRY_ADDRESS=0xfB15F90298e4CcD7106E76fFB5e520315cC42B0b \
  -e SUPPORTED_MODELS=llama3-8b \
  -e MODELS_MAP='{"f4a414fa51803433e9197f32cda96d5cb2ac8269c481eb0262fe2dd11f428848":"llama3-8b:latest"}' \
  -e OLLAMA_URL=http://127.0.0.1:11434 \
  -e BEACON_API_URL=https://beacon.mainnet.lightchain.ai \
  -e BLOB_MODE=beacon \
  -e SESSION_KEY_FILE=/data/session-keys.enc \
  -e WORKER_GATEWAY_URL=https://worker-gateway.mainnet.lightchain.ai \
  us-central1-docker.pkg.dev/lightchain/lightchain-mainnet-public-docker/worker:latest
