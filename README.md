# Plivo — Messaging (SMS / MMS / WhatsApp)

A [Bubble](https://bubble.io) plugin for sending and reading messages through
[Plivo](https://www.plivo.com/).

**Messaging only.** Despite what Plivo's platform offers, this plugin exposes no voice or
call-handling functionality — there are three messaging API calls and nothing else.

| What you get | Type |
|---|---|
| Send Message — SMS, MMS, or freeform WhatsApp | Workflow action |
| List all messages | Data source |
| Retrieve a Message | Data source |

## Setup

1. Create an account at [plivo.com](https://www.plivo.com/) and buy a phone number.
2. Open **Account → Keys & Credentials** in the Plivo console.
3. In the plugin's settings, fill in **three** fields:
   - **username** → your Plivo **Auth ID**
   - **password** → your Plivo **Auth Token**
   - **`auth_id`** → your Plivo **Auth ID again**

   The third is easy to miss and nothing works without it — the Auth ID is used both as the Basic
   Auth username and inside the request path.
4. Drop the **Send Message** action into a workflow.

Full field-by-field docs: [`docs/USAGE.md`](docs/USAGE.md).

## Before you ship

Read [`docs/KNOWN-ISSUES.md`](docs/KNOWN-ISSUES.md). The short version:

- **WhatsApp is freeform-only** — no message templates, so you cannot start a conversation, only
  continue one inside the 24-hour window.
- **MMS needs testing** before you rely on it.
- **List all messages returns at most 20 records** with no paging or filtering.
- **The two data sources hard-error** on any Plivo failure instead of returning a catchable error.
- **`mnc` and `mcc` lose leading zeros** (`01` becomes `1`).

## Documentation

| | |
|---|---|
| [`docs/USAGE.md`](docs/USAGE.md) | Setup and per-call reference |
| [`docs/REVIEW.md`](docs/REVIEW.md) | Full audit — findings, evidence, and fixes |
| [`docs/KNOWN-ISSUES.md`](docs/KNOWN-ISSUES.md) | Current limitations and workarounds |
| [`docs/EDITOR-CHECKLIST.md`](docs/EDITOR-CHECKLIST.md) | Ordered backlog for the plugin owner |

## Contributing

> [!IMPORTANT]
> **This repository is a mirror. Bubble's servers hold the source of truth.**
>
> `api/raw_calls.json`, `meta_data.json` and `shared_tech_params.json` are written by Bubble's
> GitHub sync. If both the repo and the Bubble copy change, **Bubble's copy wins** and your edits
> are discarded.
>
> Make plugin changes in the Bubble Plugin Editor and push them here — don't hand-edit those files.
> See [`docs/EDITOR-CHECKLIST.md`](docs/EDITOR-CHECKLIST.md) for the full rationale and the
> protocol for the rare cases where a direct edit is justified.

Everything under `docs/` and `tools/` is ordinary repo content that Bubble never reads, and can be
edited freely.

Before opening a PR that touches the JSON:

```bash
python3 tools/validate_raw_calls.py
```

It checks that the files still match Bubble's exact serialization, that type references resolve,
that URL placeholders line up with declared parameters, that parameter IDs don't collide, and that
the two message-object schemas haven't drifted apart. Warnings are the known issues above; errors
mean something is structurally wrong.

## Support

https://i2b.co/support

## License

MIT — see [`LICENSE`](LICENSE).
