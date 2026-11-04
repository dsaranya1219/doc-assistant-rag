import json
import sys

from core import retrieve_baseline, retrieve_reranked

methods = {"baseline": retrieve_baseline, "reranked": retrieve_reranked}
mode = sys.argv[1] if len(sys.argv) > 1 else "baseline"
retrieve = methods[mode]

with open("testset.json", encoding="utf-8") as f:
    testset = json.load(f)

hit1 = hit5 = src1 = 0
details = []
for t in testset:
    results = retrieve(t["question"], 5)
    idx = next(
        (
            i
            for i, r in enumerate(results)
            if r["source"] == t["source"] and r["page"] == t["page"]
        ),
        -1,
    )
    if idx == 0:
        hit1 += 1
    if idx != -1:
        hit5 += 1
    if results and results[0]["source"] == t["source"]:
        src1 += 1
    details.append(
        {
            "question": t["question"],
            "expected": f"{t['source']} p{t['page']}",
            "rank": None if idx == -1 else idx + 1,
        }
    )

n = len(testset)


def pct(x):
    return f"{x / n * 100:.1f}%"


print(f"\nMode: {mode} | Questions: {n}")
print(f"Correct page in top 1: {pct(hit1)}")
print(f"Correct page in top 5: {pct(hit5)}")
print(f"Correct document at top 1: {pct(src1)}")

with open(f"results-{mode}.json", "w", encoding="utf-8") as f:
    json.dump(details, f, indent=2)