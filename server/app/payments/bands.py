"""Coarse amount bands. The payments table keeps the band, never the rupee amount tied to a device."""

# (exclusive upper bound in rupees, label)
_BANDS = [(500, "lt_500"), (2_000, "500_2k"), (10_000, "2k_10k"), (50_000, "10k_50k"), (200_000, "50k_2l")]
AMOUNT_BANDS = [label for _, label in _BANDS] + ["gt_2l"]


def amount_band(amount: float) -> str:
    for upper, label in _BANDS:
        if amount < upper:
            return label
    return "gt_2l"
