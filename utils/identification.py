"""Conservative prototype thresholds: scores are evidence, never probabilities."""

from dataclasses import dataclass, field
import math

from utils.template_index import image_hash, informative


@dataclass
class Identification:
    status: str
    candidates: list = field(default_factory=list)
    mode: str = "hash-only"


def identify(image, rows, vector=None):
    if not rows:
        return Identification("unavailable")
    if not informative(image):
        return Identification("unknown")
    query_hash = image_hash(image)
    ranked = []
    for row in rows:
        h = sum(a == b for a, b in zip(query_hash, row["hash"])) / 256
        visual = None
        other = row.get("embedding")
        if vector is not None and other is not None and len(vector) == len(other):
            norm = math.sqrt(sum(x*x for x in vector) * sum(x*x for x in other))
            if norm and math.isfinite(norm):
                score = sum(a*b for a, b in zip(vector, other)) / norm
                if math.isfinite(score):
                    visual = score
        ranked.append({"id": row["id"], "hash": h, "visual": visual})
    # Only compare embedding scores when coverage is complete; partial indexes
    # must not give embedded records an artificial advantage.
    visual_mode = all(r["visual"] is not None for r in ranked)
    for r in ranked:
        r["score"] = 0.8*r["visual"] + 0.2*r["hash"] if visual_mode else r["hash"]
    ranked.sort(key=lambda r: r["score"], reverse=True)
    best = ranked[0]
    margin = best["score"] - ranked[1]["score"] if len(ranked) > 1 else 0
    if visual_mode:
        likely = best["visual"] >= 0.88 and best["hash"] >= 0.72 and margin >= 0.06
        possible = best["visual"] >= 0.78 and best["hash"] >= 0.60
    else:
        likely = best["hash"] >= 0.96 and margin >= 0.08
        possible = best["hash"] >= 0.86
    status = "likely" if likely else "possible" if possible else "unknown"
    if visual_mode:
        eligible = [r for r in ranked if r["visual"] >= 0.78 and r["hash"] >= 0.60]
    else:
        eligible = [r for r in ranked if r["hash"] >= 0.86]
    return Identification(status, eligible[:3] if status != "unknown" else [],
                          "visual + hash" if visual_mode else "hash-only")
