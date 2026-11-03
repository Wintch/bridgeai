#!/bin/bash
# After a Hermes container was recreated with the hardening profile (guests/docker-compose.guest.yml), check that what the
# agent's tools need still works without the capabilities that were taken away. Run on VM105; ONLY on a test guest or a
# container you may poke (it runs short commands inside it and leaves nothing behind):
#   ops/hardening_smoke.sh guest-prueba
# Prints PASS/FAIL per check; exit 1 if any FAIL. The profile itself is checked by ops/container_hardening.py.
C="${1:?usage: hardening_smoke.sh <container>}"
docker inspect -f '{{.State.Running}}' "$C" 2>/dev/null | grep -q true || { echo "$C is not running" >&2; exit 2; }
fail=0
t() {  # t NAME COMMAND...: run COMMAND inside the container, PASS when it exits 0
  local name="$1"; shift
  if docker exec "$C" sh -c "$*" >/dev/null 2>&1; then echo "PASS  $name"; else echo "FAIL  $name"; fail=1; fi
}
t "gateway answers /health"            'curl -sf -m 5 http://localhost:8642/health'
t "outbound https (curl)"              'curl -sf -m 8 -o /dev/null https://example.com'
t "DNS lookup (dig)"                   'dig +short +time=3 +tries=1 example.com | grep -q .'
t "ping (the diagnostics skill)"       'ping -c1 -W3 1.1.1.1'
t "traceroute"                         'traceroute -m 2 -w 2 1.1.1.1'
t "tcpdump opens a capture (NET_RAW)"  'timeout 3 tcpdump -c1 -i any >/dev/null 2>&1; [ $? -ne 1 ]'
t "nmap SYN scan (NET_RAW)"            'nmap -sS -p 8642 127.0.0.1 | grep -q "8642"'
t "write in /workdir (bind mount)"     'f=/workdir/.hardening-smoke; echo x > $f && rm $f'
t "chown inside /workdir (CHOWN)"      'f=/workdir/.hardening-smoke2; touch $f && chown 1000:1000 $f; r=$?; rm -f $f; exit $r'
t "write in /root/.hermes"             'f=/root/.hermes/.hardening-smoke; echo x > $f && rm $f'
t "git"                                'git --version'
t "python3 and pip"                    'python3 -c "import sys" && python3 -m pip --version'
t "yt-dlp"                             'yt-dlp --version'
t "ssh client"                         'ssh -V'
# Things the profile must now REFUSE:
t "mknod is refused (MKNOD dropped)"   '! mknod /tmp/.x c 1 3 2>/dev/null'
t "setuid file does not escalate"      'cp /usr/bin/id /tmp/.idcopy && chmod u+s /tmp/.idcopy; u=$(su nobody -s /bin/sh -c "/tmp/.idcopy -u" 2>/dev/null); rm -f /tmp/.idcopy; [ "$u" != "0" ]'
n=$(docker exec "$C" sh -c 'ls /proc | grep -c "^[0-9]"' 2>/dev/null)
echo "INFO  processes now: ${n:-?} (limit 1024)"
[ $fail -eq 0 ] && echo "all checks passed" || echo "SOME CHECKS FAILED: do not roll this profile out to the person stacks until each is understood"
exit $fail
