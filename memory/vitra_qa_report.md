# Vitra — QA Report
job_id: `6baf4660-b48d-49ee-9ddd-e4546f3ccc15`
runtime: 6.2 s

## Extraction
- rows_extracted: 264
- images_extracted: 0

## Certification
- overall_score: **97.3**
- production_ready: False
- duplicates_sku: 6
- cross_family_skus: 0

## Row status
- accepted: 250
- pending:  8
- rejected: 6

## Structural counts
- families:      102
- subcategories: 20
- series:        40
- finishes:      5
- colours:       5
- with_dimensions: 264
- with_images:     258

## Image quality
{
  "total": 258,
  "excellent": 4,
  "good": 30,
  "acceptable": 55,
  "poor": 169,
  "by_source": {
    "png": 105,
    "jpg": 36,
    "jpeg": 117
  },
  "min_edge_px": 144,
  "median_edge_px": 300,
  "max_edge_px": 1126,
  "premium_pct": 13,
  "verdict": "Supplier file only contains thumbnail-grade artwork (13% premium; median longest edge = 300px). Recommend sourcing official product photography separately."
}
