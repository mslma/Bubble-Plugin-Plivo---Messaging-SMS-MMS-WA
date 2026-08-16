# Using the plugin

This plugin sends and reads **messages** through Plivo — SMS, MMS and WhatsApp. It does not do
voice; there are no call-related API calls in it.

## Setup

You need a Plivo account with a purchased phone number. Credentials live in the Plivo console
under **Account → Keys & Credentials**.

There are **three** values to fill in, not two:

| Where | Value |
|---|---|
| Plugin settings → username | Your Plivo **Auth ID** (starts `MA…` / `SA…`) |
| Plugin settings → password | Your Plivo **Auth Token** |
| The `auth_id` parameter | Your Plivo **Auth ID again** |

The third one is easy to miss. The Auth ID is used twice: once as the HTTP Basic username, and
again inside the request path (`/v1/Account/{auth_id}/Message/`). If `auth_id` is left blank every
request goes to `/v1/Account//Message/` and fails.

## Send Message (action)

Use in any workflow. Runs server-side.

| Field | Required | Notes |
|---|---|---|
| `src` | yes | Sender ID — a phone number, short code, or alphanumeric sender. For WhatsApp, the number tied to your WhatsApp Business Account. |
| `dst` | yes | Recipient. Plivo strips `/ - . + ( )` and whitespace automatically. Multiple recipients are separated by `<`. |
| `text` | yes | Message body. |
| `type` | yes | `sms`, `mms`, or `whatsapp`. Defaults to `sms`. |
| `media_urls` | no | Media to attach. Required when `type` is `mms`. See the caveat below. |

**Length limits.** GSM 03.38 7-bit messages: up to 1,600 characters, split into 153-character
units past the first 160. Messages containing any UCS-2 character: up to 737 characters, split into
67-character units past the first 70. Multi-unit messages are stitched back together by carriers
that support concatenation. WhatsApp freeform text: 4,096 characters, or 1,024 when sent as a media
caption.

**Returns** `body message_uuid` (a **list** of text — use `:first item` for a single recipient),
`body api_id`, `body message`, and, because error wrapping is on for this call,
`returned_an_error` plus `error status_code` / `error status_message` / `error body`. Branch on
`returned_an_error` rather than letting failures surface as workflow errors.

### MMS caveat

The `media_urls` parameter is documented as comma-separated, but Plivo's API expects a JSON array.
Test your specific case before relying on it — see H1 in [`REVIEW.md`](REVIEW.md). Limits: up to 10
attachments, 5 MB total including body text. `gif`, `png` and `jpeg` are transcoded for device
compatibility; other types (audio, video, vCard) are passed through unoptimized. Attachment
ordering is best-effort, not guaranteed.

### WhatsApp caveat

Only **freeform** WhatsApp messages are supported. WhatsApp permits those only inside an active
24-hour customer-service window; outside it they fail with error 340. Business-initiated
conversations require a templated message, which this plugin cannot currently send — see M2 in
[`REVIEW.md`](REVIEW.md).

## List all messages (data source)

Returns your account's messages, newest first.

**It takes no parameters**, so it returns Plivo's default page — the 20 most recent messages — and
there is no way to page or filter. The `meta limit` / `meta offset` / `meta next` fields in the
response are informational only; nothing consumes them. If you need history or filtering, see M1 in
[`REVIEW.md`](REVIEW.md).

Each item in `objects` carries the message-detail fields listed below.

## Retrieve a Message (data source)

Takes a `message_uuid` — the value you got back from Send Message — and returns one message.

Useful fields: `message_state` (`queued`, `sent`, `delivered`, `undelivered`, `failed`),
`error_code` and `error_message`, `total_amount` and `units` for cost, `from_number` / `to_number`,
and the three timestamps.

Since there is no delivery-status webhook (M3), polling this call is currently the only way to
learn a message's final state.

## Error handling

`Send Message` wraps errors: check `returned_an_error` and read `error status_code`.

The two **data sources do not**. A Plivo `401` (bad credentials), `404` (unknown UUID) or `429`
(rate limited) raises a hard error in the app instead of something you can branch on. Treat these
data sources as trusted-input only, and don't drive user-facing pages directly off them without a
fallback. See M4 in [`REVIEW.md`](REVIEW.md) for why this isn't simply switched on.

## Known data-type gotchas

`mnc` and `mcc` are typed as numbers, so a network code like `01` comes back as `1`. Full list in
[`KNOWN-ISSUES.md`](KNOWN-ISSUES.md).
