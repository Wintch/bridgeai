#!/usr/bin/env python3
"""Keep the private image registry small: delete every image of aibridge-hermes-agent except the last KEEP builds, then run the
registry's own garbage collection. The Docker host keeps its images locally (rollback is its prev- tag), so nothing deployed
depends on an old image here.

  python3 ops/registry_gc.py            # dry run: what would go
  python3 ops/registry_gc.py --apply    # delete and collect (skipped while a build holds BUILD_DIR/buildkit.lock)

Which builds stay: the digests in the KEEP newest BUILD_DIR/out/*.digest files (the pipeline writes one per build). A tag whose image
is one of them stays, whatever its name. Settings: REGISTRY and the push account, as in ops/lib/pipeline_env.sh (environment or the
untracked BUILD_DIR/pipeline.env). KEEP from the environment, default 8. Nothing is deleted when no digest file is found."""
import base64, fcntl, glob, json, os, ssl, subprocess, sys, urllib.request

BUILD_DIR = os.environ.get("BUILD_DIR", "/mnt/nvme/bridgeai-build")
REPO = "aibridge-hermes-agent"
ACCEPT = ", ".join(["application/vnd.oci.image.index.v1+json", "application/vnd.docker.distribution.manifest.list.v2+json",
                    "application/vnd.oci.image.manifest.v1+json", "application/vnd.docker.distribution.manifest.v2+json"])
ALLOWED = {"REGISTRY", "REGISTRY_CA", "REGISTRY_PUSH_USER", "REGISTRY_PUSH_PASS_FILE"}


def settings():
    """The pipeline's settings: the environment first, then BUILD_DIR/pipeline.env (read, never executed)."""
    conf = {}
    try:
        for line in open(os.path.join(BUILD_DIR, "pipeline.env")):
            k, sep, v = line.strip().partition("=")
            if sep and k in ALLOWED and not line.lstrip().startswith("#"):
                conf[k] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    conf.update({k: os.environ[k] for k in ALLOWED if os.environ.get(k)})
    conf.setdefault("REGISTRY_CA", os.path.join(BUILD_DIR, "registry/certs/ca.crt"))
    conf.setdefault("REGISTRY_PUSH_USER", "pusher")
    conf.setdefault("REGISTRY_PUSH_PASS_FILE", os.path.join(BUILD_DIR, "registry/auth/pusher.pass"))
    return conf


def kept_digests(out_dir, keep):
    """The digests of the `keep` newest *.digest files (newest first by modification time)."""
    files = sorted(glob.glob(os.path.join(out_dir, "*.digest")), key=os.path.getmtime, reverse=True)[:keep]
    out = []
    for f in files:
        d = open(f).read().strip()
        if d.startswith("sha256:") and d not in out:
            out.append(d)
    return out


def plan(tag_digests, keep):
    """Pure: {tag: digest} and the digests to keep -> (digests to delete, tags they carry). Never deletes with an empty keep list."""
    if not keep:
        return [], []
    gone = sorted({d for d in tag_digests.values() if d and d not in keep})
    return gone, sorted(t for t, d in tag_digests.items() if d in gone)


class Registry:
    def __init__(self, conf):
        self.base = f"https://{conf['REGISTRY']}/v2/{REPO}"
        self.ctx = ssl.create_default_context(cafile=conf["REGISTRY_CA"])
        # Our self-made CA has no keyUsage extension: Python 3.13's strict mode refuses it (Docker accepts it). The chain is still checked.
        self.ctx.verify_flags &= ~getattr(ssl, "VERIFY_X509_STRICT", 0)
        pw = open(conf["REGISTRY_PUSH_PASS_FILE"]).read().strip()
        self.auth = "Basic " + base64.b64encode(f"{conf['REGISTRY_PUSH_USER']}:{pw}".encode()).decode()

    def call(self, method, path, headers=None):
        req = urllib.request.Request(self.base + path, method=method, headers={"Authorization": self.auth, **(headers or {})})
        return urllib.request.urlopen(req, context=self.ctx, timeout=30)

    def tags(self):
        return json.load(self.call("GET", "/tags/list")).get("tags") or []

    def digest(self, tag):
        return self.call("HEAD", f"/manifests/{tag}", {"Accept": ACCEPT}).headers.get("Docker-Content-Digest")

    def delete(self, digest):
        self.call("DELETE", f"/manifests/{digest}")


def main(argv):
    apply = "--apply" in argv
    keep_n = int(os.environ.get("KEEP", "8"))
    conf = settings()
    if not conf.get("REGISTRY"):
        print("registry_gc: no REGISTRY set (environment or BUILD_DIR/pipeline.env): nothing to do")
        return 0
    keep = kept_digests(os.path.join(BUILD_DIR, "out"), keep_n)
    reg = Registry(conf)
    tag_digests = {t: reg.digest(t) for t in reg.tags()}
    gone, tags = plan(tag_digests, keep)
    print(f"registry_gc: {len(tag_digests)} tags, keeping {len(keep)} build digests, {len(gone)} images to delete"
          + (f" (tags: {', '.join(tags)})" if tags else ""))
    if not keep:
        print("registry_gc: no *.digest file found in BUILD_DIR/out: refusing to delete anything")
        return 0
    if not apply or not gone:
        return 0
    with open(os.path.join(BUILD_DIR, "buildkit.lock"), "a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            print("registry_gc: a build is running (buildkit.lock held): skipped, the next run deletes")
            return 0
        for d in gone:
            reg.delete(d)
        r = subprocess.run(["docker", "exec", "bridgeai-registry", "registry", "garbage-collect", "--delete-untagged",
                            "/etc/docker/registry/config.yml"], capture_output=True, text=True, timeout=600)
        print(f"registry_gc: deleted {len(gone)}; garbage-collect rc={r.returncode}"
              + ("" if r.returncode == 0 else f": {(r.stderr or r.stdout)[-300:]}"))
        return r.returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
