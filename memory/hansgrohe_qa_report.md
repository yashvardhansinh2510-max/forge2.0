# Hansgrohe — QA Report
job_id: `19c3e823-3128-4302-87a8-eb718eaba205`
runtime: 0.1 s

## Certification
- overall_score: **96.9**
- production_ready: True
- duplicates_sku: 23
- cross_family_skus: 3

## Row status
- accepted: 1275
- pending:  131
- rejected: 23

## Collection split
- Hansgrohe (main): 932
- AXOR (premium):   497

## Structural counts
- categories:    14   (['3hole', 'BM', 'Ceramic', 'HFAV', 'Holder', 'SHOWERS HANSGROHE', 'Showerhose', 'Single lever', 'Spout', 'TBM', 'Thermostat', 'WBM', 'handshower', 'kitchen'])
- subcategories: 2
- series:        46
- families:      1290
- variants:      1429
- finishes:      14
- colours:       14

## Per-file
[
  {
    "file": "BM.xlsx",
    "rows": 102,
    "images_found": 102,
    "images_mapped": 102
  },
  {
    "file": "Ceramic.xlsx",
    "rows": 76,
    "images_found": 76,
    "images_mapped": 76
  },
  {
    "file": "HFAV.xlsx",
    "rows": 68,
    "images_found": 64,
    "images_mapped": 68
  },
  {
    "file": "Holder.xlsx",
    "rows": 92,
    "images_found": 78,
    "images_mapped": 91
  },
  {
    "file": "Thermostat.xlsx",
    "rows": 296,
    "images_found": 289,
    "images_mapped": 296
  },
  {
    "file": "WBM.xlsx",
    "rows": 127,
    "images_found": 120,
    "images_mapped": 127
  },
  {
    "file": "TBM.xlsx",
    "rows": 97,
    "images_found": 97,
    "images_mapped": 97
  },
  {
    "file": "3hole.xlsx",
    "rows": 54,
    "images_found": 54,
    "images_mapped": 54
  },
  {
    "file": "Single_lever.xlsx",
    "rows": 43,
    "images_found": 43,
    "images_mapped": 43
  },
  {
    "file": "Spout.xlsx",
    "rows": 72,
    "images_found": 72,
    "images_mapped": 72
  },
  {
    "file": "handshower.xlsx",
    "rows": 87,
    "images_found": 87,
    "images_mapped": 87
  },
  {
    "file": "Showerhose.xlsx",
    "rows": 42,
    "images_found": 42,
    "images_mapped": 42
  },
  {
    "file": "kitchen.xlsx",
    "rows": 33,
    "images_found": 33,
    "images_mapped": 33
  },
  {
    "file": "SHOWERS_HANSGROHE.xlsx",
    "rows": 240,
    "images_found": 237,
    "images_mapped": 240
  }
]

## Image quality
{
  "total": 1428,
  "excellent": 397,
  "good": 103,
  "acceptable": 150,
  "poor": 778,
  "by_source": {
    "png": 1197,
    "jpeg": 231
  },
  "min_edge_px": 92,
  "median_edge_px": 279,
  "max_edge_px": 2832,
  "premium_pct": 35,
  "verdict": "Supplier file only contains thumbnail-grade artwork (35% premium; median longest edge = 279px). Recommend sourcing official product photography separately."
}
