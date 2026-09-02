"""Tunable constants for the GRUDGE trust engine. Confirmed 2026-09-02.

Every number here shapes a decision the broker cannot make without memory.
"""

SCHEMA_VERSION = 1

# EWMA weight of the newest observation for each trust dimension.
EWMA_ALPHA = 0.35

# Neutral prior for every dimension. Decay pulls values back toward it.
PRIOR = 0.5

# Trust dimensions decay toward PRIOR with this half-life (days) on read.
DECAY_HALF_LIFE_DAYS = 14.0

# A failure stops counting toward status after this many days.
FAILURE_TTL_DAYS = 30

# Failures kept on the entity as facts (job id, date, reason). Oldest dropped.
MAX_FAILURES_KEPT = 10

# A job is a failure when the evaluator score is below this, or it was disputed.
FAIL_SCORE = 0.5

# Journal-only until one of these is hit, then promoted to a warm entity.
PROMOTE_AT_SAMPLES = 3
PROMOTE_AT_FAILURES = 2

# Status thresholds on live (unexpired) failures.
PROBATION_AT_FAILURES = 2
BLACKLIST_AT_FAILURES = 3

# private_score weights. Must sum to 1.0.
WEIGHTS = {
    "spec_adherence": 0.40,
    "category_competence": 0.20,
    "latency": 0.15,
    "refund_behavior": 0.15,
    "price_drift": 0.10,
}

# risk_premium = clamp((PREMIUM_PIVOT - private_score) * PREMIUM_SLOPE, 0, PREMIUM_MAX)
PREMIUM_PIVOT = 0.65
PREMIUM_SLOPE = 1.4
PREMIUM_MAX = 0.5

# Terms table. Job size cap as a fraction of the spec's base size.
SIZE_CAP_UNKNOWN = 0.10
SIZE_CAP_PROBATION = 0.25
# trusted: base * (SIZE_CAP_TRUSTED_FLOOR + private_score)
SIZE_CAP_TRUSTED_FLOOR = 0.5

# trusted providers skip staging / evaluator above these scores.
STAGED_BELOW = 0.80
EVALUATOR_BELOW = 0.85

RETRY_TRUSTED = 2
RETRY_UNKNOWN = 1
RETRY_PROBATION = 0

STAGES_WHEN_STAGED = 2

# Dispute window (seconds) we hold before releasing. Widened when the
# cross-tier search finds recent trouble.
DISPUTE_WINDOW_BASE_S = 600
DISPUTE_WINDOW_TROUBLE_MULT = 4

# Consortium: refuse an unknown provider when the shared redacted signal shows
# at least this many live failures reported by other brokers.
CONSORTIUM_REFUSE_AT = 2

STATUS_TRUSTED = "trusted"
STATUS_PROBATION = "probation"
STATUS_BLACKLISTED = "blacklisted"
STATUS_UNKNOWN = "unknown"          # not a stored status: no warm entity yet

TENANT_CONSORTIUM = "consortium"
CATEGORY_COUNTERPARTY = "counterparty"
CATEGORY_SIGNAL = "signal"
