"""Promotion gate on real LLM replay scores.

Scores are per-task pass fractions over N samples. The noise margin is the larger of one sample's
worth (1 / (N * tasks)) and two standard errors of the paired difference of train means, where each
task's variance is its own sampling variance s(1-s)/N in the baseline and in the candidate. A task
whose samples always agree adds no noise; tasks whose samples disagree widen the margin. A candidate is promoted
only when its train mean beats the baseline by more than the margin, its holdout mean does not drop
by more than the margin, and no task that passed every sample falls to a third or less. This is a
measured result on the suite, not a guarantee.
"""
import math


def margin(base, samples, cand=None):
    train = [t for t, v in base.items() if v["split"] == "train"]
    if not train:
        return 1.0
    var = sum(base[t]["score"] * (1 - base[t]["score"]) / samples for t in train)
    if cand is not None:
        var += sum(cand[t]["score"] * (1 - cand[t]["score"]) / samples for t in train)
    se = math.sqrt(var) / len(train)
    return round(max(1.0 / (samples * len(train)), 2 * se), 4)


def _mean(res, split):
    vals = [v["score"] for v in res.values() if v["split"] == split]
    return sum(vals) / len(vals) if vals else None


def decide(base, cand, samples):
    if set(base) != set(cand) or not base:
        raise ValueError("gate needs the same nonempty task set")
    m = margin(base, samples, cand)
    bt, ct = _mean(base, "train"), _mean(cand, "train")
    bh, ch = _mean(base, "holdout"), _mean(cand, "holdout")
    regressions = sorted(t for t in base if base[t]["score"] == 1.0 and cand[t]["score"] <= 1 / 3)
    holdout_drop = bh is not None and ch is not None and ch < bh - m
    gain = round(ct - bt, 4)
    if regressions or holdout_drop:
        choice = "reject"
        reason = "regression on " + ", ".join(regressions) if regressions else f"holdout fell {bh:.2f} -> {ch:.2f}"
    elif gain > m:
        choice, reason = "promote", f"train +{gain:.2f} beats noise margin {m:.2f}; holdout held"
    else:
        choice, reason = "hold", f"train change {gain:+.2f} within noise margin {m:.2f}"
    return {"policy": "llm-replay-v2", "choice": choice, "reason": reason, "margin": m, "train_gain": gain,
            "train_before": round(bt, 4), "train_after": round(ct, 4),
            "holdout_before": None if bh is None else round(bh, 4), "holdout_after": None if ch is None else round(ch, 4),
            "regressions": regressions, "samples": samples}
