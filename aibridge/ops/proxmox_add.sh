#!/bin/bash
# Add or update one Proxmox VE host for `gateway proxmox` in a stack's Hermes .env (2026-10-31). Run it on the operator's
# own computer:  AIBRIDGE_HOST=aibridge@<VM105> ops/proxmox_add.sh [stack]   (stack: hernik, the default, or a stack name)
#
# It asks for the name (the Zabbix group suffix: pve1 for bridgeai/pve1), the URL, the token id and, hidden, the token
# secret; reads the certificate fingerprint the host presents and asks you to compare it with the node's own
#   openssl x509 -noout -fingerprint -sha256 -in /etc/pve/local/pveproxy-ssl.pem   (or pve-ssl.pem when that is missing)
# The secret travels on stdin only: never in argv, a file or the transcript. The .env keeps its other lines and mode 600.
# An empty secret keeps the token already stored for that entry (to name or re-pin a host without retyping it).
# An URL equal to the stack's unsuffixed PROXMOX_URL updates that entry and names it (PROXMOX_NAME); any other is added
# to PROXMOX_HOSTS with PROXMOX_<NAME>_URL|_TOKEN|_FINGERPRINT. When the stack is awake, its live copy is written too
# (start_hermes.sh flushes the live .env over the persisted one at the next stop).
set -euo pipefail
HOST=${AIBRIDGE_HOST:?set AIBRIDGE_HOST=user@host}
STACK=${1:-hernik}
if [ "$STACK" = hernik ]; then PERSIST=aibridge/hermes-config; CT=aibridge-hermes-agent
else PERSIST=aibridge/stacks/$STACK/persist; CT=stack-$STACK-hermes; fi

read -rp "nombre (= grupo de Zabbix sin 'bridgeai/', ej. pve1): " N
[[ "$N" =~ ^[A-Za-z0-9._-]+$ ]] || { echo "nombre inválido" >&2; exit 1; }
read -rp "URL (https://IP:8006): " U
[[ "$U" =~ ^https://[A-Za-z0-9.-]+(:[0-9]+)?/?$ ]] || { echo "URL inválida" >&2; exit 1; }
U=${U%/}
read -rp "token id (ej. hermes@pve!hermes): " TID
[[ "$TID" =~ ^[A-Za-z0-9._-]+@[A-Za-z0-9._-]+![A-Za-z0-9._-]+$ ]] || { echo "token id inválido" >&2; exit 1; }
read -rsp "secreto del token (no se muestra; vacío = conservar el que ya está guardado para esa URL): " TS; echo
HP=${U#https://}; [[ "$HP" == *:* ]] || HP=$HP:8006
F=$(openssl s_client -connect "$HP" </dev/null 2>/dev/null | openssl x509 -noout -fingerprint -sha256 | cut -d= -f2)
[ -n "$F" ] || { echo "no pude leer el certificado de $HP" >&2; exit 1; }
echo "huella que presenta $HP:"; echo "  $F"
read -rp "¿es la misma que muestra el nodo? (s/n) " OK
[ "$OK" = s ] || { echo "cancelado: nada guardado" >&2; exit 1; }

PY=$(base64 -w0 <<'EOF'
import os, re, sys
n, u, tok, fp = [x.strip() for x in sys.stdin.read().split("\n")[:4]]
p = os.environ["P"]
lines = open(p).read().splitlines() if os.path.exists(p) else []
get = lambda k: next((l.split("=", 1)[1] for l in lines if l.startswith(k + "=")), "")
if get("PROXMOX_URL").rstrip("/") == u:
    pre, extra = "PROXMOX_", {"PROXMOX_NAME": n}
else:
    pre = "PROXMOX_" + re.sub(r"[^A-Z0-9]", "_", n.upper()) + "_"
    names = [x.strip() for x in get("PROXMOX_HOSTS").split(",") if x.strip()]
    extra = {"PROXMOX_HOSTS": ",".join(names + ([n] if n not in names else []))}
if tok.endswith("="):                                    # empty secret: keep the stored one (same token id only)
    old = get(pre + "TOKEN")
    if not old or old.rsplit("=", 1)[0] != tok[:-1]:
        sys.exit(f"no hay un token {tok[:-1]} guardado para {n}: nada cambiado")
    tok = old
new = dict(extra, **{pre + "URL": u, pre + "TOKEN": tok, pre + "FINGERPRINT": fp})
out = [l for l in lines if l.split("=", 1)[0] not in new] + [f"{k}={v}" for k, v in new.items()]
with open(p + ".n", "w") as f:
    f.write("\n".join(out) + "\n")
os.chmod(p + ".n", 0o600)
os.replace(p + ".n", p)
print(f"guardado en {p}: {n} ({pre}*)")
EOF
)
printf '%s\n%s\n%s\n%s\n' "$N" "$U" "$TID=$TS" "$F" | ssh "$HOST" "V=\$(cat)
printf '%s\n' \"\$V\" | docker run --rm -i -e P=/p/.env --entrypoint python3 -v ~/$PERSIST:/p aibridge-hermes-agent:latest -c \"import base64;exec(base64.b64decode('$PY'))\"
if [ \"\$(docker inspect -f '{{.State.Running}}' $CT 2>/dev/null)\" = true ]; then
  printf '%s\n' \"\$V\" | docker exec -i -e P=/root/.hermes/.env $CT python3 -c \"import base64;exec(base64.b64decode('$PY'))\"
fi"
echo "listo. Probalo en el chat: «chequeá proxmox», o en el stack: gateway proxmox --host $N"
