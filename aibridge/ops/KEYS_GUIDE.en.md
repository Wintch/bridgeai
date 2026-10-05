# How to get your AI keys (guide for new users)

Your assistant **Hermes** needs **its own AI key**. Think of it as a password that lets
Hermes use an artificial-intelligence model on your behalf. **One key is enough.** Start
with the first option and move down the list only if it doesn't work for you: the options
are ordered **from simplest to most involved**, with the **paid** ones at the very end.

> Golden rule: the key is **yours and secret**. Don't share it, and don't send it by
> chat or email. You paste it once on your own keys page (step 2) and that's it.

---

## Step 1 · Get a key

### Free options

#### 1. ⭐ OpenRouter (start here)
- **Cost:** free, no card needed. Has free models (names ending in `:free`) with a daily limit.
- **Where:** <https://openrouter.ai/settings/keys>
- **How:** create an account → **Create Key** → copy it. **Starts with `sk-or-`**.

#### 2. Google Gemini
- **Cost:** free with a small daily quota; enough to try things out.
- **Where:** <https://aistudio.google.com/apikey>
- **How:** sign in with your Google account → **Create API key** → copy it. **Starts with `AIza`**.

#### 3. Hugging Face
- **Cost:** free monthly inference credits.
- **Where:** <https://huggingface.co/settings/tokens>
- **How:** create an account → **New token** (type *Read* is enough) → copy it. **Starts with `hf_`**.

#### 4. NVIDIA NIM (the most generous, but more steps)
- **Cost:** free, no card. About 40 requests per minute.
- **Requirements:** an email address and **your own mobile phone to verify your number** (SMS code).
  If you can't verify a phone number, use one of the options above.
- **Where:** <https://build.nvidia.com/settings/api-keys>
- **How:**
  1. Sign up or log in with your email (you'll be asked to verify the email and to **verify your phone number**: it is mandatory, so keep your phone at hand to receive the SMS code).
  2. Click **Generate API Key** (if it asks for a name, anything works, e.g. `hermes`).
  3. Copy the **whole** key. **Starts with `nvapi-`**. It is shown only once: copy it right away.

| # | Provider | Starts with | Free | Difficulty |
|---|---|---|---|---|
| 1 | OpenRouter | `sk-or-` | `:free` models, daily limit | Very simple |
| 2 | Google Gemini | `AIza` | Small daily quota | Simple |
| 3 | Hugging Face | `hf_` | Monthly credits | Simple |
| 4 | NVIDIA NIM | `nvapi-` | Yes, no card | More steps: requires phone verification |

> If a provider isn't available in your country or won't let you sign up, just take
> the next one on the list: any of them will do.

### Paid options (only if the free ones aren't enough)

Use these if you keep hitting the daily limit of the free options or want more powerful models.
**Add credit yourself and set a spending cap on the provider's website.**

- **OpenRouter with credit:** it's **the same `sk-or-` key** as option 1. Add credit at
  <https://openrouter.ai/settings/credits> and you unlock more models and much higher
  limits. You don't have to change anything in your Hermes.
- Other paid providers (for example OpenAI or Anthropic) **can't be added from the keys
  page**. If you want to use one, ask whoever administers your instance.

---

## Step 2 · Load it into your instance

1. Open your Hermes page (the address we gave you, for example `https://yourname.…`).
2. Log in with the username and password we gave you.
3. Open **"Cargar mis claves"** (Spanish for "Load my keys"): it's `/keys/` on the same address.
4. Pick the provider, **paste the key** and click save.
   It is checked immediately against the provider and **only saved once it passes**.
5. **Choose the model** on that same page and go back to the chat. You can change it any time.
   With OpenRouter, Gemini and Hugging Face you have to choose the model yourself (NVIDIA comes with one preselected).

### If the page rejects your key
- Check that you copied it **completely**, with **no spaces** at the start or the end.
- Check that it starts as shown in the table above.
- If it says the provider is **rate-limiting** you (error 429), wait a minute and try again.
- If the key expired or you revoked it, generate a new one and repeat step 2.

---

## Job search (if your instance includes it)

The job-search system uses **the same key** you loaded above: you don't need another one.
Hermes will only ask for **your CV** (attach it in the chat as a PDF) and a few profile
details. Ask things like *"let's look for a job as …"* or *"make me a CV as a PDF"*.

---

## Taking care of your key

- It's **yours**: usage counts against **your** quota, not someone else's.
- If you suspect someone saw it, **revoke it** on the provider's website (same link as in
  step 1) and generate a new one.
- Your key and your files stay **only in your instance**.
