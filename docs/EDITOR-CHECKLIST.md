# Bubble Plugin Editor checklist

The remaining fixes from [`REVIEW.md`](REVIEW.md), ordered by ascending risk.

**Almost everything here has to be done in the Bubble Plugin Editor, not in this repo.** Adding a
parameter requires a new ID from Bubble's `AAg`, `AAh`, … counter, and that counter lives on
Bubble's servers — it cannot be derived from these files. Hand-picking an ID risks silently
colliding with the next one Bubble hands out, and nothing in the repo would catch it.

## Why the repo is the wrong place to edit

Bubble's GitHub sync is bidirectional but asymmetric. If the repo changed and Bubble's copy did
not, a pull picks up your version. If **both** changed, **Bubble's copy wins** — your version is
discarded and Bubble opens a PR back at you instead.

So Bubble is the source of truth. Use git as the *output* channel: make each change in the editor,
push, and review the diff. That diff is your proof the editor did what you meant and nothing else.

There is also a long-standing report of the plugin's **General tab being wiped by a GitHub pull**.
It dates from 2019 and may well be fixed, but the failure mode is silently blanking your
marketplace listing. That is why `meta_data.json` and `shared_tech_params.json` are left untouched
in this repo and appear as step 6 below instead.

## Before you start

1. **Publish the current state as a plugin version.** Bubble's versioning — not git — is your real
   rollback. Git cannot restore Bubble's server-side copy.
2. **Push Bubble → GitHub and confirm the commit is empty.** If it produces a diff, there is
   pre-existing drift and every step below is unsafe until you reconcile it.
3. **Set up a sandbox.** Recreate the three calls in a throwaway Bubble app's API Connector with
   your Plivo credentials. It is free, instant, has no published consumers, and answers every
   uncertain HTTP question below without touching the plugin. This is the single best safety
   measure here.

## Live tests worth running first

`plivo.com` was unreachable from the review environment, so every claim about Plivo's API contract
in `REVIEW.md` is from prior knowledge and needs confirming. Run these in the sandbox:

| Question | How | Cost |
|---|---|---|
| **What does Bubble actually POST?** Content-Type, and how `media_urls` is encoded | Clone Send Message pointing at a `webhook.site` URL, initialize, read the raw body | free |
| Does comma-separated `media_urls` actually deliver? | Send a real MMS with 1 URL, then 2 | billed |
| Does Bubble parse `2024-09-03 13:18:04.899216-07:00` as a date? | Display `message_time:formatted as` | free |
| Does `mnc` really lose its leading zero? | Find a message on a network with MNC `01`; confirm you get `1` | free |
| Do the List filters behave (esp. the `limit` cap and `message_time__gt` format)? | Sandbox GETs with each parameter | free |
| What is the WhatsApp `template` body shape? | Sandbox, against a real WABA | needs WABA |

The first one is the highest-value test in this document — it settles findings H1 and M3 at zero
cost and zero risk.

## The changes

Push to GitHub and review the diff after **every** step. Run
`python3 tools/validate_raw_calls.py` on each result.

| # | Change | Finding | Impact |
|---|---|---|---|
| 1 | Trailing slash on `Retrieve a Message`'s URL | — | Already applied in this repo; pull it, or redo it in the editor |
| 2 | Correct the `doc` strings — `media_urls` format, `type` allowed values | H1 | patch, non-breaking |
| 3 | Add optional query params to **List all messages**: `limit`, `offset`, `subaccount`, `message_state`, `message_direction`, `message_time__gt` | M1 | minor, additive |
| 4 | Add optional `url`, `method`, `log`, `trackable` to **Send Message** | M3 | minor, additive |
| 5 | Add `powerpack_uuid`; mark `src` optional (they are mutually exclusive) | M3 | minor |
| 6 | **General tab, one sitting:** rewrite the description (drop the voice/phone-call claims), rewrite the instructions (add the `auth_id` step, fix `6.Use`, point at Account → Keys & Credentials), set `use_jquery` to false | M5, M6, L3 | listing update |
| 7 | `mcc` and `mnc` → `text`, in **both** `AAc.objects` and `AAe` | H2 | **breaking** — own version bump |
| 8 | New **Send WhatsApp Template Message** call (raw `body` + `body_params` + `body_type: "json"`) | M2 | minor, additive; most editor work |
| 9 | `media_urls` as an array — **only if step-0 testing proves the current form broken**, and then as a separate **Send MMS** call | H1 | minor if additive, major if it mutates Send Message |
| 10 | `wrap_error` → true on both data calls | M4 | **breaking, wide blast radius — recommend against** without a major version |

Steps 1–6 can ship together as one version. Step 7 forces its own. Steps 8–10 are separate projects.

## Notes on individual steps

**Step 3 and 4 — parameter shape.** Copy an existing optional parameter exactly rather than
inventing one. The canonical form is `optional: true`, `private: true`, `value: ""`. Optional
parameters left blank are omitted from the request, which is what you want — keep both calls in
key/value `params` mode to preserve that.

**Step 4 — this one bills you.** `Send Message` has `should_reinitialize: true`, so reinitializing
it dispatches a real message. Use a number you own.

**Step 7 — do both, or neither.** `AAc.objects` and `AAe` describe the same Plivo Message object and
currently agree on every shared field's type. Fixing one and not the other introduces drift;
`tools/validate_raw_calls.py` will fail if you do.

**Step 8 — why a new call, not a parameter.** A nested `template` object needs raw-body mode, and
raw-body mode has no way to omit a blank key — a blank `<text>` emits `""` rather than being
dropped. Putting it on the existing call would break optionality for every other parameter. Other
published plugins solve this the same way, by shipping one call per body shape.

**Step 10 — what actually breaks.** With wrapping on, fields gain a `body` prefix in their `path`
(compare `Send Message`, which already has it: `path: ["body", "api_id"]`). Every field key and
path in the affected schema changes, so every expression in every consuming app breaks. If you do
it, do both calls at once and ship migration notes.

## If you must hand-edit this repo instead

Realistically only steps 1 and 7 are candidates — neither needs a new ID. The protocol:

1. Branch from a commit where Bubble and the repo are known-identical.
2. Edit with a **script**, never a text editor. Bubble's exact serialization is
   `json.dumps(obj, sort_keys=True, indent=4, ensure_ascii=False)` with **no trailing newline**.
   Anything else produces a whole-file diff, which is precisely the both-sides-modified state where
   your change loses.
3. `python3 tools/validate_raw_calls.py` — require a clean pass.
4. Confirm the diff touches only the intended lines.
5. Merge and **pull into Bubble immediately**, to minimize the divergence window.
6. Verify in the editor UI, push back, confirm an empty diff.
7. **Never include `meta_data.json` or `shared_tech_params.json` in a pull.**
