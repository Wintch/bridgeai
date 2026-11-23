#!/bin/sh
# install.sh: let a person's own bridgeai Hermes audit this server, read-only (the `sysadmin` pack, SYSADMIN_PLAN.md).
#
# Run it as root, after reading it. It is short on purpose. It does exactly this:
#   - creates the system user `hostcare`: no password; its login shell (/bin/sh) exists only because sshd runs the forced
#     command through it. The only way in is one SSH key that runs one forced command (`restrict`, no shell, no forwarding);
#   - makes its home /var/lib/hostcare owned by root (group hostcare, mode 0750), so the account cannot rename or replace
#     anything in it; the only places it may write are ~hostcare/.local/state/ (its own log), owned by it, mode 0700;
#   - copies hostcare_mcp.py and audit_root.py, owned by root, to /usr/local/lib/hostcare/;
#   - writes /etc/hostcare/hostcare.json (only this machine's name);
#   - allows `hostcare` to run audit_root.py as root, with no arguments, and nothing else (/etc/sudoers.d/hostcare);
#   - adds ONE key to ~hostcare/.ssh/authorized_keys (root-owned file in a root-owned directory). That key can only start
#     hostcare in audit mode, only from the address given with --from, with no shell, no port forwarding and no agent
#     forwarding.
# It changes nothing else: not sshd_config, not the firewall, no other user, no package.
#
#   sh install.sh --key 'ssh-ed25519 AAAA… bridgeai-sysadmin-NAME' [--from ADDRESS[,ADDRESS]] [--name NAME]
#   sh install.sh --uninstall          removes every file above and the user. The copy of this script in
#                                      /usr/local/lib/hostcare/ is removed too; it stays only when the user could not be
#                                      removed yet (a process of it was still running), so that you can run it again.
#
# Running it again with another key ROTATES: the hostcare key lines written by an earlier run are replaced, any other
# line of that file is left alone. Running it again also REPAIRS an install made by an earlier version of this script
# (which left the home owned by hostcare): ownership and modes are set again and the script says so.
# The script refuses (exit 1) when .ssh, authorized_keys or another path it writes as root is a symlink: nothing is
# written through it.
# To cut access without uninstalling: delete the key's line in /var/lib/hostcare/.ssh/authorized_keys.
set -eu

LIB=/usr/local/lib/hostcare
ETC=/etc/hostcare
HC_HOME=/var/lib/hostcare
HC_USER=hostcare
SUDOERS=/etc/sudoers.d/hostcare
HERE=$(cd "$(dirname "$0")" && pwd)

NL='
'
CR=$(printf '\r')

die() { echo "install.sh: $*" >&2; exit 1; }
# one_line VALUE: fails when it holds a line break (grep checks line by line, so a second line would slip through)
one_line() { case $1 in *"$NL"* | *"$CR"*) return 1 ;; esac; return 0; }
note() { echo "  - $*"; }
plural_lines() { if [ "$1" = 1 ]; then echo "1 other line"; else echo "$1 other lines"; fi; }

KEY="" FROM="" NAME="" UNINSTALL=0
while [ $# -gt 0 ]; do
    case "$1" in
        --key) [ $# -ge 2 ] || die "--key needs a value"; KEY=$2; shift 2 ;;
        --from) [ $# -ge 2 ] || die "--from needs a value"; FROM=$2; shift 2 ;;
        --name) [ $# -ge 2 ] || die "--name needs a value"; NAME=$2; shift 2 ;;
        --uninstall) UNINSTALL=1; shift ;;
        *) die "unknown argument: $1 (see the top of this file)" ;;
    esac
done

[ "$(id -u)" = 0 ] || die "run it as root (sudo -i, then the same command)."

if [ "$UNINSTALL" = 1 ]; then
    echo "Removing hostcare (bridgeai sysadmin) from this server:"
    rm -f "$SUDOERS" && note "sudo rule removed"
    if [ -L "$HC_HOME/.ssh" ] || [ -L "$HC_HOME" ]; then
        echo "  ! $HC_HOME or its .ssh is a symlink: not following it. Look at it by hand." >&2
    else
        rm -f "$HC_HOME/.ssh/authorized_keys" && note "key removed: Hermes cannot log in any more"
    fi
    LEFT=0
    if id "$HC_USER" >/dev/null 2>&1; then
        # the systemd user manager of the last login can outlive it for a few seconds and block userdel
        loginctl terminate-user "$HC_USER" 2>/dev/null || true
        pkill -u "$HC_USER" 2>/dev/null || true
        i=0
        while ! userdel "$HC_USER" 2>/dev/null; do
            i=$((i + 1))
            if [ "$i" -ge 15 ]; then break; fi
            sleep 1
            pkill -KILL -u "$HC_USER" 2>/dev/null || true
        done
        if id "$HC_USER" >/dev/null 2>&1; then
            echo "  ! user $HC_USER is still there (a process of it is running): run --uninstall again in a minute." >&2
            LEFT=1
        else
            note "user $HC_USER removed"
        fi
    fi
    rm -rf "$ETC" "$HC_HOME"
    if [ "$LEFT" = 0 ]; then
        rm -rf "$LIB"
    else
        rm -f "$LIB/hostcare_mcp.py" "$LIB/audit_root.py"   # install.sh stays: the retry below needs it
    fi
    note "files removed"
    if [ "$LEFT" = 0 ]; then
        echo "Done. Nothing of it is left. In Hermes: «gateway sysadmin forget NAME» deletes the key on that side."
    else
        echo "Almost: only the empty user $HC_USER is left, with no key. Run again: sh $LIB/install.sh --uninstall" >&2
        exit 1
    fi
    exit 0
fi

# ---- checks before touching anything
one_line "$KEY" && printf '%s' "$KEY" | grep -Eq '^ssh-ed25519 [A-Za-z0-9+/]{68}(=|==)?( [A-Za-z0-9@._-]{1,64})?$' \
    || die "--key must be one ssh-ed25519 public key on one line, as Hermes printed it."
if [ -n "$FROM" ]; then
    one_line "$FROM" && printf '%s' "$FROM" | grep -Eq '^[0-9A-Fa-f:.,/]{2,200}$' || die "--from must be addresses (or CIDR), comma separated, on one line."
fi
[ -n "$NAME" ] || NAME=$(hostname)
one_line "$NAME" && printf '%s' "$NAME" | grep -Eq '^[A-Za-z0-9][A-Za-z0-9._-]{0,62}$' || die "--name: letters, digits, dot, dash."
for f in hostcare_mcp.py audit_root.py; do
    [ -f "$HERE/$f" ] || die "$f is missing next to install.sh."
done
PY=$(command -v python3 || true)
[ -n "$PY" ] || die "python3 is needed (apt install python3)."
# the path goes inside the forced command of the key: an absolute path of plain characters only (no space, quote or backslash)
one_line "$PY" && printf '%s' "$PY" | grep -Eq '^/[A-Za-z0-9._/+-]+$' || die "python3 resolves to '$PY': it must be an absolute path of letters, digits and . _ / + - only."
"$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)' || die "python3 is older than 3.8."
command -v sshd >/dev/null 2>&1 || [ -x /usr/sbin/sshd ] || die "no OpenSSH server on this machine."

echo "Installing hostcare (bridgeai sysadmin, read-only) as '$NAME':"

# ---- user: system account, password field '*' (no password can match; not '!' so sshd without PAM still accepts the key).
# `useradd --create-home` also copies /etc/skel into the home (.bashrc, .profile...): harmless, the forced command runs
# through `sh -c`, and the files cannot be renamed or removed once the home is root-owned.
CREATED=0
if id "$HC_USER" >/dev/null 2>&1; then
    # an account that already has this name must be ours (home /var/lib/hostcare): this script chowns the home and locks the password
    EXISTING_HOME=$(getent passwd "$HC_USER" 2>/dev/null | cut -d: -f6)
    [ -z "$EXISTING_HOME" ] || [ "$EXISTING_HOME" = "$HC_HOME" ] \
        || die "an account named $HC_USER already exists with another home ($EXISTING_HOME). It is not ours: nothing was changed. Remove or rename it first."
fi
if ! id "$HC_USER" >/dev/null 2>&1; then
    CREATED=1
    useradd --system --home-dir "$HC_HOME" --create-home --shell /bin/sh --comment "bridgeai sysadmin (read-only)" "$HC_USER"
    note "user $HC_USER created"
fi
usermod -p '*' "$HC_USER"

# ---- the home belongs to ROOT (group hostcare, 0750). If hostcare owned its home it could rename the root-owned .ssh away
# and plant its own authorized_keys (sshd accepts a file owned by the user), and every later root-run step of this script
# would follow paths inside a tree that hostcare controls. 0750 keeps sshd's StrictModes happy (not writable by group or
# others) and lets the account walk through it. The account writes only inside ~/.local/state (hostcare_mcp.py: its log).
refuse() { echo "install.sh: $1 is a symbolic link; refusing to follow it; nothing was written through it. Inspect it, remove it, run again." >&2; exit 1; }
[ ! -L "$HC_HOME" ] || refuse "$HC_HOME"
[ -d "$HC_HOME" ] || install -d -o root -g "$HC_USER" -m 0750 "$HC_HOME"
OWNER=$(stat -c %U "$HC_HOME" 2>/dev/null || echo root)
chown "root:$HC_USER" "$HC_HOME"
chmod 0750 "$HC_HOME"
if [ "$CREATED" = 0 ] && [ "$OWNER" != root ]; then
    note "repaired: $HC_HOME was owned by $OWNER (earlier version of this script); it is root-owned now"
    note "  look through $HC_HOME/.ssh/authorized_keys: every line that is not yours stays there"
fi
SSHDIR="$HC_HOME/.ssh"
AK="$SSHDIR/authorized_keys"
# the home is root-owned from here on, so these two cannot be swapped under us; the files below sit inside root-only directories
[ ! -L "$SSHDIR" ] || refuse "$SSHDIR"
[ ! -L "$HC_HOME/.local" ] || refuse "$HC_HOME/.local"
install -d -o root -g root -m 0755 "$SSHDIR"
install -d -o root -g "$HC_USER" -m 0750 "$HC_HOME/.local"
for p in "$HC_HOME/.local/state" "$AK" "$AK.new"; do
    [ ! -L "$p" ] || refuse "$p"
done
{ [ ! -e "$AK" ] || [ -f "$AK" ]; } || { echo "install.sh: $AK is not a regular file; nothing was written through it." >&2; exit 1; }
install -d -o "$HC_USER" -g "$HC_USER" -m 0700 "$HC_HOME/.local/state"

# ---- programs and config, owned by root so hostcare cannot change them
install -d -o root -g root -m 0755 "$LIB" "$ETC"
install -o root -g root -m 0755 "$HERE/hostcare_mcp.py" "$LIB/hostcare_mcp.py"
install -o root -g root -m 0755 "$HERE/audit_root.py" "$LIB/audit_root.py"
install -o root -g root -m 0755 "$HERE/install.sh" "$LIB/install.sh"   # kept for --uninstall
printf '{"host": "%s", "audit_helper": "%s/audit_root.py"}\n' "$NAME" "$LIB" > "$ETC/hostcare.json"
chmod 0644 "$ETC/hostcare.json"
note "programs in $LIB, config in $ETC"

# ---- sudo: exactly the helper, exactly no arguments ("" in sudoers means: no arguments allowed)
if command -v visudo >/dev/null 2>&1; then
    TMP=$(mktemp)
    printf '# bridgeai sysadmin: the read-only audit helper, no arguments. Remove with install.sh --uninstall.\n%s ALL=(root) NOPASSWD: %s/audit_root.py ""\n' "$HC_USER" "$LIB" > "$TMP"
    if visudo -cf "$TMP" >/dev/null; then
        install -o root -g root -m 0440 "$TMP" "$SUDOERS"
        note "sudo: $HC_USER may run only $LIB/audit_root.py, without arguments"
    else
        echo "  ! visudo rejected the rule; the root checks will say unknown." >&2
    fi
    rm -f "$TMP"
else
    note "sudo is not installed: the checks that need root (ssh, firewall, fail2ban, logins...) will say unknown."
    note "  To get them: apt install sudo, then run this same command again."
fi

# ---- the key: a root-owned file in a root-owned directory inside a root-owned home, so the hostcare account cannot add keys
# to itself. The new content is built in a fresh mktemp file in that root-only directory and moved over in one step.
OPTS="restrict"
[ -n "$FROM" ] && OPTS="$OPTS,from=\"$FROM\""
OPTS="$OPTS,command=\"$PY -I $LIB/hostcare_mcp.py --mode audit --config $ETC/hostcare.json\""
[ -e "$AK" ] || : > "$AK"
KEYBODY=$(printf '%s' "$KEY" | cut -d' ' -f2)
MARK="$LIB/hostcare_mcp.py --mode audit"   # inside the forced command of every key this script writes
BEFORE=$(grep -c '' "$AK" || true)   # counts an unterminated last line too (wc -l does not)
NEWAK=$(mktemp "$SSHDIR/.authorized_keys.XXXXXX")
trap 'rm -f "$NEWAK"' EXIT
# rotation: drop the lines an earlier run wrote (they carry our forced command) and any line with this same key; every
# other line of the file is somebody else's and stays
grep -v -F -e "$MARK" -e "$KEYBODY" "$AK" > "$NEWAK" || true
AFTER=$(grep -c '' "$NEWAK" || true)
OLDKEYS=$(grep -F -e "$MARK" "$AK" | grep -vcF -e "$KEYBODY" || true)   # our earlier lines that carried a DIFFERENT key
printf '%s %s\n' "$OPTS" "$KEY" >> "$NEWAK"
chown root:root "$NEWAK"
chmod 0644 "$NEWAK"
mv -f "$NEWAK" "$AK"
trap - EXIT
if [ "$OLDKEYS" -gt 0 ]; then
    note "replaced $OLDKEYS earlier hostcare key line(s) that held another key: that old key no longer works"
elif [ "$BEFORE" -gt "$AFTER" ]; then
    note "the key line of an earlier run was refreshed (same key, new options)"
fi
[ "$AFTER" -gt 0 ] && note "$(plural_lines "$AFTER") in $AK are not written by this script and were left alone: make sure you know them"
if [ -n "$FROM" ]; then note "key installed: audit mode only, only from $FROM"; else note "key installed: audit mode only, from ANY address (no --from)"; fi

# ---- does sshd let this user in?
SSHD=$(command -v sshd || echo /usr/sbin/sshd)
EFF=$("$SSHD" -T 2>/dev/null || true)
PORTS=$(printf '%s\n' "$EFF" | awk '$1=="port"{print $2}' | tr '\n' ' ')
ALLOWU=$(printf '%s\n' "$EFF" | awk '$1=="allowusers"{ $1=""; print }')
ALLOWG=$(printf '%s\n' "$EFF" | awk '$1=="allowgroups"{ $1=""; print }')
# sshd needs BOTH lists to pass when both are set. Patterns are shell-like (* and ?); a user@host pattern is matched on its user part.
# Never advise creating a new Allow* line: on a server that has only AllowGroups, a new AllowUsers line would lock everyone else out.
allowed_by() {   # allowed_by "PATTERNS" WORD...: success when any word matches any pattern
    pats=$1; shift
    set -f
    for p in $pats; do
        p=${p%%@*}
        for w in "$@"; do
            case $w in $p) set +f; return 0 ;; esac
        done
    done
    set +f
    return 1
}
if [ -n "$ALLOWU" ] && ! allowed_by "$ALLOWU" "$HC_USER"; then
    echo "  ! sshd's AllowUsers does not list '$HC_USER', so Hermes cannot log in yet." >&2
    echo "    Add '$HC_USER' to the AllowUsers line that is already in /etc/ssh/sshd_config (do not start a second line), 'sshd -t', reload ssh." >&2
fi
if [ -n "$ALLOWG" ]; then
    # shellcheck disable=SC2046
    if ! allowed_by "$ALLOWG" $(id -Gn "$HC_USER" 2>/dev/null); then
        echo "  ! sshd's AllowGroups does not cover any group of '$HC_USER', so Hermes cannot log in yet." >&2
        echo "    Put the user in a group that AllowGroups already lists (usermod -aG GROUP $HC_USER) rather than adding any AllowUsers line:" >&2
        echo "    with both set, sshd needs both to pass and every other user would be locked out." >&2
    fi
fi

echo
echo "Ready. SSH port(s): ${PORTS:-22}"
echo "This server's key fingerprints (Hermes shows one of them on the first check; they must match):"
for f in /etc/ssh/ssh_host_ed25519_key.pub /etc/ssh/ssh_host_ecdsa_key.pub /etc/ssh/ssh_host_rsa_key.pub; do
    [ -f "$f" ] && ssh-keygen -lf "$f" | awk '{print "    " $2 "  " $NF}'
done
echo
echo "Back in Hermes, say it is done (it runs «gateway sysadmin check $NAME»)."
echo "To remove everything later: sh $LIB/install.sh --uninstall"
