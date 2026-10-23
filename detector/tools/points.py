"""Python mirror of PointsScale in detector/src/main/kotlin/com/satark/detector/Explainer.kt (display only).

Each reason's contribution (weight x scaled value, logit units) becomes whole points; the total gets a band name. These
numbers never feed back into the score, threshold or level, and are not probabilities.
"""
import math

LOGIT_PER_POINT = 0.5


def points(contribution: float) -> int:
    return max(1, math.floor(contribution / LOGIT_PER_POINT + 0.5))


def band(total: int) -> str:
    if total <= 3:
        return "LOG"
    if total <= 5:
        return "NUDGE"
    if total <= 8:
        return "PAUSE"
    return "ESCALATE"
