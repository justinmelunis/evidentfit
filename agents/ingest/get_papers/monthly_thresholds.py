"""
Hard-coded monthly quality thresholds per supplement.

Generated: 2025-10-06 15:06:51
Source: pm_papers.jsonl
Total papers analyzed: 30,000
Supplements: 80

Logic:
- Small corpus (<100 papers): P25 (25th percentile) to build diversity
- Large corpus (≥100 papers): Median (50th percentile) to maintain quality

These thresholds are STATIC - they never change month-to-month.
This provides predictable, explainable filtering behavior.
"""

# Generated thresholds
MONTHLY_THRESHOLDS = {
    # Small corpora (<100 papers) - P25 threshold
    "acetyl-l-carnitine": 3.0,
    "alpha-gpc": 3.5,
    "arginine-akg": 4.5,
    "ashwagandha": 4.0,
    "betaine": 4.5,
    "blackcurrant": 3.5,
    "boron": 3.0,
    "caffeine-anhydrous": 3.0,
    "caffeine-citrate": 2.5,
    "casein-protein": 3.0,
    "chromium-picolinate": 3.0,
    "citrulline-malate": 4.5,
    "cla": 2.5,
    "cordyceps": 3.0,
    "creatine-ethyl-ester": 2.0,
    "d-aspartic-acid": 3.0,
    "d-ribose": 3.0,
    "deer-antler": 3.5,
    "ecdysteroids": 2.0,
    "epicatechin": 3.5,
    "fenugreek": 3.0,
    "garcinia-cambogia": 3.0,
    "hica": 2.5,
    "hmb-ca": 2.5,
    "hmb-fa": 2.5,
    "isoleucine": 3.0,
    "maca": 2.5,
    "pea-protein": 5.0,
    "phosphatidic-acid": 3.0,
    "phosphatidylserine": 3.0,
    "pomegranate": 3.5,
    "pycnogenol": 3.5,
    "raspberry-ketone": 1.5,
    "red-spinach": 4.0,
    "rhodiola": 3.0,
    "shilajit": 3.0,
    "sodium-citrate": 3.0,
    "sodium-phosphate": 3.0,
    "soy-protein": 3.0,
    "synephrine": 3.5,
    "tart-cherry": 3.0,
    "theacrine": 3.5,
    "theanine": 3.0,
    "tongkat-ali": 5.0,
    "tribulus": 4.5,
    "valine": 3.0,
    "yohimbine": 3.5,
    "zma": 3.0,

    # Large corpora (>=100 papers) - Median threshold
    "alpha-lipoic-acid": 4.0,
    "arginine": 4.0,
    "bcaa": 4.0,
    "beetroot": 4.5,
    "beta-alanine": 4.5,
    "caffeine": 4.0,
    "carnitine": 4.5,
    "citrulline": 4.5,
    "collagen": 4.0,
    "coq10": 4.0,
    "creatine": 4.0,
    "creatine-monohydrate": 3.5,
    "curcumin": 5.0,
    "glutamine": 4.5,
    "glycerol": 3.0,
    "green-tea-extract": 4.0,
    "hmb": 4.5,
    "iron": 4.0,
    "ketone-esters": 4.0,
    "l-carnitine": 4.5,
    "leucine": 3.5,
    "magnesium": 4.5,
    "nac": 4.5,
    "nitrate": 4.5,
    "omega-3": 4.5,
    "protein": 4.0,
    "quercetin": 4.0,
    "resveratrol": 4.5,
    "sodium-bicarbonate": 4.0,
    "taurine": 4.5,
    "vitamin-d": 5.0,
    "whey-protein": 4.5,
}

# Recency guarantee: Top N most recent papers per supplement
# These are ALWAYS included (if quality >= 2.5) to keep research fresh
RECENCY_TOP_N = {
    "default": 2,  # Top 2 for small supplements
    "large_supplements": [
        "arginine",
        "caffeine",
        "creatine",
        "iron",
        "magnesium",
        "nitrate",
        "omega-3",
        "protein",
        "vitamin-d",
    ],
    "large_supplement_n": 10,  # Top 10 for large supplements
}

# Always add study types (bypass all thresholds)
ALWAYS_ADD_STUDY_TYPES = ["meta-analysis", "systematic_review"]

# Exceptional quality bypass
EXCEPTIONAL_QUALITY_THRESHOLD = 4.5

# Minimum quality for recency guarantee
RECENCY_MIN_QUALITY = 2.5
