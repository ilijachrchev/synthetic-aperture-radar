# Catalog evidence

Public metadata retrieved on **13 November 2026** for the research task. No science imagery, account credentials, or signed access URLs were downloaded or stored here.

## Files

| File | Contents |
| --- | --- |
| [valencia_nisar_catalog.json](valencia_nisar_catalog.json) | Compact CMR results for validated, provisional, and beta NISAR GCOV collections; exact query URLs, retrieval time, counts, IDs, footprints, and selected asset links |
| [G4309933434-ASF.umm.json](G4309933434-ASF.umm.json) | Detailed public metadata for the candidate 10 September 2026 NISAR scene |
| [G4345394349-ASF.umm.json](G4345394349-ASF.umm.json) | Detailed public metadata for the candidate 4 October 2026 NISAR scene |
| [valencia_sentinel1_2024_catalog.json](valencia_sentinel1_2024_catalog.json) | Compact CMR inventory for OPERA RTC-S1 around the historical Valencia flood |

The detailed files retain the public UMM record, including associated-asset references. A URL appearing in a public catalog does not imply anonymous access to the referenced asset; some associated internal metadata URLs are explicitly restricted. Use documented science/browse/QA assets through the appropriate access route.

## Query scope and interpretation

Bounding box, WGS84 longitude/latitude: `[-0.50, 39.10, -0.20, 39.50]` in **west, south, east, north** order.

NISAR queries used each of:

```text
NISAR_L2_GCOV_V1
NISAR_L2_GCOV_PROVISIONAL_V1
NISAR_L2_GCOV_BETA_V1
```

The OPERA query used `OPERA_L2_RTC-S1_V1` with temporal bounds `2024-10-20T00:00:00Z,2024-11-02T23:59:59Z`.

Each query requested at most 1,000 records and returned fewer than that. `complete` records whether the number saved equals the server's `CMR-Hits` count. Future refreshes may require pagination and can return different results as products are added, replaced, or reprocessed.

Important distinctions:

- Counts represent **catalog records intersecting the box**, not distinct acquisition dates, full AOI coverage, or usable observations.
- CMR legacy polygon strings use **latitude longitude** pairs. This differs from the bounding-box order above and GeoJSON coordinate order.
- `granule_size` is retained unchanged from CMR; it can include associated assets. For precise science-file bytes, use `DataGranule.ArchiveAndDistributionInformation` in the detailed UMM records.
- NISAR filename segments identify cycle, relative track, orbit direction, frame, mode, polarization, times, and processing release. Check detailed attributes rather than relying only on string parsing.
- The exact selected NISAR endpoints have stack `066_D_069`, primary HH/HV, and release `P05023`.
- Neither downloaded pixel quality nor a surface-change result is established by these records.

## Repeat a discovery query

This standard-library example repeats the provisional discovery request and reports compact facts. It requires network access, but no Earthdata authentication, and does **not** download imagery or overwrite the saved snapshot.

```python
import json
from urllib.parse import urlencode
from urllib.request import urlopen

params = {
    "short_name": "NISAR_L2_GCOV_PROVISIONAL_V1",
    "bounding_box": "-0.5,39.1,-0.2,39.5",
    "page_size": 1000,
    "sort_key": "start_date",
}
url = "https://cmr.earthdata.nasa.gov/search/granules.json?" + urlencode(params)
with urlopen(url, timeout=30) as response:
    hits = int(response.headers["CMR-Hits"])
    entries = json.load(response)["feed"]["entry"]

print("Records:", hits, "Returned:", len(entries))
if hits > len(entries):
    raise RuntimeError("More results exist; paginate before treating this as complete")
for entry in entries:
    print(entry["id"], entry["time_start"], entry["producer_granule_id"])
```

Detailed metadata can be retrieved from `https://cmr.earthdata.nasa.gov/search/concepts/{granule_id}.umm_json`. See the [CMR search documentation](https://cmr.earthdata.nasa.gov/search/site/docs/search/api.html) for endpoint behavior and pagination. Product interpretation and actual data access are described in the [research](../RESEARCH.md) and [implementation plan](../IMPLEMENTATION_PLAN.md).
