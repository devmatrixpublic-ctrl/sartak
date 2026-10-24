# Verification record for `google_attestation_roots.pem`

Prepared 2026-10-24 by M4 (with a coding agent). **Status: prepared, not yet signed off by a person.** The last step below is yours.

## What the file contains

Exactly four roots, all self-signed CA certificates, none expired:

| SHA-256 of the DER | Key | Valid until | In Google's API | On Google's docs page |
|---|---|---|---|---|
| `CE:DB:1C:B6:DC:89:6A:E5:EC:79:73:48:BC:E9:28:67:53:C2:B3:8E:E7:1C:E0:FB:E3:4A:9A:12:48:80:0D:FC` | RSA 4096 | 2042-03-15 | yes | yes |
| `6D:9D:B4:CE:6C:5C:0B:29:31:66:D0:89:86:E0:57:74:A8:77:6C:EB:52:5D:9E:43:29:52:0D:E1:2B:A4:BC:C0` | EC P-384 ("Key Attestation CA1") | 2035-07-15 | yes | yes |
| `1E:F1:A0:4B:8B:A5:8A:B9:45:89:AC:49:8C:89:82:A7:83:F2:4E:A7:30:7E:01:59:A0:C3:A7:3B:37:7D:87:CC` | RSA 4096 | 2034-11-18 | **no** | yes |
| `AB:66:41:17:8A:36:E1:79:AA:0C:1C:DD:DF:9A:16:EB:45:FA:20:94:3E:2B:8C:D7:C7:C0:5C:26:CF:8B:48:7A` | RSA 4096 | 2036-11-13 | **no** | yes |

**Excluded on purpose:** `C1:98:4A:3E:F4:5C:1E:2A:91:85:51:DE:10:60:3C:86:F7:05:1B:22:49:C4:89:1C:AE:32:30:EA:BD:0C:97:D5`, which expired on 2026-05-24.

## The decision that was made, and how to undo it

The two roots marked "docs page only" are **included**. Reason: Google's documentation page is the list Google publishes for app developers,
and leaving them out would reject any phone whose attestation chain ends at one of them. The cost is trusting two more roots that Google
publishes in one place and not the other. **If you would rather pin only the two that both sources agree on**, delete the last two
certificates from the file (the SHA-256 values above identify them) and delete the matching rows from this table. Either choice is defensible;
it is a trust decision and therefore yours.

## What was checked (all on 2026-10-24)

1. `python ops/security/attestation_roots.py --include-docs-only` fetched both sources and produced the table above (the same table the earlier
   `CANDIDATE_ROOTS.md` records, taken two days before).
2. **Independent recomputation in a real browser.** The documentation page was opened in a browser and the SHA-256 of every certificate shown on it
   was computed with the browser's own crypto; the same was done for the API's JSON. Both matched the tool, fingerprint for fingerprint (5 on
   the page, 2 from the API).
3. The committed file was loaded with the server's own loader (`app.auth.attestation.load_roots_pem`): 4 certificates, each genuinely
   self-signed, each a CA, none expired, and the set of fingerprints equals the four above exactly.
4. The production server **boots** with this file (dummy secret and signing digest, only to prove boot) and builds an attestation policy with 4 roots.
5. Google's revocation list, `https://android.googleapis.com/attestation/status`, is reachable (HTTP 200, 1,765 entries). The server fails
   closed without it.
6. The full server and ops test suites pass with the file in place.

## What was NOT checked

* **No person has compared the fingerprints with Google's page.** Steps 1 and 2 are two code paths reading Google's own endpoints, which is strong
  but is not the same as a human looking at the page. Do that, then sign off below.
* **No real phone has produced a chain that ends at one of these roots.** Until then, "the server accepts a genuine chain" is only proven with
  synthetic chains. `ops/e2e/verify_captured_chain.py` (step F) is the tool for testing a real chain.
* Google can rotate roots again. Re-run the tool before each release and compare.

## Sign-off (fill in by hand before committing)

* [ ] I compared the four fingerprints above with Google's page in my own browser.
* [ ] I decided to keep / drop the two "docs page only" roots (circle one).

Signed: ______________________  Date: ______________
