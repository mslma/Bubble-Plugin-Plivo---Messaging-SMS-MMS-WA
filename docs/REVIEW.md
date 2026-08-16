# Plugin review — Plivo Messaging (SMS / MMS / WhatsApp)

Review of the plugin as it stands at commit `f9572c4`.

## Scope

This plugin contains **no JavaScript**. There are no elements, no server-side actions, no
`initialize`/`update`/`preview` functions, no build or test tooling — and there never have been
(`git log --all --diff-filter=A` shows the same five files across a single commit). It is built
entirely from Bubble's declarative API Connector tab, so everything it does lives in
`api/raw_calls.json`.

This is therefore an **API-contract and configuration review**, not a code review.

### What the plugin exposes

Auth is HTTP Basic (`"auth": "basic_auth"`) — Plivo Auth ID as username, Auth Token as password —
plus a separate `auth_id` URL parameter (ID `AAV`) reused by all three calls.

| ID | Name | Method | Bubble surface | `wrap_error` | Parameters |
|---|---|---|---|---|---|
| `AAU` | Send Message | POST | Action | `true` | `src`, `dst`, `text`, `type` (default `sms`), `media_urls` (optional) |
| `AAc` | List all messages | GET | Data source | `false` | **none** |
| `AAe` | Retrieve a Message | GET | Data source | `false` | none (URL: `auth_id`, `message_uuid`) |

### Severity key

**High** — wrong or lost data, or a documented capability that does not work.
**Medium** — a real limitation users will hit.
**Low** — cosmetic, or correct-but-untidy.

---

## High

### H1. `media_urls` is a comma-separated string; Plivo expects a JSON array

`api/raw_calls.json` documents the parameter as *"A comma-separated list of URL-encoded hyperlinks
to the images or media"*. Plivo's Send Message API takes `media_urls` as an **array**:

```json
{ "src": "…", "dst": "…", "type": "mms", "media_urls": ["https://example.com/a.jpg"] }
```

A key/value `params` call in the API Connector can only emit flat string values, so as configured
the plugin cannot produce an array at all.

**Before changing anything, establish what Bubble actually sends.** Clone Send Message in a
throwaway Bubble app, point it at a `webhook.site` URL, initialize, and read the raw body and
`Content-Type`. That one test costs nothing and settles this finding outright:

- If Plivo accepts the current encoding, this is a **documentation fix** — correct the `doc`
  string and move on.
- If it does not, **add a separate "Send MMS" call** using raw-body mode
  (`body` + `body_params` + `body_type: "json"`). Do **not** convert Send Message itself: raw-body
  mode has no way to omit a blank key, so `<text>` and every other optional parameter would start
  emitting `""` instead of being dropped from the request.

A UX note either way: making app builders hand-type `["https://a.png","https://b.png"]` into a
Bubble text input is worse than comma-separated. If an array is required, the cleanest shape is a
dedicated call whose `body` template joins a single URL, plus documented guidance for the
multi-attachment case.

### H2. `mcc` and `mnc` are typed `number`, but they are identifiers

Both `plugin_api.AAc.objects` and `plugin_api.AAe` declare:

```json
"_p_mnc": { "ret_btype": "number", "sample_value": "650" }
"_p_mcc": { "ret_btype": "number", "sample_value": "312" }
```

Plivo returns these as strings. Mobile Network Codes are commonly two digits **with a leading
zero** (`"01"`, `"03"`), and coercing them to a number silently rewrites `"01"` as `1`. These are
opaque identifiers, not quantities — nobody does arithmetic on an MNC.

**Fix:** change both to `text`. Apply to **both** type definitions; fixing only one introduces
schema drift between two calls that currently agree perfectly (`tools/validate_raw_calls.py`
enforces that parity). This is a **breaking** change for any app already reading these fields, so
it belongs in its own version bump with a migration note.

---

## Medium

### M1. `List all messages` accepts no parameters at all

`AAc` declares no `params` key whatsoever — no `limit`, `offset`, `subaccount`, `message_state`,
`message_direction`, `message_time__gt`, or `error_code`. Plivo defaults to returning 20 records,
so **the data source can only ever read the 20 most recent messages**, with no way to page back
through history or filter server-side.

The call's own return schema makes this worse by advertising `meta.limit`, `meta.offset`,
`meta.next` and `meta.previous` — pagination metadata it gives the app builder no means to act on.

**Fix:** add the parameters as optional (`"optional": true, "value": ""`) so blank inputs are
omitted from the request. Purely additive; the response schema does not change, so no
reinitialization is needed.

### M2. "WA" is in the plugin name, but there is no `template` parameter

The plugin supports `type: whatsapp` with freeform `text`, and nothing else. WhatsApp only permits
freeform messages inside an active 24-hour customer-service window — the plugin's own parameter
documentation says as much: *"If no conversation is ongoing, such messages will fail with error
340."*

Business-initiated WhatsApp — the majority of real usage — **requires** a templated message, which
means a nested `template` object (`name`, `language`, `components`). That cannot be expressed in
key/value `params` mode.

**Fix:** add a separate **Send WhatsApp Template Message** call in raw-body mode. This is the most
editor-intensive item in the backlog: it needs a new call ID and a return-type schema that only
Bubble can generate by initializing against the live API.

### M3. No delivery-status callback

Plivo's `url` and `method` parameters let you register a webhook that receives message status
updates. Neither is exposed, so the only way a Bubble app can learn whether a message was delivered
is to poll `Retrieve a Message`.

Adding `url`/`method` would let apps point at a Bubble backend workflow endpoint and get delivery
receipts pushed to them. Also absent: `log`, `trackable`, and `powerpack_uuid` (the last is mutually
exclusive with `src`, so exposing it means marking `src` optional).

⚠️ `AAU` carries `should_reinitialize: true`. **Reinitializing Send Message dispatches a real,
billable message** — use a number you own.

### M4. Both data sources have error wrapping off

`AAc` and `AAe` set `wrap_error: false`, so a Plivo `401`, `404` or `429` raises a hard error in
the app rather than something the builder can branch on. Only `Send Message` has `wrap_error: true`.

**This is real, but it is not a quick fix.** Compare `AAU`, where wrapping is on: its fields carry
`path: ["body", "api_id"]`. Turning the flag on **re-nests the entire response under `body`**,
changing every `path` and every field key in the affected `types` blob. Every expression in every
consuming app breaks.

**Recommendation:** document the current failure behaviour now (see `KNOWN-ISSUES.md`); defer the
flag itself to a major version with migration notes, and change both calls together if you do it.

### M5. Setup instructions omit the `auth_id` step

`meta_data.json` walks the user through pasting the Auth ID into the username field and the Auth
Token into the password field — and stops. But `auth_id` is a **separate URL parameter** that also
has to be populated. If it is left blank, every request goes to `/v1/Account//Message/`.

Two smaller problems in the same text: the typo `6.Use` (missing space), and the instruction to
find credentials under *Messaging → Overview* when they live under Account → Keys & Credentials.

### M6. The marketplace description claims capabilities the plugin does not have

> "…enables businesses to embed **voice and SMS** capabilities… you can easily **manage phone
> calls**, send SMS messages…"

There is no Voice API call anywhere in `raw_calls.json`. The description is accurate about *Plivo
the platform* and inaccurate about *this plugin*, which does messaging only. That is a listing
accuracy problem, and a predictable source of support tickets and refund requests.

---

## Low

### L1. Date fields sample as space-separated timestamps

All six `message_time` / `message_sent_time` / `message_updated_time` fields are typed `date` with
samples like `2024-09-03 13:18:04.899216-07:00` — space-separated with microseconds, not ISO-8601
`T`. Whether Bubble's date parser accepts this format is **unverified**. Worth one live test
(display `message_time:formatted as` in a test app); if it fails, the fields need to be `text` with
parsing done app-side.

### L2. `log` is typed `boolean` with the string sample `"true"`

The type is right — Plivo returns a real boolean. Only the `sample_value` is an initialization
artifact. `sample_value` is editor-display only with no runtime effect, so this is the lowest
priority item here.

### L3. `use_jquery: true` with zero client-side code

`shared_tech_params.json` declares a jQuery dependency for a plugin that ships no browser code.
Harmless in practice (most Bubble apps load jQuery anyway), but it should be `false`.

### L4. `README.md` was boilerplate

The original README described GitHub sync mechanics and included the copy-paste error *"lets you
use Github's functionality"* in a Plivo plugin. There were no usage docs anywhere in the repo.
Addressed in this change.

---

## Examined and explicitly *not* problems

Recording these so they don't get "fixed" later.

### Decimal money fields typed `number`

`total_amount`, `total_rate`, `carrier_fees` and `carrier_fees_rate` are `number` with string
samples (`"0.00850"`). Unlike `mcc`/`mnc` (H2), **this is correct.** These are genuine numeric
quantities, Bubble's coercion is lossless, and converting them to `text` would force every user to
append `:converted to number` before summing costs. That would be a regression dressed as a fix.

### `private: true` on `src`, `dst`, `text`

At first glance this looks like it would freeze the values at configuration time. It does not — in
plugin API calls this flag keeps the value off the client, and it is the normal shape for
user-facing plugin parameters. Cross-checked against other published Bubble plugin mirrors, where
obviously per-call fields (`email`, `amount`) carry the same flag. Leave as-is.

### The stray `"0": "A"`, `"1": "A"`, `"2": "b"` keys

Present in `AAc` and `AAe`. These are Bubble serializing a string as an index-keyed object — in
each case the call ID immediately preceding the call's own (`AAb` before `AAc`, `AAd` before
`AAe`). The same artifact appears in unrelated plugin mirrors. Benign; leave byte-identical.

### The trailing-slash fix (now applied)

`AAe`'s URL was missing the trailing slash the other two calls have. Worth noting this was
**robustness, not an outage**: the call is marked `initialized: true`, so the slash-less form
demonstrably returned data. Plivo's API is Tastypie/Django-shaped (note the
`meta.limit`/`offset`/`next`/`previous` envelope), so it almost certainly `APPEND_SLASH`
301-redirects and Bubble follows the redirect. The fix removes a wasted round-trip and the
fragility of depending on redirect behaviour.

---

## Verification status

Everything asserted about `raw_calls.json` above was checked mechanically —
`tools/validate_raw_calls.py` reproduces the type mismatches, confirms schema parity between the
two message-object definitions, and verifies the URL-placeholder bijection.

Every claim about **Plivo's API contract** is from prior knowledge and could not be verified during
this review — `plivo.com` is unreachable from the review environment. Re-check H1, M1, M2 and M3
against the current Plivo docs before implementing. `docs/EDITOR-CHECKLIST.md` lists the live tests
worth running first.
