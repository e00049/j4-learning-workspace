"""Answer-key eval for agent-api: correctness + latency + token cost per question."""
import json, re, sys, time, urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:9090"
PRICE = {"input": 0.30, "output": 2.50, "thinking": 2.50}   # USD per 1M tokens (verify current pricing)
INR = 88
# Each case passes if ANY group has ALL its keywords (commas removed, lowercase).
CASES = [
    ("What is my total spend this month?", [["55525"]]),
    ("How much did I spend on Swiggy and Zomato combined?", [["5119"], ["2365", "2754"]]),
    ("Which category did I spend most on, excluding Rent and Investment?", [["shopping"]]),
    ("If I cut my Swiggy and Zomato spending by 30%, how much would I save?", [["1535"]]),
    ("What is my credit score?", [["not"], ["unable"], ["don't"], ["can't"]]),
]

def tokens():
    txt = urllib.request.urlopen(f"{BASE}/metrics").read().decode()
    out = {}
    for m in re.finditer(r'^agent_llm_tokens_total\{[^}]*type="(\w+)"[^}]*\} ([\d.e+]+)$', txt, re.M):
        out[m.group(1)] = out.get(m.group(1), 0) + float(m.group(2))
    return out

def ask(q):
    req = urllib.request.Request(f"{BASE}/ask", data=json.dumps({"question": q}).encode(),
                                 headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    try:
        ans = json.loads(urllib.request.urlopen(req, timeout=90).read()).get("answer", "")
    except Exception as e:
        ans = f"ERROR {e}"
    return ans, time.perf_counter() - t0

before, passed, secs_total = tokens(), 0, 0.0
for q, any_of in CASES:
    ans, secs = ask(q)
    secs_total += secs
    norm = ans.lower().replace(",", "")
    ok = any(all(k in norm for k in group) for group in any_of)
    passed += ok
    print(f"{'PASS' if ok else 'FAIL'}  {secs:4.1f}s  {q}\n        -> {ans.strip()[:110]}")
after = tokens()
delta = {k: int(after.get(k, 0) - before.get(k, 0)) for k in after}
usd = sum(v * PRICE.get(k, 0) for k, v in delta.items()) / 1e6
print(f"\nSCORE {passed}/{len(CASES)} | avg {secs_total/len(CASES):.1f}s | tokens {delta} | ~INR {usd*INR/len(CASES):.3f}/question")
sys.exit(0 if passed == len(CASES) else 1)
