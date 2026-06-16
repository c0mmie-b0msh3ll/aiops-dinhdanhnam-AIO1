#!/usr/bin/env sh
# Flip the middleware to active. Compose reads this .env value on recreate.
printf '%s\n' 'EVIL_REGEX_ACTIVE=1' > .env
docker compose up -d --force-recreate api
echo "[$(date -u +%H:%M:%S)] WAF rule now active - try: curl --max-time 30 'http://localhost:8888/?q=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx='"
