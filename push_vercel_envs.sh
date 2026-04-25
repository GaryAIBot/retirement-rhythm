#!/usr/bin/env bash
set -euo pipefail
ENV_FILE="/home/ubuntu/.config/gary/vercel-secrets.env"
set -a
source "$ENV_FILE"
set +a
for name in OPENAI_API_KEY GOOGLE_API_KEY DATABASE_URL; do
  value="${!name:-}"
  if [[ -z "$value" ]]; then
    continue
  fi
  for env in production preview development; do
    printf "%s" "$value" | vercel env add "$name" "$env" --force
  done
done
