---
title: What a website shows to anyone (TLS, HTTPS, headers, banners, private files)
scope: any public website or web app a person or team runs, behind a CDN or not
when_to_use: launching a site; a certificate is about to expire; reviewing what a site tells a visitor; the sysadmin pack's `web` check reported something
related: [README.md, hardening-ssh-fail2ban-waf.md, publishing-without-leaks.md, static-sites-deploy-keys.md]
---
# What a website shows to anyone

Everything here can be seen by any visitor with a browser, so it is the first thing a scanner reads. The `web` check of the
`sysadmin` pack reads exactly this (SEC-WEB-1 to 4) and nothing more. SEC-WEB-5 probes paths, so it needs proof that the
site is yours.

## Quick reference
| Situation | Rule |
|---|---|
| Certificate expiring, expired or not matching the name | SEC-WEB-1 |
| The site still answers on plain HTTP | SEC-WEB-2 |
| Missing security headers | SEC-WEB-3 |
| The server says its version | SEC-WEB-4 |
| `/.git/`, `/.env` or a directory listing is reachable | SEC-WEB-5 |
| The site is behind a CDN | SEC-WEB-6 |

## Rules

### SEC-WEB-1: A valid certificate, renewed by itself, checked from outside
- **Rule:** the certificate matches the name, chains to a public CA, renews automatically and has more than 14 days left. Only
  TLS 1.2 and 1.3 are offered.
- **Why:** an expired certificate takes the site down for every visitor, and automatic renewal fails silently (a DNS change,
  a moved web root, a port 80 that a new firewall rule closed).
- **How:** `certbot renew --dry-run` (or the CDN's own certificate). In nginx: `ssl_protocols TLSv1.2 TLSv1.3;`.
- **Verify:** `echo | openssl s_client -connect <domain>:443 -servername <domain> 2>/dev/null | openssl x509 -noout -enddate -subject`.
  Then `openssl s_client -connect <domain>:443 -tls1_1` must fail.
- **Don't:** trust the renewal cron because it exists; read the expiry date from outside.

### SEC-WEB-2: HTTPS only: redirect port 80, then HSTS
- **Rule:** plain HTTP answers only with a permanent redirect to `https://` (or the port is closed). HTTPS sends
  `Strict-Transport-Security: max-age=31536000` (180 days at least).
- **Why:** a page served over HTTP can be read and changed on the way; HSTS makes the browser skip HTTP on the next visits.
- **How:** nginx `return 301 https://$host$request_uri;` on port 80; `add_header Strict-Transport-Security "max-age=31536000" always;`.
- **Verify:** `curl -sI http://<domain>/` gives 301/308 with `Location: https://...`; `curl -sI https://<domain>/ | grep -i strict`.
- **Don't:** add `includeSubDomains` or `preload` before every subdomain serves HTTPS: browsers enforce it for months.

### SEC-WEB-3: The three cheap headers, plus a CSP when you can
- **Rule:** `X-Content-Type-Options: nosniff`, framing limited (`X-Frame-Options: SAMEORIGIN` or CSP `frame-ancestors 'self'`)
  and `Referrer-Policy: strict-origin-when-cross-origin`. A `Content-Security-Policy` when the site's scripts are known.
- **Why:** they block MIME sniffing, clickjacking and leaking full URLs to other sites, at almost no cost. A CSP limits what an
  injected script can do.
- **How:** `add_header ... always;` in the server block. In nginx, an `add_header` inside a `location` replaces all the
  inherited ones, so repeat them there.
- **Verify:** `curl -sI https://<domain>/` and read the headers.
- **Don't:** copy a strict CSP from another site without testing; it breaks pages silently. Start with
  `Content-Security-Policy-Report-Only`.

### SEC-WEB-4: Do not advertise versions
- **Rule:** no version in `Server`, no `X-Powered-By`, no generator tag that names a CMS version.
- **Why:** a version string turns a CVE list into a target list; scanners grep for it.
- **How:** nginx `server_tokens off;`, PHP `expose_php = Off`, remove `X-Powered-By` in the app or the proxy
  (`proxy_hide_header X-Powered-By;`).
- **Verify:** `curl -sI https://<domain>/ | grep -iE '^(server|x-powered-by):'`.
- **Don't:** treat hiding the version as patching. It only removes the easy match, so patch as well (SEC-PATCH-1).

### SEC-WEB-5: Nothing private under the web root
- **Rule:** `/.git/`, `/.env`, backups (`*.sql`, `*.zip`, `*.bak`) and directory listings are not reachable.
- **Why:** an exposed `.git` gives away the whole source and its history; an exposed `.env` gives away the keys.
- **How:** deploy only the built files (never the repo); `autoindex off;`; deny dotfiles
  (`location ~ /\.(?!well-known) { return 404; }`; see the mini-WAF in SEC-HARD-10).
- **Verify:** `curl -s -o /dev/null -w '%{http_code}\n' https://<domain>/.git/HEAD`, `/.env` and `/` of a folder with no index
  must not be 200.
- **Proof first:** these are probes, so the `sysadmin` pack runs them only on a site that holds its token at
  `/.well-known/bridgeai-sysadmin.txt` or in a DNS TXT record.

### SEC-WEB-6: Behind a CDN, check the origin too
- **Rule:** read the headers both through the CDN and at the origin. Allow only the CDN to reach the origin.
- **Why:** the CDN may add or hide headers, so the public view is not the origin's. An origin open to everyone skips the CDN's
  protections, and its real address leaks through old DNS records and certificate logs.
- **How:** firewall the origin's 80/443 to the CDN's published ranges, or use the CDN's tunnel. Ban in nginx, not iptables
  (SEC-HARD-6).
- **Verify:** `curl -sI --resolve <domain>:443:<origin-ip> https://<domain>/` from outside the CDN.
