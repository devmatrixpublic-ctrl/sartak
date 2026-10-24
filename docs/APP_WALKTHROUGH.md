# How the app works, in one page

**Signals in (all on the phone):** unknown call or video call, a text from a stranger, an app installed or opened (sideloaded
and remote-access apps are on a watch-list), a payee added, and the payment attempt itself (payee, amount). Message text and
call audio are never read. Phone numbers and UPI IDs are stored only as salted hashes.

**Fusion:** `EventMapper` turns each signal into an event; `Deduplicator` drops repeats; `EventSequencer` puts them in order;
`SessionPolicy` decides what belongs to one scam session. The frozen detector (M2) scores the session. `SplitGuard` runs a
second copy on the running total paid to a new payee in the last hour, so paying in three pieces does not hide it. It can
only add an alarm, never remove one.

**What the person sees:**
- **Hold (alarm):** the payment cannot continue. Stop screen, the reasons, a playbook, call a trusted contact, hold 30 minutes.
- **Nudge:** a dismissible amber banner when a new payee is paid during an unknown call and the amount is at least twice the
  person's usual payment. Capped at one per 30 days (`NudgeLimiter`), so a genuine user stays inside the alert budget.
- **Alert history:** warnings, held payments, folded repeats, nudges this month, and what is stored on the phone.

**Restarts:** `RestartReceiver` restarts protection after a reboot or app update. If Android kills the app mid-scam the
session is rebuilt from the last 3 hours of stored events.

**Privacy:** events are deleted after 24 hours, decisions after 30 days; everything is read from the phone's own storage.

**Where to look:** `events/` (policies and dispatcher), `signals/` (sources), `ui/alerts/` (screens),
`ops/eval/` (offline evaluations: alert budget, split payments, AI variants, rising patterns).
