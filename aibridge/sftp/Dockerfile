# One person's file access over SFTP (design: ops/stack_sftp.py). A chrooted internal-sftp and nothing else: no shell, no forwarding, no keys, one
# user whose password hash is a file the operator tool writes. The person's folders are mounted by the compose file the tool generates.
FROM debian:13@sha256:9c6e381421d0f48d1b8133e573f33c185ee16cbf505eda9c4a8a4791b25ea8a6
RUN apt-get update && apt-get install -y --no-install-recommends openssh-server \
    && rm -rf /var/lib/apt/lists/* /etc/ssh/ssh_host_* \
    && mkdir -p /run/sshd /srv/view /config \
    && chown root:root /srv/view && chmod 755 /srv/view
# The image is read-only at run time, so the account files live on the tmpfs /run (the entrypoint writes them at every start from the username and
# hash files); /etc/passwd and /etc/shadow are links to them, the originals stay as templates.
RUN cp /etc/passwd /etc/passwd.template && cp /etc/shadow /etc/shadow.template \
    && rm /etc/passwd /etc/shadow && ln -s /run/passwd /etc/passwd && ln -s /run/shadow /etc/shadow
COPY sshd_config /etc/ssh/sshd_config.template
COPY entrypoint.sh /entrypoint.sh
COPY LEEME.txt /srv/view/LEEME.txt
RUN chmod 755 /entrypoint.sh && chmod 444 /srv/view/LEEME.txt
EXPOSE 2222
ENTRYPOINT ["/entrypoint.sh"]
