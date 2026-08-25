"""Channel integrity facts for a decoded recording.

A channel's name is a claim; only its samples are evidence. This module reports what the samples say and
does not decide anything: it returns per-channel facts and leaves rejection to the caller, because a
duplicated or dead channel is harmless to one analysis and fatal to another.

Motivating cases, both from a WorkMate x64 study read through this package:

* Two raw channels named ``u+HIS`` and ``u+LBB`` held byte-identical samples over all 2 447 718 samples.
  Only one electrode pair had been connected; the ``HIS`` name was not evidence of a His electrode.
* An export page whose index line carries a single pin (``...,CIM,48,``) held samples byte-identical to the
  two-pin bipolar page of the same lead (``...,CIM,48,47``). The ``pins`` field is therefore not a reliable
  statement of the derivation, and a caller asking for "the unipolar channel" can silently receive the
  bipolar one.

Thresholds are arguments rather than constants on purpose. The defaults were chosen on a single WorkMate
x64 study and should be treated as a starting point, not as validated limits.

Non-finite samples are reported rather than assumed away: epycon's own decoders do not produce them, but
this module is a general tool and one NaN must not be able to make a channel look clipped or its standard
deviation vanish.
"""
from hashlib import md5

import numpy as np

from epycon.core._typing import (
    Optional,
    Sequence,
)

# ------------------------- DEFAULT THRESHOLDS --------------------------
# Provenance: one WorkMate x64 study, 17 channels, 2 447 718 samples at 2 kHz. Starting points only.
DEAD_ZERO_FRACTION = 0.95
FROZEN_FRACTION = 0.5
RAIL_FRACTION = 0.01


def channel_digest(samples) -> str:
    """Content fingerprint of one channel, for detecting channels that carry the same samples.

    The fingerprint is taken over the samples as float64, so an int16 channel and its float copy match,
    and integers beyond 2**53 (far outside any ADC range) are not told apart.
    """
    return md5(np.ascontiguousarray(samples, dtype=np.float64).tobytes()).hexdigest()


def channel_facts(samples, name: str = "") -> dict:
    """Measurements of one channel. No thresholds are applied here.

    Returns ``zero_fraction`` (samples exactly zero), ``frozen_fraction`` (consecutive samples exactly
    equal, which a held or disconnected input produces), ``rail_fraction`` (samples resting on a repeated
    extreme, see below) and ``nonfinite_fraction``, alongside the content digest and basic statistics.

    Non-finite samples are counted and then excluded from every other statistic, so that one NaN cannot
    turn ``sd`` into NaN, collapse the range and make an ordinary channel look clipped, or close a gap and
    make two separated samples look held.

    ``frozen_fraction`` is 0.0 when no pair of adjacent samples can be evaluated at all — a single sample,
    or finite samples every one of which a gap separates. Absence of evidence is not evidence of a held
    input, and an empty or wholly non-finite channel is reported by ``n_samples``, ``zero_fraction`` and
    ``nonfinite_fraction`` instead.

    ``rail_fraction`` counts an extreme only when that exact value occurs at least twice. Every finite
    channel has one minimum and one maximum sample, so counting them unconditionally would put a floor of
    2/n on this fraction and make any channel shorter than 2/threshold samples look clipped; a channel that
    is genuinely resting against a rail repeats the value. By the same rule a single sample, or no finite
    sample at all, gives 0.0.

    ``samples`` must be one channel: a 1-D array or a column/row vector. A 2-D block is refused rather than
    flattened into one long channel that would then look perfectly healthy.
    """
    column = np.asarray(samples, dtype=float)
    if column.ndim > 1 and column.size != max(column.shape):
        raise ValueError(f"one channel must be one-dimensional, got shape {column.shape}")
    column = column.ravel()
    finite = np.isfinite(column)
    values = column[finite]
    # Differences are taken on the original column and then restricted to pairs whose both endpoints are
    # finite. Dropping the non-finite samples first would make samples that a gap had separated adjacent,
    # so [1, nan, 1, 2, nan, 2] would read as two thirds frozen when nothing was ever held.
    with np.errstate(invalid="ignore"):  # inf - inf on pairs the finite mask discards on the next line
        step = np.diff(column)
    if step.size:
        step = step[finite[:-1] & finite[1:]]
    rail = 0
    if values.size:
        low, high = float(values.min()), float(values.max())
        at_low = int(np.count_nonzero(values == low))
        at_high = int(np.count_nonzero(values == high))
        rail = (at_low if at_low >= 2 else 0) + (at_high if at_high >= 2 else 0)
        if high == low and values.size >= 2:  # a constant channel rests on its extreme at every sample
            rail = int(values.size)
    return {
        "name": name,
        "digest": channel_digest(column),
        "n_samples": int(column.size),
        "nonfinite_fraction": float(np.mean(~finite)) if column.size else 1.0,
        "sd": float(values.std()) if values.size else 0.0,
        "zero_fraction": float(np.mean(values == 0.0)) if values.size else 1.0,
        "frozen_fraction": float(np.mean(step == 0.0)) if step.size else 0.0,
        "rail_fraction": float(rail / values.size) if values.size else 0.0,
    }


def inspect_channels(
    channels,
    names: Optional[Sequence] = None,
    dead_zero_fraction: float = DEAD_ZERO_FRACTION,
    frozen_fraction: float = FROZEN_FRACTION,
    rail_fraction: float = RAIL_FRACTION,
) -> list:
    """Facts for every channel, plus the observations a caller usually wants flagged.

    ``channels`` is a 2-D numpy array with one channel per column, or a sequence of 1-D channels. The two
    are told apart by type, not by shape: a list holding a single 1-D channel is one channel, not one
    sample of many. A 1-D array, or a flat sequence of numbers, is refused rather than read as one channel
    per sample. Names must be unique, because ``duplicate_of`` and :func:`summarise` refer to channels by
    name. Each result
    carries ``duplicate_of``, naming the first channel that holds the same samples, and ``observations``, a
    list of strings. An empty ``observations`` list means nothing stood out; it is not a guarantee, and a
    non-empty one is not an instruction — see :func:`summarise` and decide in the caller.
    """
    if isinstance(channels, np.ndarray):
        if channels.ndim != 2:
            raise ValueError("an array of channels must be 2-D with one channel per column, "
                             f"got shape {channels.shape}")
        columns = [channels[:, i] for i in range(channels.shape[1])]
    else:
        columns = [np.asarray(channel) for channel in channels]
        scalars = [i for i, column in enumerate(columns) if column.ndim == 0]
        if scalars:
            raise ValueError(f"channel {scalars[0]} is a single number: pass a 2-D array or a sequence of 1-D "
                             "channels, not one flat sequence of samples")
    labels = list(names) if names is not None else [f"channel_{i}" for i in range(len(columns))]
    if len(labels) != len(columns):
        raise ValueError(f"got {len(columns)} channels but {len(labels)} names")
    if len(set(labels)) != len(labels):
        raise ValueError("channel names must be unique: duplicate_of and summarise refer to channels by name")

    results, first_seen = [], {}
    for label, column in zip(labels, columns):
        facts = channel_facts(column, name=label)
        observations = []
        digest = facts["digest"]
        if digest in first_seen:
            facts["duplicate_of"] = first_seen[digest]
            observations.append(f"duplicate of {first_seen[digest]}")
        else:
            facts["duplicate_of"] = None
            first_seen[digest] = label
        if facts["zero_fraction"] >= dead_zero_fraction:
            observations.append("dead: never connected")
        elif facts["frozen_fraction"] >= frozen_fraction:
            observations.append("frozen: held or disconnected")
        if facts["rail_fraction"] >= rail_fraction:
            observations.append("clipped: resting on a repeated extreme")
        if facts["nonfinite_fraction"] > 0.0:
            observations.append(f"{facts['nonfinite_fraction']:.1%} of samples are not finite")
        facts["observations"] = observations
        results.append(facts)
    return results


def summarise(facts: Sequence) -> dict:
    """How many channels there are, how many distinct signals they carry, and what stood out."""
    digests = {item["digest"] for item in facts}
    return {
        "n_channels": len(facts),
        "n_distinct_signals": len(digests),
        # `is not None`, not truthiness: channel_facts allows an empty name, and a duplicate of a channel
        # named "" would drop out of this report while n_distinct_signals had already counted it.
        "duplicates": {item["name"]: item["duplicate_of"] for item in facts if item["duplicate_of"] is not None},
        "flagged": {item["name"]: item["observations"] for item in facts if item["observations"]},
    }


# ------------------------- ECG LEAD IDENTITIES -------------------------
# Einthoven and Goldberger relate the six limb leads to two independent ones. A recorder that derives the
# other four satisfies these exactly, which is also why they cannot detect an I/II swap: swapping the two
# and re-deriving the rest leaves every identity intact.
LIMB_LEADS = ("I", "II", "III", "aVR", "aVL", "aVF")
LIMB_IDENTITIES = {
    "III = II - I": lambda s: s["III"] - (s["II"] - s["I"]),
    "aVR = -(I + II) / 2": lambda s: s["aVR"] + (s["I"] + s["II"]) / 2,
    "aVL = I - II / 2": lambda s: s["aVL"] - (s["I"] - s["II"] / 2),
    "aVF = II - I / 2": lambda s: s["aVF"] - (s["II"] - s["I"] / 2),
}


def check_limb_identities(leads: dict, tolerance: float = 0.05) -> dict:
    """Residual of each limb-lead identity, in the units of the leads given.

    A worst residual at floating-point zero means the four dependent leads were derived by the recorder
    rather than measured — provided the leads carry signal at all. When neither I nor II varies, every
    identity holds trivially (six flat-zero leads satisfy all four), so ``informative`` is False and
    ``derived`` is not claimed. Note the blind spot documented above: these identities cannot detect a
    swap between leads I and II.

    ``derived`` presumes float64 arithmetic: its 1e-9 threshold absorbs float64 rounding (a scaled copy
    leaves ~1e-14) but not float32 (~1e-7), and three of the four identities divide by two, so leads stored
    as integers keep a residual (1.5 LSB for truncated int16) however faithfully the recorder derived them.
    ``holds`` is then the caller's call via ``tolerance``; ``derived`` is not a test of storage dtype.
    """
    missing = [name for name in LIMB_LEADS if name not in leads]
    if missing:
        raise KeyError(f"limb leads missing: {', '.join(missing)}")
    # ravel, as channel_facts does: a lead handed in as a column slice has shape (n, 1), and the identity
    # arithmetic would broadcast it against the (n,) leads into an (n, n) grid, failing on correct data.
    # Only the six limb leads are read; other keys in the dict are left alone.
    arrays = {name: np.asarray(leads[name], dtype=float).ravel() for name in LIMB_LEADS}
    # Lengths are checked here rather than left to numpy. Most mismatches do raise a broadcast error, but a
    # lead of length one broadcasts as a scalar against every other lead and reports the whole set as an
    # exact identity while carrying no information at all.
    lengths = {array.size for array in arrays.values()}
    if len(lengths) != 1 or 0 in lengths:
        raise ValueError(f"limb leads must share one nonzero length, got {sorted(lengths)}")
    residuals = {label: float(np.max(np.abs(expression(arrays)))) for label, expression in LIMB_IDENTITIES.items()}
    # np.max, not the builtin: builtin max() compares pairwise, so a NaN is swallowed or returned depending
    # on where it sits in the sequence, and a NaN in aVF would report a worst residual of 0.0 — a silent
    # pass in exactly the case this check exists to catch. np.max propagates, and `nan <= tolerance` is False.
    worst = float(np.max(list(residuals.values())))
    # The identities are non-trivial only if one of the two independent leads varies; with I and II both
    # flat, the four dependent leads are flat too and a zero residual is no evidence of derivation.
    informative = bool(np.ptp(arrays["I"]) > 0 or np.ptp(arrays["II"]) > 0)
    return {
        "residual": residuals,
        "worst": worst,
        "holds": worst <= tolerance,
        "informative": informative,
        "derived": informative and worst <= 1e-9,
        "blind_to": "a swap between leads I and II",
    }
