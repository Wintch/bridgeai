# A headless Quake III Arena demo dedicated server (ioquake3, id Software's free demo data packaged at build time by Debian's game-data-packager), for LAN
# games between places. No display, no GPU, no shell needed at run time; runs as an unprivileged user. See ../PLACES.md, "A shared LAN server".
#   docker build -t bridgeai-q3ded:latest .      then run.sh (or the docker run line it prints)
FROM debian:trixie-slim
RUN set -eux; \
    printf 'Types: deb\nURIs: http://deb.debian.org/debian\nSuites: trixie trixie-updates\nComponents: main contrib\nSigned-By: /usr/share/keyrings/debian-archive-keyring.gpg\n\nTypes: deb\nURIs: http://deb.debian.org/debian-security\nSuites: trixie-security\nComponents: main contrib\nSigned-By: /usr/share/keyrings/debian-archive-keyring.gpg\n' > /etc/apt/sources.list.d/debian.sources; \
    apt-get update; \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends ioquake3-server game-data-packager ca-certificates; \
    mkdir -p /tmp/q3; /usr/games/game-data-packager quake3 --demo -d /tmp/q3 --no-search --download; \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends /tmp/q3/quake3-demo-data_*_all.deb; rm -rf /tmp/q3; \
    DEBIAN_FRONTEND=noninteractive apt-get purge -y --auto-remove game-data-packager; \
    apt-get clean; rm -rf /var/lib/apt/lists/*; \
    test -e /usr/lib/quake3/demo/demoq3/pak0.pk3; ls /usr/lib/ioquake3/ioq3ded; \
    useradd -r -u 27960 -m -d /home/q3 q3
USER q3
WORKDIR /usr/lib/ioquake3
# The demo's own QVMs are an older interface: the game code runs from ioquake3's native library (vm_game 0), and a non-pure server keeps it that way.
# dedicated 1 = LAN only (no heartbeat to the public master servers). SV_HOSTNAME and SV_MAP can be set at run time.
ENV SV_HOSTNAME=bridgeai-lan-bots SV_MAP=q3dm17
ENTRYPOINT ["sh", "-c", "exec ./ioq3ded +set fs_basepath /usr/lib/quake3/demo +set fs_homepath /home/q3/.q3a +set com_basegame demoq3 +set dedicated 1 +set net_port 27960 +set net_enabled 1 +set sv_pure 0 +set vm_game 0 +set sv_hostname \"$SV_HOSTNAME\" +set sv_maxclients 12 +set g_gametype 0 +set fraglimit 30 +set timelimit 0 +set bot_enable 1 +set logfile 1 +map \"$SV_MAP\""]
