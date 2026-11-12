#!/bin/bash
# Software inventory for the Zabbix agent (UserParameters vw.dpkg and vw.apt). Read-only: no root, no sudo, no network.
# Installed on a monitored host as /etc/zabbix/vw_inventory.sh and run by the Zabbix agent user.
#
#   vw_inventory.sh dpkg N M   shard N of M of the installed packages (installed or partly installed: second status character
#                              i, U, F, H, W or t, so held packages "hi" are included), one line per binary package:
#                                binary<TAB>version<TAB>source<TAB>source_version
#                              Shard of a package = (POSIX cksum CRC of the binary name) mod M, the value of
#                              `printf %s NAME | cksum`, computed here in one awk pass (no fork per package).
#                              First line:  #vw.dpkg shard=N of=M count=K     (K = packages in the shard before any cut)
#                              Over VW_MAX_BYTES (default 60000) the output is cut at a line boundary and the last line is
#                              #truncated. Without dpkg the output is the single line #nodpkg.
#                              If dpkg-query fails nothing is printed and the exit status is 1, so the Zabbix item turns
#                              unsupported instead of reporting an empty shard.
#   vw_inventory.sh apt        one compact JSON object (at most 2 KB): pending and security updates from the apt lists cache,
#                              reboot_required, age of the lists, running and newest installed kernel.
#                              Without apt: {"error":"no-apt"}.
#
# Test overrides (environment): VW_MAX_BYTES, VW_APT_LISTS (default /var/lib/apt/lists),
# VW_REBOOT_FILE (default /var/run/reboot-required), VW_PATH_SUFFIX (appended to PATH; default the system bin directories).
set -u
export LC_ALL=C
PATH="$PATH${VW_PATH_SUFFIX-:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin}"

max_bytes="${VW_MAX_BYTES:-60000}"
apt_lists="${VW_APT_LISTS:-/var/lib/apt/lists}"
reboot_file="${VW_REBOOT_FILE:-/var/run/reboot-required}"

usage() {
    echo "usage: ${0##*/} dpkg N M | apt" >&2
    exit 2
}

# ---------------------------------------------------------------------------------------------------------------------
cmd_dpkg() {
    local n="${1:-}" m="${2:-}"
    case "$n" in '' | *[!0-9]*) usage ;; esac
    case "$m" in '' | *[!0-9]*) usage ;; esac
    [ "$m" -ge 1 ] 2>/dev/null && [ "$n" -lt "$m" ] || usage
    case "$max_bytes" in '' | *[!0-9]*) max_bytes=60000 ;; esac

    if ! command -v dpkg-query >/dev/null 2>&1; then
        echo "#nodpkg"
        return 0
    fi

    # Stage 1: keep installed packages (second status character: installed or partly installed, held ones included), dedupe by
    # binary name (a multi-arch package is listed once), compute the CRC, keep our shard.
    # Stage 2: sort by binary name, add the header, cut at max_bytes.
    # pipefail: a failing dpkg-query must not look like an empty, healthy shard.
    local out
    out="$(set -o pipefail
    dpkg-query -W -f='${db:Status-Abbrev}\t${Package}\t${Version}\t${source:Package}\t${source:Version}\n' 2>/dev/null |
        awk -F'\t' -v n="$n" -v m="$m" '
            function xor8(a, b,    k, r, bit, i, x, y) {
                k = a * 256 + b
                if (k in xm) return xm[k]
                r = 0; bit = 1; x = a; y = b
                for (i = 0; i < 8; i++) {
                    if ((x % 2) != (y % 2)) r += bit
                    x = int(x / 2); y = int(y / 2); bit *= 2
                }
                xm[k] = r
                return r
            }
            function step(b,    idx, t0, t1, t2, t3) {
                idx = xor8(c0, b)
                t0 = T0[idx]; t1 = T1[idx]; t2 = T2[idx]; t3 = T3[idx]
                c0 = xor8(c1, t0); c1 = xor8(c2, t1); c2 = xor8(c3, t2); c3 = t3
            }
            function crc_mod(s,    i, len, b) {
                c0 = 0; c1 = 0; c2 = 0; c3 = 0
                len = length(s)
                for (i = 1; i <= len; i++) step(ord[substr(s, i, 1)])
                while (len > 0) { step(len % 256); len = int(len / 256) }
                # complement; four bytes fit a double exactly, so any modulus works
                return ((255 - c0) * 16777216 + (255 - c1) * 65536 + (255 - c2) * 256 + (255 - c3)) % m
            }
            BEGIN {
                for (i = 1; i < 256; i++) ord[sprintf("%c", i)] = i
                # CRC table for the POSIX cksum polynomial 0x04C11DB7 (MSB first), kept as four bytes per entry
                p0 = 4; p1 = 193; p2 = 29; p3 = 183
                for (i = 0; i < 256; i++) {
                    a0 = i; a1 = 0; a2 = 0; a3 = 0
                    for (j = 0; j < 8; j++) {
                        top = (a0 >= 128)
                        b0 = (a0 * 2) % 256 + int(a1 / 128)
                        b1 = (a1 * 2) % 256 + int(a2 / 128)
                        b2 = (a2 * 2) % 256 + int(a3 / 128)
                        b3 = (a3 * 2) % 256
                        if (top) { b0 = xor8(b0, p0); b1 = xor8(b1, p1); b2 = xor8(b2, p2); b3 = xor8(b3, p3) }
                        a0 = b0; a1 = b1; a2 = b2; a3 = b3
                    }
                    T0[i] = a0; T1[i] = a1; T2[i] = a2; T3[i] = a3
                }
            }
            substr($1, 2, 1) ~ /[iUFHWt]/ && $2 != "" {
                if ($2 in seen) next
                seen[$2] = 1
                if (crc_mod($2) != n) next
                v = $3; s = $4; sv = $5
                if (s == "") s = $2
                if (sv == "") sv = v
                print $2 "\t" v "\t" s "\t" sv
            }' |
        sort -t "$(printf '\t')" -k1,1 |
        awk -v n="$n" -v m="$m" -v max="$max_bytes" '
            { line[++cnt] = $0 }
            END {
                head = "#vw.dpkg shard=" n " of=" m " count=" (cnt + 0)
                out = head "\n"; used = length(head) + 1
                tail = "#truncated\n"
                cut = 0
                for (i = 1; i <= cnt; i++) {
                    l = length(line[i]) + 1
                    # keep room for the marker whenever anything is left out
                    if (used + l > max || (i < cnt && used + l + length(tail) > max)) { cut = 1; break }
                    out = out line[i] "\n"; used += l
                }
                if (cut) out = out "#truncated\n"
                printf "%s", out
            }')" || exit 1
    printf '%s\n' "$out"
}

# ---------------------------------------------------------------------------------------------------------------------
json_escape() {
    printf '%s' "$1" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g' | tr -d '\000-\037'
}

cmd_apt() {
    if ! command -v apt >/dev/null 2>&1; then
        echo '{"error":"no-apt"}'
        return 0
    fi

    local list pending security names
    list="$(apt list --upgradable 2>/dev/null | grep '\[upgradable' || true)"
    if [ -n "$list" ]; then
        pending="$(printf '%s\n' "$list" | wc -l)"
        # first field is "name/suite[,suite...]"; security = a suite containing -security
        security="$(printf '%s\n' "$list" | awk '$1 ~ /\/[^ ]*-security/ { c++ } END { print c + 0 }')"
        names="$(printf '%s\n' "$list" | awk '$1 ~ /\/[^ ]*-security/ { sub(/\/.*/, "", $1); print $1 }' | head -n 20)"
    else
        pending=0
        security=0
        names=""
    fi
    pending="$(printf '%s' "$pending" | tr -d ' ')"

    local reboot=false
    [ -e "$reboot_file" ] && reboot=true

    local now newest age=-1
    now="$(date +%s)"
    newest="$(find "$apt_lists" -maxdepth 1 -type f -printf '%T@\n' 2>/dev/null | sort -nr | head -n 1)"
    if [ -n "$newest" ]; then
        newest="${newest%%.*}"
        case "$newest" in '' | *[!0-9]*) ;; *) age=$((now - newest)) ;; esac
        [ "$age" -lt 0 ] && age=0
    fi

    local running inst_pkg="" inst_ver=""
    running="$(uname -r 2>/dev/null || true)"
    if command -v dpkg-query >/dev/null 2>&1; then
        # newest installed kernel image package of the running kernel's flavour (versioned names only, not the linux-image-amd64
        # meta package; other flavours such as -cloud-amd64 and -dbg packages are ignored). The flavour is what is left of
        # `uname -r` after the version, for example -amd64; when it cannot be derived every versioned image counts.
        local flav
        flav="$(printf '%s' "$running" | sed -E 's/^[0-9]+(\.[0-9]+)*([+~][^-]*)?(-[0-9]+(\.[0-9]+)*)?//')"
        inst_pkg="$(dpkg-query -W -f='${db:Status-Abbrev}\t${Package}\n' 'linux-image-*' 2>/dev/null |
            awk -F'\t' -v f="$flav" 'substr($1, 2, 1) ~ /[iUFHWt]/ && $2 ~ /^linux-image-[0-9]/ {
                    n = $2; sub(/^linux-image-/, "", n)
                    if (f == "") { print n; next }
                    if (length(n) <= length(f) || substr(n, length(n) - length(f) + 1) != f) next
                    b = substr(n, 1, length(n) - length(f))
                    if (b ~ /^[0-9][0-9.+~a-z]*(-[0-9.]+)?$/) print n
                }' |
            sort -V | tail -n 1)"
        if [ -n "$inst_pkg" ]; then
            inst_pkg="linux-image-$inst_pkg"
            inst_ver="$(dpkg-query -W -f='${Version}' "$inst_pkg" 2>/dev/null || true)"
        fi
    fi

    # Build the JSON; drop security package names (last first) until it fits in 2 KB.
    local k=20 total json namelist
    while :; do
        namelist="$(printf '%s\n' "$names" | awk -v k="$k" 'NF && NR <= k { gsub(/[\\"]/, ""); printf "%s\"%s\"", (c++ ? "," : ""), $1 }')"
        json="{\"pending\":$pending,\"security\":$security,\"security_pkgs\":[$namelist],\"reboot_required\":$reboot,\"lists_age_s\":$age"
        json="$json,\"kernel_running\":\"$(json_escape "$running")\",\"kernel_installed\":\"$(json_escape "$inst_ver")\",\"kernel_installed_pkg\":\"$(json_escape "$inst_pkg")\"}"
        total="${#json}"
        if [ "$total" -le 2048 ] || [ "$k" -le 0 ]; then break; fi
        k=$((k - 1))
    done
    printf '%s\n' "$json"
}

# ---------------------------------------------------------------------------------------------------------------------
case "${1:-}" in
    dpkg) shift; cmd_dpkg "${1:-}" "${2:-}" ;;
    apt) cmd_apt ;;
    *) usage ;;
esac
