#!/bin/sh
# Starts sshd for one SFTP account. Inputs, all from files so nothing secret sits in the container's environment:
#   /config/passhash     the account's crypt(3) hash (written by ops/stack_sftp.py, mounted read-only)
#   /config/hostkeys/    the host key, created on first start and kept in the person's stack folder (the fingerprint does not change)
set -eu
[ -s /config/passhash ] || { echo "no /config/passhash: run ops/stack_sftp.py passwd" >&2; exit 1; }
mkdir -p /config/hostkeys /run/sshd && chmod 755 /run/sshd
[ -f /config/hostkeys/ssh_host_ed25519_key ] || ssh-keygen -q -t ed25519 -N "" -f /config/hostkeys/ssh_host_ed25519_key
chmod 600 /config/hostkeys/ssh_host_ed25519_key
# The account (made at build) is uid 0 on purpose: the bot (root in its container) made most of the files, and a backup needs to read and replace them. What it can
# reach is only what the compose file mounts under /srv/view (the chroot), and what it can do is only SFTP.
{ grep -v '^persona:' /etc/shadow.template; printf 'persona:%s:19000:0:99999:7:::\n' "$(cat /config/passhash)"; } > /run/shadow
chown root:shadow /run/shadow && chmod 640 /run/shadow
exec /usr/sbin/sshd -D -e
