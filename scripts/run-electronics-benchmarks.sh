#!/usr/bin/env bash
# Run all three electronics scenario benchmarks end-to-end:
#   electronics      (base Amazon-style descriptions)
#   electronics-specs (Apple spec PDFs w/ explicit compatibility)
#   electronics-reviews (specs + Amazon UK review highlights)
#
# Each benchmark: 3 setups × 3 people = 9 FullPersons
# Proxies: XOR, VD1, VD2, NVD, H
# Usage: cd "DT Study" && bash scripts/run-electronics-benchmarks.sh 2>&1 | tee logs/run-electronics.log

set -e

# Shared proxy parameters (same as 'first' benchmark runs)
CAP=20
MIN_ITER=0
CHECK="high"
TARGET="highest"
HAPPY="low"
EMPHASIS="Quickly explore the person's valuation and get to the essence of things"
ANCHOR="20 to 30"
NUM_Q=5

echo "============================================================"
echo "STEP 1: Generate benchmarks (seeds + FullPersons)"
echo "============================================================"

for BENCH in electronics electronics-specs electronics-reviews; do
    case "$BENCH" in
        electronics)         SCENARIO="ELECTRONICS" ;;
        electronics-specs)   SCENARIO="ELECTRONICS-SPECS" ;;
        electronics-reviews) SCENARIO="ELECTRONICS-REVIEWS" ;;
    esac

    echo ""
    echo ">>> make-benchmark: $BENCH ($SCENARIO)"
    python scripts/make-benchmark.py \
        --benchmark "$BENCH" \
        --scenarios "$SCENARIO" \
        --num_setups 3 \
        --num_people 3
    echo "Done: $BENCH benchmark created."
done

echo ""
echo "============================================================"
echo "STEP 2: Run proxies for each benchmark"
echo "============================================================"

for BENCH in electronics electronics-specs electronics-reviews; do
    echo ""
    echo ">>> Proxy-XOR: $BENCH"
    python scripts/run-proxy-xor.py --benchmark "$BENCH"

    echo ""
    echo ">>> Proxy-VD1: $BENCH"
    python scripts/run-proxy-vd1.py \
        --benchmark "$BENCH" \
        --cap "$CAP" \
        --min_iterations "$MIN_ITER" \
        --check_priority "$CHECK" \
        --target_bundle_priority "$TARGET" \
        --happy_priority "$HAPPY" \
        --target_bundle_emphasis "$EMPHASIS" \
        --anchor_num_target_bundles "$ANCHOR"

    echo ""
    echo ">>> Proxy-VD2: $BENCH"
    python scripts/run-proxy-vd2.py \
        --benchmark "$BENCH" \
        --cap "$CAP" \
        --min_iterations "$MIN_ITER" \
        --check_priority "$CHECK" \
        --target_bundle_priority "$TARGET" \
        --happy_priority "$HAPPY" \
        --target_bundle_emphasis "$EMPHASIS" \
        --anchor_num_target_bundles "$ANCHOR"

    echo ""
    echo ">>> Proxy-NVD: $BENCH"
    python scripts/run-proxy-nvd.py \
        --benchmark "$BENCH" \
        --num_questions "$NUM_Q" \
        --cap "$CAP" \
        --min_iterations "$MIN_ITER" \
        --check_priority "$CHECK" \
        --target_bundle_priority "$TARGET" \
        --happy_priority "$HAPPY" \
        --target_bundle_emphasis "$EMPHASIS" \
        --anchor_num_target_bundles "$ANCHOR"

    echo ""
    echo ">>> Proxy-H: $BENCH"
    python scripts/run-proxy-h.py \
        --benchmark "$BENCH" \
        --cap "$CAP" \
        --min_iterations "$MIN_ITER" \
        --check_priority "$CHECK" \
        --target_bundle_priority "$TARGET" \
        --happy_priority "$HAPPY" \
        --target_bundle_emphasis "$EMPHASIS" \
        --anchor_num_target_bundles "$ANCHOR"

    echo ""
    echo "All proxies done for $BENCH."
done

echo ""
echo "============================================================"
echo "STEP 3: Generate visualizations"
echo "============================================================"

mkdir -p data/experiments/plots

for BENCH in electronics electronics-specs electronics-reviews; do
    echo ">>> vis-benchmark-fig: $BENCH"
    python scripts/vis-benchmark-fig.py \
        "$BENCH" \
        --outprefix "data/experiments/plots/${BENCH}"
    echo "Saved: data/experiments/plots/${BENCH}_fig2.png"
done

echo ""
echo "ALL DONE. Results in data/experiments/plots/"
