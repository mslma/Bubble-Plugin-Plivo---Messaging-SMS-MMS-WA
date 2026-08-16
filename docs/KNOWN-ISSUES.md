# Known issues

Current, unfixed behaviour that app builders will hit. Full analysis in [`REVIEW.md`](REVIEW.md).

Run `python3 tools/validate_raw_calls.py` to reproduce the schema findings.

## `mnc` and `mcc` lose leading zeros

Both are declared `ret_btype: "number"` in `plugin_api.AAc.objects` and `plugin_api.AAe`, but Plivo
returns them as strings. Mobile Network Codes are frequently two digits with a leading zero, so
`"01"` is coerced to `1`.

**Workaround:** none within the plugin — the coercion happens before your expression sees the
value. If you need exact network codes, read them from Plivo's API directly via the API Connector
until this is fixed.

**Fix:** retype both to `text`, in both definitions. Breaking; needs a version bump.

## Both data sources hard-error on API failures

`List all messages` and `Retrieve a Message` have `wrap_error: false`. Any non-2xx from Plivo — bad
credentials, unknown UUID, rate limit — surfaces as a hard error rather than a value you can branch
on. Only `Send Message` returns `returned_an_error`.

**Workaround:** don't drive user-facing pages directly off these data sources without a fallback,
and validate `message_uuid` before using it.

Switching the flag on is a breaking change (it re-nests the whole response under `body`), so it is
deferred to a major version.

## MMS may not send

`media_urls` is configured as a plain string but Plivo's API expects an array. Whether the current
encoding works depends on how Bubble serializes the request body, which has not been verified.

**Test before relying on MMS in production.** See H1 in [`REVIEW.md`](REVIEW.md) for a zero-cost way
to check what Bubble actually sends.

## WhatsApp is freeform-only

No `template` parameter exists, so you can only message users inside an active 24-hour window.
Business-initiated WhatsApp messages will fail with error 340.

## `List all messages` is capped at 20 records

No `limit`, `offset` or filter parameters are exposed, so you get Plivo's default page and nothing
else. There is no way to reach older messages through the plugin.

## Date parsing is unverified

The six timestamp fields are typed `date` with samples like `2024-09-03 13:18:04.899216-07:00` —
space-separated rather than ISO-8601. Whether Bubble parses this reliably has not been tested. If
you see empty or wrong dates, this is the likely cause.

## The marketplace description overstates scope

It mentions voice and phone calls. This plugin does messaging only.

---

## Not bugs

Recorded so they don't get "fixed" into regressions.

**`total_amount`, `total_rate`, `carrier_fees`, `carrier_fees_rate` are `number` with string
samples.** This is correct and deliberate. They are real numeric quantities, Bubble's coercion is
lossless, and retyping them to `text` would force `:converted to number` on every cost calculation.

**`log` is `boolean` with the string sample `"true"`.** The type is right; only the sample is an
initialization artifact, and samples have no runtime effect.

**Every parameter has `private: true`.** This keeps values off the client. It does not freeze them
at configuration time — they remain per-call inputs.

**`"0": "A"`, `"1": "A"`, `"2": "b"` in `AAc` and `AAe`.** A Bubble serialization artifact (a string
written as an index-keyed object). Harmless; leave byte-identical.
