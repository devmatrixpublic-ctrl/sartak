# Candidate Google attestation roots (NOT trusted yet)

Prepared for M4's manual verification. **Reproduce and refresh with `python ops/security/attestation_roots.py --write`** (tested; it fetches both sources, flags expired or single-source roots, and writes `CANDIDATE_google_attestation_roots.pem`, a file the server does not read). **No root is committed to `google_attestation_roots.pem`**: a trust anchor must be
checked by a person against Google's own page before it is pinned (see `README.md` here).

Fetched 2026-10-22 from two Google sources and compared by SHA-256 of the DER:

* `https://android.googleapis.com/attestation/root` (Google's attestation API) returns 2 certificates.
* `https://developer.android.com/privacy-and-security/security-key-attestation` (the documentation page) lists 5.

| SHA-256 (DER) | Subject | Not after | API | Docs page |
|---|---|---|---|---|
| `CE:DB:1C:B6:DC:89:6A:E5:EC:79:73:48:BC:E9:28:67:53:C2:B3:8E:E7:1C:E0:FB:E3:4A:9A:12:48:80:0D:FC` | serialNumber=f92009e853b6b045 (RSA root, self-signed) | 2042-03-15 | yes | yes |
| `6D:9D:B4:CE:6C:5C:0B:29:31:66:D0:89:86:E0:57:74:A8:77:6C:EB:52:5D:9E:43:29:52:0D:E1:2B:A4:BC:C0` | CN=Key Attestation CA1, O=Google LLC (self-signed) | 2035-07-15 | yes | yes |
| `C1:98:4A:3E:F4:5C:1E:2A:91:85:51:DE:10:60:3C:86:F7:05:1B:22:49:C4:89:1C:AE:32:30:EA:BD:0C:97:D5` | serialNumber=f92009e853b6b045 (self-signed) | **2026-05-24 (expired)** | no | yes |
| `1E:F1:A0:4B:8B:A5:8A:B9:45:89:AC:49:8C:89:82:A7:83:F2:4E:A7:30:7E:01:59:A0:C3:A7:3B:37:7D:87:CC` | serialNumber=f92009e853b6b045 (self-signed) | 2034-11-18 | no | yes |
| `AB:66:41:17:8A:36:E1:79:AA:0C:1C:DD:DF:9A:16:EB:45:FA:20:94:3E:2B:8C:D7:C7:C0:5C:26:CF:8B:48:7A` | serialNumber=f92009e853b6b045 (self-signed) | 2036-11-13 | no | yes |

What this does and does not settle:

* The first two agree across both sources, which is good evidence but not independent: both come from Google over the same
  network path. **Compare the fingerprints above with the ones printed on the documentation page in a browser.**
* The API serves only 2 roots while the documentation lists 3 more (one already expired, two valid until 2034 and 2036).
  Phones whose chains end at a newer root would be rejected if only the API's 2 were pinned. Decide whether to pin all
  non-expired roots from the documentation; do not pin the expired one.
* Check the revocation list at `https://android.googleapis.com/attestation/status` is reachable from the server (the
  server fails closed without it).
