#!/usr/bin/env bash
# Save an API key into this project's .env without showing it on screen or in shell history.
#   scripts/set-key.sh FAL_KEY
#   scripts/set-key.sh ODYSSEY_API_KEY
#   scripts/set-key.sh ANTHROPIC_API_KEY
# Replaces any earlier value for the same name. The server reads .env when it starts.
set -euo pipefail

name="${1:-}"
case "$name" in
  FAL_KEY|ODYSSEY_API_KEY|ANTHROPIC_API_KEY) ;;
  *) echo "usage: scripts/set-key.sh FAL_KEY|ODYSSEY_API_KEY|ANTHROPIC_API_KEY" >&2; exit 2 ;;
esac

cd "$(dirname "$0")/.."
printf 'Paste your %s (nothing will show), then press Enter: ' "$name"
IFS= read -rs value
echo
value="$(printf '%s' "$value" | tr -d '[:space:]')"
if [ -z "$value" ]; then
  echo "Nothing was pasted. .env is unchanged." >&2
  exit 1
fi

umask 077
touch .env
grep -v "^${name}=" .env > .env.new || true
printf '%s=%s\n' "$name" "$value" >> .env.new
mv .env.new .env
chmod 600 .env

colons="$(printf '%s' "$value" | tr -cd ':' | wc -c | tr -d ' ')"
echo "Saved $name: ${#value} characters."
if [ "$name" = "FAL_KEY" ] && [ "$colons" != "1" ]; then
  echo "Warning: a fal key normally looks like <id>:<secret> with exactly one colon. This one has $colons." >&2
fi
echo "Restart the server (Ctrl+C, then run it again) so it picks up the new key."
