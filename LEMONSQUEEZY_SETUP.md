# Lemon Squeezy Setup — Scribe Dictation Pro

Prep doc for creating the seller account and product. I (Claude) can't create the
account itself — it needs your identity/bank/tax info — but everything else below
is drafted so signup is fast.

## 1. Account creation (you do this)
- Sign up at lemonsqueezy.com as a "Store" (merchant of record — they handle sales
  tax/VAT globally, which is why it's a better fit than raw Stripe for a solo indie
  app).
- You'll need: legal name, address, bank account or payout method (or PayPal), tax
  ID if you have a registered business (a sole prop / your SSN works if not).
- Verification can take 1-2 business days — do this early, before the domain/store
  page is finished.

## 2. Store config
- Store name: **Scribe Dictation**
- Store URL slug: `scribe-dictation` (or your custom domain once DNS is pointed —
  Lemon Squeezy supports custom domains on paid-ish tiers, check current pricing)
- Currency: USD

## 3. Product setup
- Product name: **Scribe Dictation Pro**
- Type: **License key** product (Lemon Squeezy has this as a built-in product type
  — it auto-generates and validates keys via their API, which is exactly what
  `scribe_dictation/licensing.py` already calls against
  `https://api.lemonsqueezy.com/v1/licenses/activate`)
- Price: **$19** one-time (matches the hardcoded price already shown in the app's
  activation dialog — `scribe_dictation/ui/activation.py`)
- License activation limit: 1-3 machines per key (your call — 1 is stricter, 3 is
  more generous for people with a desktop+laptop)
- Delivery: license key only (no file download needed — the app itself is
  distributed separately via your domain/GitHub releases, not through Lemon
  Squeezy's file delivery)

## 4. Product description draft
> **Scribe Dictation Pro**
> Cross-platform desktop dictation. Hold a hotkey, speak, get text pasted wherever
> your cursor is — offline via faster-whisper or online via OpenAI Whisper, your
> choice. No subscription, no cloud lock-in: one license, yours forever.
>
> - Global hotkey (Ctrl+Win), hold-to-talk or tap-to-toggle
> - Offline transcription (faster-whisper, GPU-accelerated if you have CUDA) or
>   online (OpenAI Whisper API) — switch anytime
> - Auto-paste into the active window
> - System tray background operation
> - Windows, macOS, Linux

## 5. After signup — things I still need from you to finish the code side
- **Store slug / product permalink** once created, to replace the placeholder
  `PRODUCT_ID = "scribe-dictation-pro"` in `scribe_dictation/licensing.py`
- **Real checkout URL** to replace the placeholder in
  `scribe_dictation/ui/activation.py`'s `_open_buy_page()` (currently just links to
  `https://lemonsqueezy.com`, not a real product page)
- Whether you want webhook-based license provisioning (Lemon Squeezy emits a
  webhook on purchase) — not required for the current "manual key entry + online
  verify" flow already built, but worth it later for auto-email delivery

## 6. Domain / no-fee alternative
Once you tell me which domain to use, the plan is: a simple static landing page
(product description + "Buy" button linking to the Lemon Squeezy checkout, or a
direct download link once purchased) hosted on that domain — no extra platform fee
beyond Lemon Squeezy's own cut (they take a %, there's no way around that if they're
acting as merchant of record, but it avoids stacking a second platform's fee like
Gumroad + a separate site would).
