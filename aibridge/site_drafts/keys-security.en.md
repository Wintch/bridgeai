<!-- Draft for the public website, keys section. For operator review; not yet in the site repo.
     Items marked "(planned)" must stay labelled until they are live. -->

# Your keys are yours

**The account and the key are yours.** You create your account with each AI provider (NVIDIA, OpenRouter, Gemini, Groq...),
accept its terms, and paste your own key into your own assistant. Whether what you do with that key counts as testing or
production is set by the provider's terms: it is between you and them.

**We provide the software and the place it runs, not the keys.** We don't give you keys, we don't resell them, and nobody
pays us for model access. Our rule is that a key is never shared across accounts. (Some older setups started on a temporary
shared trial key; that is being phased out, and if yours did, the welcome message says so.)

## What we do

- You paste the key only on **your own keys page**, never in the chat. **We never ask for it** in a chat, an email or a
  message.
- It is **checked with the provider when you paste it**, and from then on the keys page only shows the **last 4 characters**.
- That copy lives in your instance, so the assistant can call the provider for you. Our own checks also use it to see that
  it still works.
- We are working to keep keys out of backups, logs and exports, and to make sure no account uses another's key (see
  "Where we are heading"). Each point is checked with tests before we claim it.

## What we ask of you

- **Set a spending limit** at the provider before you paste a paid key, an amount you can afford to lose, and turn on a
  usage alert. It is the protection that still works if something fails on our side.
- **One key per app or bot.** Don't reuse one you use elsewhere.
- **Revoke it and make a new one** if you suspect a leak, or if you pasted it in a chat by mistake.
- **Tell us**, so we check our side too.

## The limits, plainly

To call the provider, a running service has to hold the key in memory. Today the working copy of your key is in your
instance, and whoever administers the server can technically read it, as can the assistant's own process. The server's daily
backups also hold a copy for a few days. That is why the
provider's spending cap and quick revocation are your real safety net, more than any promise of ours.

## Where we are heading

A leaked key is one of the worst things that can happen: it can be used for anything and, with paid providers, burn real
money. So the direction is that the key stays on the client's side and that we are never the ones who leak it:

1. **First (planned, small steps):** usage alerts and spending ceilings, backups without keys, no fallback to anyone else's
   key, and a check that no two accounts share a key.
2. **Next (planned):** the assistant no longer holds the key in its own container: a separate component stores it, calls the
   provider for it and enforces the ceiling. Encrypted on disk.
3. **Later (planned):** an option to keep the key encrypted with a passphrase only you hold, and alerts on unusual use. The
   secure way to load and keep keys is still to be designed; we will publish it once it is defined.

If you suspect a key leaked: revoke it at the provider first, then load the new one and write to us.
