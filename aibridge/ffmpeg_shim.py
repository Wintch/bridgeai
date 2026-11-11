#!/usr/bin/env python3
"""ffmpeg in a stack container (/usr/local/bin/ffmpeg, ahead of /usr/bin/ffmpeg on PATH): the real ffmpeg with two guards.

1. A thread cap. A stack has `docker --cpus 1` but nproc shows the VM's 4 cores, so ffmpeg sizes its threads for 4 cores (24
   threads were seen), each holding whole frames: a hand-run 4K libx264 encode reached 1.9 GB of the stack's 2.5 GB.
   When the command has no -threads of its own, the decoder, the filters and the last output get the container's real CPU count
   (cgroup cpu.max), and libx265/libsvtav1 get their pool size. Measured the same day under the stack's limits: 4K to 480p in
   294-350 MB instead of 1.9 GB.
2. No AV1 encoded by hand. libaom-av1, libsvtav1 and librav1e on this one CPU took hours on a 196 MB video and were killed for
   memory twice. `gateway transcode ... codec=av1` sends it to a free video host, or does it here only when its estimate is short
   (it sets AIBRIDGE_FFMPEG_GATEWAY=1). Decoding AV1 is not affected.

Commands with no -i (ffmpeg -version, -encoders, -h) pass through untouched. Everything else is passed on as given.
"""
import math
import os
import sys

REAL = "/usr/bin/ffmpeg"
AV1_ENCODERS = {"libaom-av1", "libsvtav1", "librav1e"}


def quota():
    n = os.cpu_count() or 1
    try:
        q, p = open("/sys/fs/cgroup/cpu.max").read().split()[:2]
        if q != "max":
            n = min(n, max(1, math.ceil(int(q) / int(p))))
    except (OSError, ValueError):
        pass
    return max(1, min(n, 4))


def shape(args, threads):
    """The argument list with the thread cap added where the command set none (pure function, for the selftest)."""
    if "-i" not in args:
        return list(args)
    t = str(threads)
    out = list(args)
    if "-threads" not in out:
        last = out[-1]
        if last == "-" or not last.startswith("-"):        # the last output file: its encoders get the cap
            out[-1:] = ["-threads", t, last]
        first_i = out.index("-i")
        out[first_i:first_i] = ["-threads", t]          # the first input's decoder (4K frames live there)
    if "-filter_threads" not in out:
        out[0:0] = ["-filter_threads", t]
    if "-filter_complex" in out and "-filter_complex_threads" not in out:
        out[0:0] = ["-filter_complex_threads", t]
    if "libx265" in out and "-x265-params" not in out:
        i = len(out) - 1 if out[-1] == "-" or not out[-1].startswith("-") else len(out)
        out[i:i] = ["-x265-params", f"pools={t}:frame-threads=1"]
    if "libsvtav1" in out and "-svtav1-params" not in out:
        i = len(out) - 1 if out[-1] == "-" or not out[-1].startswith("-") else len(out)
        out[i:i] = ["-svtav1-params", f"lp={t}"]
    return out


def main():
    args = sys.argv[1:]
    if os.environ.get("AIBRIDGE_FFMPEG_GATEWAY") != "1" and "-i" in args:
        last_i = len(args) - 1 - args[::-1].index("-i")
        if AV1_ENCODERS & set(args[last_i:]):           # an AV1 encoder named after the inputs: an encode, not a decode
            sys.stderr.write("ffmpeg: AV1 is not encoded by hand in this container (one CPU: hours, and it runs out of memory). "
                             "Use: gateway transcode IN OUT codec=av1 [height=720]. It sends the job to a free video host, "
                             "or makes it here only when that is quick. The same command does h264 and hevc too.\n")
            return 2
    os.execv(REAL, [REAL] + shape(args, quota()))


if __name__ == "__main__":
    sys.exit(main())
