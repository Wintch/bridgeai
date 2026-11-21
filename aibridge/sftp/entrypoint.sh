#!/bin/sh
# Starts sshd for one SFTP account. Inputs, all from files so nothing secret sits in the container's environment:
#   /config/username     the account's name, random, written by ops/stack_sftp.py
#   /config/passhash     the account's crypt(3) hash (same tool; mounted read-only)
#   /config/hostkeys/    the host key, created on first start and kept in the person's stack folder (the fingerprint does not change)
set -eu
[ -s /config/passhash ] && [ -s /config/username ] || { echo "no /config/username or /config/passhash: run ops/stack_sftp.py passwd" >&2; exit 1; }
user="$(cat /config/username)"
printf '%s' "$user" | grep -qE '^[a-z][a-z0-9]{3,15}$' || { echo "bad username" >&2; exit 1; }
# The account is uid 0 on purpose: the bot (root in its container) made most of the files, and a backup needs to read and replace them. What it can
# reach is only what the compose file mounts under /srv/view (the chroot), and what it can do is only SFTP.
{ cat /etc/passwd.template; printf '%s:x:0:0::/:/usr/sbin/nologin\n' "$user"; } > /run/passwd
{ cat /etc/shadow.template; printf '%s:%s:19000:0:99999:7:::\n' "$user" "$(cat /config/passhash)"; } > /run/shadow
chown root:shadow /run/shadow && chmod 640 /run/shadow && chmod 644 /run/passwd
mkdir -p /config/hostkeys /run/sshd && chmod 755 /run/sshd
[ -f /config/hostkeys/ssh_host_ed25519_key ] || ssh-keygen -q -t ed25519 -N "" -f /config/hostkeys/ssh_host_ed25519_key
chmod 600 /config/hostkeys/ssh_host_ed25519_key
sed "s/__USER__/$user/g" /etc/ssh/sshd_config.template > /run/sshd_config
exec /usr/sbin/sshd -D -e -f /run/sshd_config
