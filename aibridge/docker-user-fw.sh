#!/bin/bash
# Ports published by containers (docker run -p) do NOT go through ufw (INPUT),
# they go straight through DOCKER-USER in FORWARD. Without this, any -p is
# wide open to the whole internet. The container's response leaves with the
# bridge's own IP (not the LAN one) -> ESTABLISHED,RELATED has to be allowed
# first, otherwise return traffic gets dropped.
#
# Copy of /usr/local/sbin/docker-user-fw.sh on VM105 (backdocker), with ONE
# line added to let edge VM101 (192.168.3.1) reach the published ports --
# aibridge needs this so the bridge.loadsavedelete.com vhost can proxy_pass
# here.
set -e
iptables -F DOCKER-USER
iptables -I DOCKER-USER -m conntrack --ctstate ESTABLISHED,RELATED -j RETURN
iptables -I DOCKER-USER -i lo -j RETURN
iptables -I DOCKER-USER -s 192.168.1.0/24 -j RETURN
iptables -I DOCKER-USER -s 192.168.3.1 -j RETURN
iptables -A DOCKER-USER -j DROP
