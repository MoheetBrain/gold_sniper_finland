# Data sources, licences and redistribution decisions

Reviewed **2 November 2026** against repository provenance and official sources. A data server being public does not confer blanket redistribution permission. Historical licence claims in the acquisition register are not treated as clearance. No legal guarantee or confirmation of current exploration rights is implied.

## What this candidate distributes

Only project code, project-authored prose/figures, coordinate-free aggregate experiment results, synthetic examples and simplified **Natural Earth** country geometry. **No GTK observations, Tukes permit records, satellite chips, proprietary map tiles, raw geological datasets or unpublished target coordinates are included.** Dataset-specific uncertainties therefore limit full reproduction, not the offline synthetic demonstration.

MIT is recommended for project-owned code/synthetic fixtures, subject to owner approval. It does not relicense third-party data. Original project figures and documentation can use the same licence if the owner confirms ownership. Retain the separate notices below.

## Reviewed source families

| Source / use in original work | Official terms and attribution | Release decision |
|---|---|---|
| GTK bedrock, structures, FODD, mines, surficial geology, glacial indicators and till geochemistry | [GTK open licence](https://www.gtk.fi/en/open-licence/) applies CC BY 4.0 to designated open products, requires source/product/date, licence link, disclaimers and change notice. GTK also has Basic and other licences; verify the specific product. | Original source records are absent or excluded. Generic acquisition/processing code and coordinate-free aggregate results retained. Do not assume every ArcGIS layer is CC BY. |
| GTK Hakku magnetic/gravity grids, drillholes and historical reports | [Hakku](https://hakku.gtk.fi/en/locations/) product metadata controls. [GTK terms](https://www.gtk.fi/en/open-licence/) do not turn Basic-licence products into open data. | All raw files/reports withheld; obtain exact product/version/permission before reuse. Historical BA_FIN.XYZ processing is documented, not redistributed. |
| Tukes mining register: reservations, exploration permits, concessions, claims and gold-panning rights | [Official map-files page](https://tukes.fi/en/mining-ore-prospecting-and-gold-panning/map-files). The official page returned HTTP 403 during this review; explicit redistribution terms were not established from the available evidence. | No cadastre records redistributed. Download code only. Confirm terms and source/date attribution directly before sharing snapshots or derived legal-status maps. |
| Syke: Natura 2000, protected areas, groundwater and other environmental restrictions | [Use licence](https://www.syke.fi/en/environmental-data/use-license-and-responsibilities): designated open data CC BY 4.0; name Syke and dataset. Other products can have restrictions in metadata. | No source geometry distributed. GTK-hosted copies do not replace original rights metadata. |
| National Land Survey: terrain, DEM, water, railways and base maps | [Publication rights](https://www.maanmittauslaitos.fi/en/about-nls/organisation/publications-and-brochures/publication-rights): open datasets can be published under their CC BY 4.0 terms, depending on source. Map-service use is distinct. | No data/tiles retained. Product-level review required before acquisition or redistribution. |
| OpenStreetMap / Overpass / tile service | [ODbL and attribution](https://www.openstreetmap.org/copyright); credit OpenStreetMap contributors, link licence, observe share-alike obligations where applicable. Tile/API policies are separate. | Original town cache and tile-based maps excluded; no OSM-derived geometry in new figures. |
| Natural Earth admin-0 countries | [Terms](https://www.naturalearthdata.com/about/terms-of-use/): vector/raster data public domain. Courtesy credit: “Made with Natural Earth.” | Included five country outlines, simplified at 0.035° with topology preserved. Source/archive hash and changes in `data/context/provenance.json`. No targets. |
| geoBoundaries Finland ADM0 | [API/licensing](https://www.geoboundaries.org/api.html): gbOpen CC BY 4.0 compliant; other release families differ. Exact source metadata must be retained. | Original large boundary and metadata excluded; no reliance on unverified family/version. |
| Eurostat GISCO countries / EuroGeographics | [Administrative-unit terms](https://ec.europa.eu/eurostat/en/web/gisco/geodata/administrative-units) specify noncommercial use and visible EuroGeographics attribution. | Original 2020 boundary file excluded; do not bundle in a permissively licensed software archive. |
| Esri World Imagery and other background tiles | [Esri terms](https://www.esri.com/en-us/legal/terms/full-master-agreement); provider/product restrictions and required attribution must be checked. | No imagery, rendered original target map or tile cache included; no general republication permission assumed. |
| GeoNames settlement labels | [Data export terms](https://www.geonames.org/export): CC-BY attribution to GeoNames; check exact download/version. | Source referenced by original diagnostics; no GeoNames records retained. |
| Sentinel-1 RTC / Copernicus DEM via Microsoft Planetary Computer | [Catalogue](https://planetarycomputer.microsoft.com/catalog): collection-specific licences apply. [Copernicus DEM notice](https://dataspace.copernicus.eu/news/2026-7-17-copernicus-dem-30m-view-service-license-acceptance) also illustrates that service access rights can differ. | TerraMind prototype, imagery and embeddings excluded. No model inference run or new terms accepted. |
| TerraMind / TerraTorch pretrained model and code | [Official TerraMind repository](https://github.com/IBM/terramind); separate code/model/data licences must be checked for an actual distribution. | No vendored code, model weights or prototype embeddings in candidate. No foundation-model performance claim. |
| Väylä/Digiroad, Fingrid, Statistics Finland, Metsähallitus, reindeer-herding association and EEA | [Digiroad](https://vayla.fi/en/transport-network/data/digiroad/open-data), [Fingrid](https://data.fingrid.fi/en/), [Statistics Finland](https://stat.fi/org/avoindata/paikkatietoaineistot_en.html), [Metsähallitus](https://www.metsa.fi/), [Paliskunnat](https://paliskunnat.fi/), [EEA](https://www.eea.europa.eu/). These occur as acquisition targets/checklists, not proof that every layer ran. | No materials retained. Exact dataset terms, attribution, access and privacy require product-level verification; not blanket-cleared here. |

The protected-area and cultural/land-use layers were incomplete in the original workflow. Missing data must never be interpreted as unrestricted land.

## Dataset-level provenance catalogue

The following register preserves **historical acquisition status**, not present-day availability. All source observations are external-only in this candidate. `already_exists` or `downloaded` means the original report said so; the current Git snapshot does not contain those original inputs. The original register's source URLs are retained for acquisition planning, not as a warranty of rights.

| Dataset | Historical status | Source URL | Release material |
|---|---|---|---|
| Tukes active exploration permits | already_exists | [Official source](https://tukes.fi/en/mining-ore-prospecting-and-gold-panning/map-files) | Metadata only; raw/target data excluded |
| Tukes exploration applications | already_exists | [Official source](https://tukes.fi/en/mining-ore-prospecting-and-gold-panning/map-files) | Metadata only; raw/target data excluded |
| Tukes reservations | already_exists | [Official source](https://tukes.fi/en/mining-ore-prospecting-and-gold-panning/map-files) | Metadata only; raw/target data excluded |
| Tukes reservation applications | already_exists | [Official source](https://tukes.fi/en/mining-ore-prospecting-and-gold-panning/map-files) | Metadata only; raw/target data excluded |
| Tukes mining permits | already_exists | [Official source](https://tukes.fi/en/mining-ore-prospecting-and-gold-panning/map-files) | Metadata only; raw/target data excluded |
| Tukes gold panning permits | already_exists | [Official source](https://tukes.fi/en/mining-ore-prospecting-and-gold-panning/map-files) | Metadata only; raw/target data excluded |
| Tukes Karenssi/cooling-off/lapsed status | already_exists | [Official source](https://tukes.fi/en/mining-ore-prospecting-and-gold-panning/map-files) | Metadata only; raw/target data excluded |
| GTK bedrock geology polygons | already_exists | [Official source](https://gtkdata.gtk.fi/arcgis/rest/services/GTK_Bedrock_and_Superficial_Geology/MapServer/3) | Metadata only; raw/target data excluded |
| GTK lithology attributes | already_exists | [Official source](https://gtkdata.gtk.fi/arcgis/rest/services/GTK_Bedrock_and_Superficial_Geology/MapServer/3) | Metadata only; raw/target data excluded |
| GTK stratigraphy/group attributes | already_exists | [Official source](https://gtkdata.gtk.fi/arcgis/rest/services/GTK_Bedrock_and_Superficial_Geology/MapServer/3) | Metadata only; raw/target data excluded |
| Central Lapland Greenstone Belt boundary or derivable geology | already_exists | [Official source](https://gtkdata.gtk.fi/arcgis/rest/services/GTK_Bedrock_and_Superficial_Geology/MapServer/3) | Metadata only; raw/target data excluded |
| GTK structures/faults/shear zones | already_exists | [Official source](https://gtkdata.gtk.fi/arcgis/rest/services/GTK_Bedrock_and_Superficial_Geology/MapServer/0) | Metadata only; raw/target data excluded |
| Dykes if available | manual_required | [Official source](https://hakku.gtk.fi) | Metadata only; raw/target data excluded |
| Lithological contacts if available | manual_required | [Official source](https://gtkdata.gtk.fi/arcgis/rest/services/GTK_Bedrock_and_Superficial_Geology/MapServer/3) | Metadata only; raw/target data excluded |
| GTK aeromagnetic TMI | manual_required | [Official source](https://gtkdata.gtk.fi/arcgis/rest/services/MDaE/Geophysics/MapServer/63) | Metadata only; raw/target data excluded |
| Magnetic 1VD or raw TMI suitable for derivative calculation | manual_required | [Official source](https://gtkdata.gtk.fi/arcgis/rest/services/MDaE/Geophysics/MapServer/63) | Metadata only; raw/target data excluded |
| Magnetic analytic signal if available | manual_required | [Official source](https://hakku.gtk.fi) | Metadata only; raw/target data excluded |
| Magnetic tilt derivative if available | manual_required | [Official source](https://gtkdata.gtk.fi/arcgis/rest/services/MDaE/Geophysics/MapServer/63) | Metadata only; raw/target data excluded |
| Bouguer gravity | manual_required | [Official source](https://gtkdata.gtk.fi/arcgis/rest/services/MDaE/Geophysics/MapServer/58) | Metadata only; raw/target data excluded |
| Gravity gradient / upward continuation if available | manual_required | [Official source](https://gtkdata.gtk.fi/arcgis/rest/services/MDaE/Geophysics/MapServer/58) | Metadata only; raw/target data excluded |
| Radiometric K, Th, U if available | manual_required | [Official source](https://gtkdata.gtk.fi/arcgis/rest/services/MDaE/Geophysics/MapServer/72) | Metadata only; raw/target data excluded |
| EM/electromagnetic data if publicly available | manual_required | [Official source](https://gtkdata.gtk.fi/arcgis/rest/services/MDaE/Geophysics/MapServer/66) | Metadata only; raw/target data excluded |
| GTK till geochemistry Au | downloaded | [Official source](https://gtkdata.gtk.fi/arcgis/rest/services/Rajapinnat/GTK_Maapera_WFS/MapServer/11) | Metadata only; raw/target data excluded |
| GTK till As | downloaded | [Official source](https://gtkdata.gtk.fi/arcgis/rest/services/Rajapinnat/GTK_Maapera_WFS/MapServer/52) | Metadata only; raw/target data excluded |
| GTK till Sb | downloaded | [Official source](https://gtkdata.gtk.fi/arcgis/rest/services/Rajapinnat/GTK_Maapera_WFS/MapServer/52) | Metadata only; raw/target data excluded |
| GTK till Bi | manual_required | [Official source](https://hakku.gtk.fi) | Metadata only; raw/target data excluded |
| GTK till Te | downloaded | [Official source](https://gtkdata.gtk.fi/arcgis/rest/services/Rajapinnat/GTK_Maapera_WFS/MapServer/11) | Metadata only; raw/target data excluded |
| GTK till W | downloaded | [Official source](https://gtkdata.gtk.fi/arcgis/rest/services/Rajapinnat/GTK_Maapera_WFS/MapServer/52) | Metadata only; raw/target data excluded |
| GTK till Cu | downloaded | [Official source](https://gtkdata.gtk.fi/arcgis/rest/services/Rajapinnat/GTK_Maapera_WFS/MapServer/10) | Metadata only; raw/target data excluded |
| GTK till Co | downloaded | [Official source](https://gtkdata.gtk.fi/arcgis/rest/services/Rajapinnat/GTK_Maapera_WFS/MapServer/10) | Metadata only; raw/target data excluded |
| GTK till Ni | downloaded | [Official source](https://gtkdata.gtk.fi/arcgis/rest/services/Rajapinnat/GTK_Maapera_WFS/MapServer/10) | Metadata only; raw/target data excluded |
| Detection limits / sample fraction / survey metadata | downloaded | [Official source](https://gtkdata.gtk.fi/arcgis/rest/services/Rajapinnat/GTK_Maapera_WFS/MapServer/10) | Metadata only; raw/target data excluded |
| Stream sediment geochemistry if available | downloaded | [Official source](https://gtkdata.gtk.fi/arcgis/rest/services/Rajapinnat/GTK_Maapera_WFS/MapServer/53) | Metadata only; raw/target data excluded |
| Bedrock/lithogeochemistry if available | manual_required | [Official source](https://hakku.gtk.fi) | Metadata only; raw/target data excluded |
| Surficial geology | downloaded | [Official source](https://gtkdata.gtk.fi/arcgis/rest/services/Rajapinnat/GTK_Maapera_WFS/MapServer/48) | Metadata only; raw/target data excluded |
| Till cover / drift thickness if available | manual_required | [Official source](https://gtkdata.gtk.fi/arcgis/rest/services/Maapeitepaksuus_1m/MapServer) | Metadata only; raw/target data excluded |
| Glacial flow indicators | downloaded | [Official source](https://gtkdata.gtk.fi/arcgis/rest/services/Rajapinnat/GTK_Maapera_WFS/MapServer/31) | Metadata only; raw/target data excluded |
| Drumlins | downloaded | [Official source](https://gtkdata.gtk.fi/arcgis/rest/services/Rajapinnat/GTK_Maapera_WFS/MapServer/58) | Metadata only; raw/target data excluded |
| Ribbed moraines | downloaded | [Official source](https://gtkdata.gtk.fi/arcgis/rest/services/Rajapinnat/GTK_Maapera_WFS/MapServer/60) | Metadata only; raw/target data excluded |
| Eskers | downloaded | [Official source](https://gtkdata.gtk.fi/arcgis/rest/services/Rajapinnat/GTK_Maapera_WFS/MapServer/60) | Metadata only; raw/target data excluded |
| Peat/bog/wetland polygons | manual_required | [Official source](https://www.syke.fi/en/open-information/open-data) | Metadata only; raw/target data excluded |
| DEM/elevation | manual_required | [Official source](https://www.maanmittauslaitos.fi/en/e-services/open-data-file-download-service) | Metadata only; raw/target data excluded |
| Slope | manual_required | [Official source](https://www.maanmittauslaitos.fi/en/e-services/open-data-file-download-service) | Metadata only; raw/target data excluded |
| Water bodies | manual_required | [Official source](https://www.maanmittauslaitos.fi/en/e-services/open-data-file-download-service) | Metadata only; raw/target data excluded |
| GTK/FODD mineral deposit database | already_exists | [Official source](https://gtkdata.gtk.fi/arcgis/rest/services/Fodd/fodd_FDM_v5/MapServer/39) | Metadata only; raw/target data excluded |
| Gold occurrences | already_exists | [Official source](https://gtkdata.gtk.fi/arcgis/rest/services/Fodd/fodd_FDM_v5/MapServer/39) | Metadata only; raw/target data excluded |
| Orogenic gold labels | already_exists | [Official source](https://gtkdata.gtk.fi/arcgis/rest/services/Fodd/fodd_FDM_v5/MapServer/39) | Metadata only; raw/target data excluded |
| Known mines | already_exists | [Official source](https://gtkdata.gtk.fi/arcgis/rest/services/MDaE/Mines_deposits/MapServer/5) | Metadata only; raw/target data excluded |
| Historical prospects | already_exists | [Official source](https://gtkdata.gtk.fi/arcgis/rest/services/Fodd/fodd_FDM_v5/MapServer/39) | Metadata only; raw/target data excluded |
| Drillholes if available | manual_required | [Official source](https://hakku.gtk.fi) | Metadata only; raw/target data excluded |
| Historical exploration reports if downloadable | manual_required | [Official source](https://hakku.gtk.fi) | Metadata only; raw/target data excluded |
| Natura 2000 | already_exists | [Official source](https://gtkdata.gtk.fi/arcgis/rest/services/MDaE/NatureETC/MapServer/1) | Metadata only; raw/target data excluded |
| Protected areas | already_exists | [Official source](https://gtkdata.gtk.fi/arcgis/rest/services/MDaE/NatureETC/MapServer/2) | Metadata only; raw/target data excluded |
| Wilderness areas | manual_required | [Official source](https://www.syke.fi/en/open-information/open-data) | Metadata only; raw/target data excluded |
| Groundwater areas | already_exists | [Official source](https://gtkdata.gtk.fi/arcgis/rest/services/MDaE/NatureETC/MapServer/0) | Metadata only; raw/target data excluded |
| Water bodies | manual_required | [Official source](https://www.maanmittauslaitos.fi/en/e-services/open-data-file-download-service) | Metadata only; raw/target data excluded |
| Roads | manual_required | [Official source](https://vayla.fi/en/transport-network/data/digiroad/open-data) | Metadata only; raw/target data excluded |
| Railways | manual_required | [Official source](https://www.maanmittauslaitos.fi/en/e-services/open-data-file-download-service) | Metadata only; raw/target data excluded |
| Power lines if available | manual_required | [Official source](https://data.fingrid.fi/en/) | Metadata only; raw/target data excluded |
| Towns | manual_required | [Official source](https://stat.fi/org/avoindata/paikkatietoaineistot_en.html) | Metadata only; raw/target data excluded |
| Kittila mine/mill location | already_exists | [Official source](https://gtkdata.gtk.fi/arcgis/rest/services/MDaE/Mines_deposits/MapServer/5) | Metadata only; raw/target data excluded |
| Active company claims nearby | already_exists | [Official source](https://tukes.fi/en/mining-ore-prospecting-and-gold-panning/map-files) | Metadata only; raw/target data excluded |
| Distance-to-infrastructure layers | manual_required | [Official source](https://vayla.fi/en/transport-network/data/digiroad/open-data) | Metadata only; raw/target data excluded |
