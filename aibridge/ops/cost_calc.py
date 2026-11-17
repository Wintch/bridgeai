#!/usr/bin/env python3
"""
cost_calc.py - rough cost and price calculator for bridgeai as a service.

Python 3 stdlib only. Everything is an ESTIMATE. Edit the PARAMS dict below,
or override from a JSON file:

    python3 -I cost_calc.py                      # run with defaults
    python3 -I cost_calc.py --template > my.json # print a JSON template
    python3 -I cost_calc.py --params my.json     # override (deep merge, only
                                                 # the keys you list change)

See SCALING_AND_COSTS.md for the reasoning behind the numbers.

Items marked MEASURED are rough values seen in telemetry on one small shared
host with a few users (container stats, cgroups, session databases). They are
a starting point, not a benchmark: measure your own. Items marked ESTIMATE are
engineering judgement or assumptions.

Region costs, token prices and hourly rates are EXAMPLE PLACEHOLDERS. They
are not quotes. Put your own region's numbers in (that is the point of this
file).

All money values use one currency (PARAMS["region"]["currency"] is only a
label). Token prices are per million tokens. Results are before taxes.
"""
import argparse
import copy
import json
import math
import sys

PARAMS = {
    # ------------------------------------------------------------------
    # 1. REGION COSTS (EXAMPLE PLACEHOLDERS - replace with your region's quotes)
    # ------------------------------------------------------------------
    "region": {
        "currency": "USD",                 # label only, no conversion is done
        "vps_per_gb_ram_month": 2.0,       # EXAMPLE: 12 GB + 4 vCPU + 80 GB ~ 46/month
        "vps_per_vcpu_month": 4.0,         # ESTIMATE
        "storage_per_gb_month": 0.08,      # ESTIMATE: block/SSD storage
        "egress_per_gb": 0.0,              # most VPS include traffic; set >0 if billed (large media files and off-host restores can be billed)
        "gpu_per_hour": 0.45,              # ESTIMATE: rented 24 GB consumer-class card, per wall hour
        "electricity_per_kwh": 0.12,       # own hardware only
        "own_hw_host_watts": 60,           # ESTIMATE: average draw of a small home/office host
        "own_hw_amortisation_month": 12.0, # ESTIMATE: hardware cost spread per month
        "host_mode": "vps",                # "vps" (rented) or "own" (own hardware)
        # Fully loaded hourly cost per role (salary + employer charges). EXAMPLES.
        # Support is set low here: check it against your market.
        "human_hourly": {
            "sre": 22.0, "dev": 25.0, "qa": 15.0, "security": 30.0,
            "support": 8.0, "sales": 12.0, "product": 28.0
        },
        "hours_per_fte_month": 160,        # paid hours per FTE-month
    },

    # ------------------------------------------------------------------
    # 2. MODEL TOKEN PRICES per class, per million tokens (ESTIMATE, replace
    #    with your provider's list). "in" = uncached input, "cin" = cache-read
    #    input, "out" = output (hidden reasoning is billed as output).
    #    People bring their own keys, so by default these are informational.
    # ------------------------------------------------------------------
    "model": {
        "classes": {
            "free":    {"in": 0.0,  "cin": 0.0,   "out": 0.0},   # free tiers (rate limited)
            "cheap":   {"in": 0.10, "cin": 0.025, "out": 0.40},  # small/open-weight hosted
            "mid":     {"in": 0.60, "cin": 0.15,  "out": 2.50},
            "premium": {"in": 3.00, "cin": 0.30,  "out": 15.00}
        },
        "selected_class": "cheap",         # class used in the package tables
        "include_tokens_in_price": False   # False = client pays the provider directly (BYO key)
    },

    # ------------------------------------------------------------------
    # 3. PLATFORM / STACK constants
    # ------------------------------------------------------------------
    "stack": {
        "host_ram_gb": 12,                 # reference host
        "host_vcpu": 4,                    # reference host
        "host_disk_gb": 80,                # reference host
        "host_fixed_disk_gb": 36,          # MEASURED approx: OS, images and tools, without backups or bot data
        "disk_headroom": 0.20,             # ESTIMATE: keep 20% free
        "baseline_gb": 1.4,                # MEASURED approx: 1.4-1.9 GB with no brains
        "reserve_gb": 1.5,                 # MEASURED: memory the waker keeps free
        "brain_gb": 0.55,                  # MEASURED 0.47-0.54 resident, cgroup peaks 0.63-2.0
        "web_gb": 0.30,                    # ESTIMATE: extra for a bot with a web front
        "always_on_gb": 0.02,              # MEASURED 15-25 MB per stack (bot-api + proxy)
        "always_on_cpu_h_day": 0.16,       # MEASURED telegram-bot-api per stack
        "cpu_core_per_awake_h": 0.05,      # MEASURED about 0.05 core average while awake
        "boot_cpu_s": 28,                  # ESTIMATE 25-30 CPU-s per wake
        "ram_utilisation": 0.60,           # ESTIMATE: share of billed RAM actually usable (peaks, cache)
        "cpu_utilisation": 0.50,           # ESTIMATE
        "max_awake": 4,                    # waker setting; RAM alone would allow about twice that
        "peak_factor": 2.4,                # ESTIMATE: working-hours concentration
        "peak_z": 1.645,                   # P(wait) <= 5%
        "correlation_haircut": 0.67,       # ESTIMATE: cut counts by about one third, peaks are correlated
        "wakes_per_host_day_limit": 400,   # ESTIMATE: serial boot slot (one boot at a time) queues beyond this
        "backup_keep": 7,                  # backups kept per bot (a policy value)
        "platform_fixed_per_host_month": 5.0,  # ESTIMATE: edge, monitoring, off-host backup share (raise it if you add an off-site node)
        "overhead_bots_per_host": 20,      # ESTIMATE: bots sharing that platform overhead
        "ha_standby_fraction": 0.5,        # ESTIMATE: warm standby hosts per active host (min 1)
        "ha_enabled_from_agents": 10       # standby only counted from this fleet size
    },

    # ------------------------------------------------------------------
    # 4. BOT PROFILES (per bot, per day unless noted)
    #    awake_h_day = hours/day the brain is awake under the sleep rule
    #    (central value; range in the comment). tokens in millions/day.
    # ------------------------------------------------------------------
    "bots": {
        # Personal bot used through a web page. Awake roughly 0.9 to 1.5 h/day.
        "personal_web": {
            "awake_h_day": 1.2, "web_tier": 1, "cpu_mult": 1.0, "wakes_day": 2.9,
            "live_gb": 0.21, "backup_gb": 0.17,
            "prompt_m_day": 1.37, "cache_share": 0.79, "out_k_day": 19,
            "gpu_h_month": 0.0, "egress_gb_month": 1.5
        },
        # Personal bot used through a chat app, many turns a day. Awake roughly
        # 4 to 6.7 h/day on the sleep rule; about 24 h/day if kept warm.
        "personal_chat_heavy": {
            "awake_h_day": 5.0, "web_tier": 0, "cpu_mult": 1.0, "wakes_day": 11.4,
            "live_gb": 2.5, "backup_gb": 1.64,
            "prompt_m_day": 7.14, "cache_share": 0.81, "out_k_day": 122,
            "gpu_h_month": 5.5, "egress_gb_month": 2.0
        },
        # Business task bot (an IT bot, a marketing bot, a news bot, averaged).
        # Awake roughly 0.1 to 0.6 h/day, 0.1 to 1.1 M prompt tokens/day.
        "business_task": {
            "awake_h_day": 0.30, "web_tier": 0, "cpu_mult": 1.0, "wakes_day": 1.7,
            "live_gb": 0.01, "backup_gb": 0.008,
            "prompt_m_day": 0.63, "cache_share": 0.80, "out_k_day": 12,
            "gpu_h_month": 0.0, "egress_gb_month": 1.3
        },
        # Media bot. Awake roughly 0.5 to 0.8 h/day, about 70 model calls/day.
        # GPU wall time is bursty: plan with 10-42 h/month, central 20.
        "media_design": {
            "awake_h_day": 0.65, "web_tier": 0, "cpu_mult": 2.0, "wakes_day": 2.3,
            "live_gb": 0.01, "backup_gb": 0.28,
            "prompt_m_day": 3.08, "cache_share": 0.91, "out_k_day": 36,
            "gpu_h_month": 20.0, "egress_gb_month": 2.5
        },
        # Personal bot that is rarely used: 0.01-0.09 h/day, 0-1.6 calls/day.
        "personal_light": {
            "awake_h_day": 0.05, "web_tier": 0, "cpu_mult": 1.0, "wakes_day": 0.2,
            "live_gb": 0.10, "backup_gb": 0.15,
            "prompt_m_day": 0.053, "cache_share": 0.40, "out_k_day": 1,
            "gpu_h_month": 0.0, "egress_gb_month": 1.3
        },
        # Reception/support bot: NOT measured. ESTIMATE: 35-50% duty in
        # business hours (8-12 h), ~60 calls/day x 40k prompt tokens.
        "receptionist_hot": {
            "awake_h_day": 9.0, "web_tier": 0, "cpu_mult": 1.0, "wakes_day": 4.0,
            "live_gb": 0.05, "backup_gb": 0.05,
            "prompt_m_day": 2.4, "cache_share": 0.85, "out_k_day": 40,
            "gpu_h_month": 0.0, "egress_gb_month": 2.0
        }
    },

    # ------------------------------------------------------------------
    # 5. COMPANY MIX (fraction of agents by bot type, for host counts at scale)
    #    ESTIMATE: mostly light task bots, a few receptionists and humans.
    # ------------------------------------------------------------------
    "company_mix": {
        "business_task": 0.45, "receptionist_hot": 0.12, "media_design": 0.10,
        "personal_web": 0.08, "personal_light": 0.20, "personal_chat_heavy": 0.05
    },
    "scale_points": [10, 50, 200],         # agents, for host counts and team size

    # ------------------------------------------------------------------
    # 6. SME PACKAGES (counts of each bot type)
    # ------------------------------------------------------------------
    "packages": {
        "sme_3":  {"receptionist_hot": 1, "business_task": 2},
        "sme_6":  {"receptionist_hot": 1, "business_task": 3, "media_design": 1, "personal_light": 1},
        "sme_10": {"receptionist_hot": 1, "business_task": 5, "media_design": 1,
                    "personal_web": 1, "personal_light": 2}
    },
    # A human who uses and supervises the agents (agents sleep about 65-80% of the
    # time with a human, 80-90% without).
    "human_assist": {
        "awake_mult": 1.9,                 # ESTIMATE: 25-32% awake vs 15%
        "token_mult": 1.8,                 # ESTIMATE
        "support_contacts_mult": 1.5,      # ESTIMATE
        "reasonable_agents_without_human": 3   # ESTIMATE: 2-3 autonomous agents per SME
    },

    # ------------------------------------------------------------------
    # 7. STAFFING (variable, per agent) and TEAM (fixed, by scale)
    #    Use ONE of the two views in a price, not both (they overlap).
    # ------------------------------------------------------------------
    "staffing": {
        # incidents per agent per week. "today" is a rough ESTIMATE for an early
        # system (plausible range 0.1 to 0.4; it does not scale linearly, because
        # one bad release hits every agent at once and counts as one incident).
        # "target" is what regression tests, early detection and consented
        # auto-repair should reach (0.03 or less).
        "incidents_per_agent_week": {"today": 0.19, "target": 0.03},
        "hours_per_incident": 3.0,         # ESTIMATE, range 1-8 h
        "support_contacts_per_agent_month": 1.0,   # ESTIMATE, range 0.5-2
        "minutes_per_contact": 20,         # ESTIMATE
        "incident_role": "sre",            # role billed for incident hours
        "support_role": "support",
        # FTE by role at each scale (ESTIMATE: 10 agents -> 1.5-2 FTE,
        # 50 -> 3.5-5, 200 -> 11-15)
        "team_fte": {
            "10":  {"sre": 0.8, "dev": 0.4, "qa": 0.2, "security": 0.1, "support": 0.1, "sales": 0.1},
            "50":  {"sre": 1.0, "dev": 1.5, "qa": 0.5, "security": 0.4, "support": 0.5, "sales": 0.75},
            "200": {"sre": 2.0, "dev": 3.5, "qa": 1.0, "security": 1.0, "support": 2.5,
                    "sales": 2.0, "product": 1.0}
        }
    },

    # ------------------------------------------------------------------
    # 8. MARGINS
    # ------------------------------------------------------------------
    "margins": {
        "markup_on_cost": 0.40,            # price = cost * (1 + markup) / (1 - fee); on the variable staffing view it does not fund development, sales or product
        "payment_fee": 0.04,               # share of price lost to payment processing; local methods can cost more; chargebacks and FX are not counted
        "min_price_per_agent": 5.0,        # floor
        "usage_sensitivity": [0.6, 1.0, 1.7]   # multipliers on awake hours and tokens
    }
}


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------
def deep_merge(base, over):
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            deep_merge(base[k], v)
        else:
            base[k] = v
    return base


def host_monthly_cost(P):
    R, S = P["region"], P["stack"]
    if R["host_mode"] == "own":
        kwh = R["own_hw_host_watts"] * 0.72  # kWh per month at 24/7
        return kwh * R["electricity_per_kwh"] + R["own_hw_amortisation_month"]
    return (S["host_ram_gb"] * R["vps_per_gb_ram_month"]
            + S["host_vcpu"] * R["vps_per_vcpu_month"]
            + S["host_disk_gb"] * R["storage_per_gb_month"])


def awake_hours(prof, human, mult, P):
    a = prof["awake_h_day"] * mult * (P["human_assist"]["awake_mult"] if human else 1.0)
    return min(24.0, a)


def bot_infra(name, human, mult, P):
    prof, R, S = P["bots"][name], P["region"], P["stack"]
    a = awake_hours(prof, human, mult, P)
    brain = S["brain_gb"] + (S["web_gb"] if prof["web_tier"] else 0.0)
    ram_gbh = a * brain + 24 * S["always_on_gb"]                  # GB-hours per day
    ram = ram_gbh / 24 / S["ram_utilisation"] * R["vps_per_gb_ram_month"]
    wakes = prof["wakes_day"] * (P["human_assist"]["awake_mult"] if human else 1.0) * mult
    cpu_h = (S["always_on_cpu_h_day"]
             + S["cpu_core_per_awake_h"] * a * prof["cpu_mult"]
             + wakes * S["boot_cpu_s"] / 3600.0)                  # CPU-hours per day
    cpu = cpu_h / 24 / S["cpu_utilisation"] * R["vps_per_vcpu_month"]
    disk_gb = prof["live_gb"] + prof["backup_gb"] * S["backup_keep"]
    disk = disk_gb * R["storage_per_gb_month"]
    gpu = prof["gpu_h_month"] * mult * R["gpu_per_hour"]
    egress = prof["egress_gb_month"] * R["egress_per_gb"]
    overhead = ((S["baseline_gb"] * R["vps_per_gb_ram_month"] + S["platform_fixed_per_host_month"])
                / S["overhead_bots_per_host"])
    total = ram + cpu + disk + gpu + egress + overhead
    return {"ram": ram, "cpu": cpu, "disk": disk, "gpu": gpu, "egress": egress,
            "overhead": overhead, "total": total, "awake_h": a}


def bot_tokens(name, cls, human, mult, P):
    prof = P["bots"][name]
    price = P["model"]["classes"][cls]
    tm = (P["human_assist"]["token_mult"] if human else 1.0) * mult
    prompt = prof["prompt_m_day"] * tm
    unc, cached = prompt * (1 - prof["cache_share"]), prompt * prof["cache_share"]
    out = prof["out_k_day"] / 1000.0 * tm
    return 30 * (unc * price["in"] + cached * price["cin"] + out * price["out"])


def staffing_per_agent(scenario, human, P):
    st, hr = P["staffing"], P["region"]["human_hourly"]
    inc = st["incidents_per_agent_week"][scenario] * 52 / 12      # incidents per month
    inc_cost = inc * st["hours_per_incident"] * hr[st["incident_role"]]
    contacts = st["support_contacts_per_agent_month"] * (P["human_assist"]["support_contacts_mult"] if human else 1.0)
    sup_cost = contacts * st["minutes_per_contact"] / 60.0 * hr[st["support_role"]]
    hours = inc * st["hours_per_incident"] + contacts * st["minutes_per_contact"] / 60.0
    return inc_cost + sup_cost, hours


def price_from_cost(cost, P):
    M = P["margins"]
    return max(M["min_price_per_agent"], cost * (1 + M["markup_on_cost"]) / (1 - M["payment_fee"]))


def package_numbers(pkg, human, mult, scenario, P):
    cls = P["model"]["selected_class"]
    n = sum(pkg.values())
    infra = sum(bot_infra(b, human, mult, P)["total"] * c for b, c in pkg.items())
    tokens = sum(bot_tokens(b, cls, human, mult, P) * c for b, c in pkg.items())
    staff_pa, staff_h = staffing_per_agent(scenario, human, P)
    staff = staff_pa * n
    cost = infra + staff + (tokens if P["model"]["include_tokens_in_price"] else 0.0)
    return {"n": n, "infra": infra, "tokens": tokens, "staff": staff, "staff_h": staff_h * n,
            "cost": cost, "price": price_from_cost(cost / n, P) * n}


def hosts_needed(N, human, mult, P):
    """Smallest host count satisfying awake-peak, RAM, wakes and disk limits."""
    S = P["stack"]
    mix = P["company_mix"]
    tot = sum(mix.values())
    counts = {t: N * f / tot for t, f in mix.items()}
    mean_awake = sum(c * awake_hours(P["bots"][t], human, mult, P) / 24 for t, c in counts.items())
    web_share = sum(c * P["bots"][t]["web_tier"] for t, c in counts.items()) / N
    brain_eff = S["brain_gb"] + web_share * S["web_gb"]
    wakes = sum(c * P["bots"][t]["wakes_day"] * (P["human_assist"]["awake_mult"] if human else 1) * mult
                for t, c in counts.items())
    disk_need = sum(c * (P["bots"][t]["live_gb"] + P["bots"][t]["backup_gb"] * S["backup_keep"])
                    for t, c in counts.items())
    usable_disk = (S["host_disk_gb"] - S["host_fixed_disk_gb"]) * (1 - S["disk_headroom"])
    for h in range(1, 10000):
        m = mean_awake / h * S["peak_factor"]
        peak = m + S["peak_z"] * math.sqrt(m)
        ram_free = S["host_ram_gb"] - S["baseline_gb"] - S["reserve_gb"] - (N / h) * S["always_on_gb"]
        ram_cap = max(0, int(ram_free / brain_eff))
        cap = max(1, min(S["max_awake"], ram_cap) * S["correlation_haircut"])
        c_awake, c_wakes = peak <= cap, wakes / h <= S["wakes_per_host_day_limit"]
        c_disk = disk_need / h <= usable_disk
        if c_awake and c_wakes and c_disk and ram_free > 0:
            binding = []
            if peak > 0.8 * cap:
                binding.append("awake")
            if wakes / h > 0.8 * S["wakes_per_host_day_limit"]:
                binding.append("wakes")
            if disk_need / h > 0.8 * usable_disk:
                binding.append("disk")
            if S["max_awake"] > ram_cap:
                binding.append("ram")
            return h, peak, cap, ",".join(binding) or "none", disk_need
    return 10000, 0, 0, "n/a", disk_need


def f(x, w=8, d=2):
    return f"{x:{w}.{d}f}"


def main():
    ap = argparse.ArgumentParser(description="rough cost and price calculator for bridgeai as a service (estimates)")
    ap.add_argument("--params", help="JSON file with overrides (deep merge)")
    ap.add_argument("--template", action="store_true", help="print the full PARAMS as JSON and exit")
    args = ap.parse_args()
    if args.template:
        print(json.dumps(PARAMS, indent=2))
        return
    P = copy.deepcopy(PARAMS)
    if args.params:
        with open(args.params, encoding="utf-8") as fh:
            deep_merge(P, json.load(fh))

    cur = P["region"]["currency"]
    cls_sel = P["model"]["selected_class"]
    hc = host_monthly_cost(P)
    print(f"bridgeai cost calculator - ALL FIGURES ARE ESTIMATES - currency {cur}, per month")
    print(f"host mode {P['region']['host_mode']}, one {P['stack']['host_ram_gb']} GB / "
          f"{P['stack']['host_vcpu']} vCPU / {P['stack']['host_disk_gb']} GB host = {hc:.2f}")
    print(f"token class for package tables: {cls_sel} (tokens in price: {P['model']['include_tokens_in_price']})")

    # ---- 1. per bot type
    print("\n[1] MONTHLY COST PER BOT TYPE (one bot, sleep rule, no human assist)")
    print("    infra = RAM + CPU + disk/backups + GPU + platform share; tokens = what the provider bills;")
    print("    staff = incident + support hours (today / target incident rate)")
    hdr = (f"{'type':19}{'awakeH':>7}{'infra':>8}{'ram':>7}{'cpu':>6}{'disk':>6}{'gpu':>7}"
           f"{'tok chp':>8}{'tok mid':>8}{'tok prem':>9}{'staff now':>10}{'staff tgt':>10}")
    print(hdr)
    sn, _ = staffing_per_agent("today", False, P)
    st, _ = staffing_per_agent("target", False, P)
    for b in P["bots"]:
        i = bot_infra(b, False, 1.0, P)
        print(f"{b:19}{f(i['awake_h'],7,2)}{f(i['total'])}{f(i['ram'],7)}{f(i['cpu'],6)}{f(i['disk'],6)}"
              f"{f(i['gpu'],7)}{f(bot_tokens(b,'cheap',False,1,P),8)}{f(bot_tokens(b,'mid',False,1,P),8)}"
              f"{f(bot_tokens(b,'premium',False,1,P),9)}{f(sn,10)}{f(st,10)}")

    # ---- 2. packages
    print("\n[2] SME PACKAGES (per package per month, before taxes)")
    print("    breakeven = infra + staffing (+ tokens only if include_tokens_in_price; the tokens column is informational)")
    print(f"    {'package':9}{'human':>6}{'scen':>7}{'infra':>8}{'staff':>8}{'tokens':>8}{'breakeven':>10}"
          f"{'BE/agent':>9}{'price/pkg':>10}{'price/agent':>12}{'staff%':>8}")
    notes = []
    for name, pkg in P["packages"].items():
        for human in (False, True):
            for scen in ("today", "target"):
                r = package_numbers(pkg, human, 1.0, scen, P)
                n = r["n"]
                share = 100 * r["staff"] / r["cost"] if r["cost"] else 0
                print(f"    {name:9}{'yes' if human else 'no':>6}{scen:>7}{f(r['infra'])}{f(r['staff'])}"
                      f"{f(r['tokens'])}{f(r['cost'],10)}{f(r['cost']/n,9)}{f(r['price'],10)}"
                      f"{f(r['price']/n,12)}{share:8.0f}")
        n = sum(pkg.values())
        if n > P["human_assist"]["reasonable_agents_without_human"]:
            notes.append(f"{name} ({n} agents): more than {P['human_assist']['reasonable_agents_without_human']} "
                         "autonomous agents without a human is not reasonable; read the 'no' rows as a lower bound on risk")
    for t in notes:
        print("    note:", t)

    # ---- 3. host count at scale
    print("\n[3] HOSTS NEEDED FOR N AGENTS (company mix from PARAMS, awake-peak/RAM/wakes/disk limits)")
    print(f"    mix: " + ", ".join(f"{k} {v:.0%}" for k, v in P["company_mix"].items()))
    print(f"    {'agents':>6}{'human':>6}{'hosts':>6}{'standby':>8}{'peakAwk/host':>13}{'cap/host':>9}"
          f"{'binding':>14}{'host cost':>10}{'gpu':>8}{'infra/agent':>12}{'agents/host':>12}")
    S = P["stack"]
    for N in P["scale_points"]:
        for human in (False, True):
            h, peak, cap, bind, dneed = hosts_needed(N, human, 1.0, P)
            sb = max(1, math.ceil(h * S["ha_standby_fraction"])) if N >= S["ha_enabled_from_agents"] else 0
            mix = P["company_mix"]
            tot = sum(mix.values())
            gpu = sum(N * fr / tot * P["bots"][t]["gpu_h_month"] * (1.0) for t, fr in mix.items()) \
                * P["region"]["gpu_per_hour"]
            cost = (h + sb) * hc + gpu + (h + sb) * S["platform_fixed_per_host_month"]
            print(f"    {N:6d}{'yes' if human else 'no':>6}{h:6d}{sb:8d}{f(peak,13,2)}{f(cap,9,1)}{bind:>14}"
                  f"{f(hc*(h+sb),10,0)}{f(gpu,8,0)}{f(cost/N,12)}{f(N/h,12,1)}")
    print("    note: cap/host already includes the correlation haircut; 'binding' lists limits above 80% use.")
    print("    note: infra/agent here includes standby hosts; compare with the marginal per-type costs in [1].")

    # ---- 4. staffing share
    print("\n[4] STAFFING")
    print("    (4a) variable view, per agent per month (incident hours + support contacts):")
    for scen in ("today", "target"):
        for human in (False, True):
            c, hrs = staffing_per_agent(scen, human, P)
            print(f"        scenario {scen:6} human {'yes' if human else 'no':3}: {c:7.2f} {cur} "
                  f"({hrs:.2f} staff hours/agent/month)")
    print("    (4b) team view, fixed team by scale (do not add to (4a), they overlap):")
    hr = P["region"]["human_hourly"]
    hfte = P["region"]["hours_per_fte_month"]
    print(f"        {'agents':>6}{'FTE':>7}{'team/month':>12}{'team/agent':>12}{'infra/agent':>12}"
          f"{'team share of cost':>20}{'price/agent':>13}")
    for N in P["scale_points"]:
        roles = P["staffing"]["team_fte"].get(str(N))
        if not roles:
            continue
        fte = sum(roles.values())
        team = sum(v * hfte * hr[k] for k, v in roles.items())
        h, _, _, _, _ = hosts_needed(N, False, 1.0, P)
        sb = max(1, math.ceil(h * S["ha_standby_fraction"])) if N >= S["ha_enabled_from_agents"] else 0
        infra_pa = ((h + sb) * (hc + S["platform_fixed_per_host_month"])) / N
        cost_pa = team / N + infra_pa
        print(f"        {N:6d}{fte:7.2f}{team:12.0f}{team/N:12.2f}{infra_pa:12.2f}"
              f"{100*(team/N)/cost_pa:19.0f}%{price_from_cost(cost_pa,P):13.2f}")

    # ---- 5. sensitivity
    print("\n[5] SENSITIVITY: sme_6 with human assist, price per agent (usage x awake hours and tokens)")
    pkg = P["packages"].get("sme_6")
    if pkg:
        for m in P["margins"]["usage_sensitivity"]:
            a = package_numbers(pkg, True, m, "today", P)
            b = package_numbers(pkg, True, m, "target", P)
            print(f"    usage x{m:<4}: infra/agent {a['infra']/a['n']:6.2f}, tokens(cheap class)/agent "
                  f"{a['tokens']/a['n']:6.2f}, price/agent today {a['price']/a['n']:6.2f}, target {b['price']/b['n']:6.2f}")

    print("\nReading guide: replace region costs and token prices with local quotes (--template, --params).")
    print("Per-bot defaults come from a short window on one small host: use them as a starting point.")
    print("Prices are before taxes. The variable staffing view (4a) covers incident and support hours only;")
    print("view (4b) shows the fixed team cost that a price must cover at small scale.")


if __name__ == "__main__":
    sys.exit(main())
