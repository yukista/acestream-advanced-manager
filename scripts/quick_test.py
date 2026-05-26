import httpx
import time

HASHES = [
    "dda5d2cace9bc4cb0918e62bc50d657d4a10496a",  # was 403 last run, was OK in fast_retry
    "d65257bb934b73647374224fd62d836815804be2",  # always OK
    "31c19ffb3472c289c5bbbbc174449c8ed0d19e38",  # always OK
    "c9321006921967d6258df6945f1d598a5c0cbf1e",  # was 403
    "4b528d10eaad747ddf52251206177573ee3e9f74",  # was 403
]

for h in HASHES:
    t0 = time.time()
    r = httpx.post("http://localhost:8000/probe", json={"hash": h}, timeout=70)
    elapsed = round(time.time() - t0, 2)
    if r.status_code == 200:
        d = r.json()
        res = (d.get("resolution") or {}).get("label", "?")
        print(f"OK   {h}  {elapsed}s  res={res}")
    else:
        detail = r.json().get("detail", {})
        err = detail.get("error", r.text[:80]) if isinstance(detail, dict) else str(detail)[:80]
        print(f"FAIL {h}  {elapsed}s  {err}")
