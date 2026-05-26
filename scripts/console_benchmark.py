import time
import httpx

HASHES = [
    "c9321006921967d6258df6945f1d598a5c0cbf1e",
    "dda5d2cace9bc4cb0918e62bc50d657d4a10496a",
    "af458073c3096293a4dea9f369d4f308e7125bd6",
    "4b528d10eaad747ddf52251206177573ee3e9f74",
    "d4fa689e575f7626c8b136c9ad8685b945d3cccf",
    "0febfb5cac3384f487d55c559bbfc877db2d0357",
    "1bc437bce57b4b0450f6d1f8d818b7e97000745e",
    "f31a586422c9244196c810c84b6c85da350318a5",
    "31c19ffb3472c289c5bbbbc174449c8ed0d19e38",
    "d65257bb934b73647374224fd62d836815804be2",
    "fd53cfa7055fe458d4f5c0ff59a06cd43723be55",
    "b08e158ea3f5c72084f5ff8e3c30ca2e4d1ff6d1",
]

BASE = "http://127.0.0.1:8000"

ok = 0
fail = 0

with httpx.Client(timeout=25.0) as client:
    for h in HASHES:
        t0 = time.perf_counter()
        try:
            r = client.post(f"{BASE}/probe", json={"hash": h})
            dt = time.perf_counter() - t0
            if r.status_code == 200:
                ok += 1
                data = r.json()
                res = data.get("resolution") or {}
                print(f"OK   {h}  {dt:5.2f}s  connect={data.get('connect_time_ms')}ms  res={res.get('label')}", flush=True)
            else:
                fail += 1
                try:
                    err = r.json().get("detail", {}).get("error")
                except Exception:
                    err = r.text[:160]
                print(f"FAIL {h}  {dt:5.2f}s  {err}", flush=True)
        except Exception as exc:
            fail += 1
            dt = time.perf_counter() - t0
            print(f"ERR  {h}  {dt:5.2f}s  {type(exc).__name__}: {exc}", flush=True)

print(f"SUMMARY total={len(HASHES)} ok={ok} fail={fail}", flush=True)
