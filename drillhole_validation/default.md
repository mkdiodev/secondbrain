# Drillhole Validation Role Inference

Panduan ini dipakai UI untuk mengenali permintaan validasi drillhole dari bahasa natural.
Edit file ini ketika nama file, istilah internal, atau struktur folder Anda berbeda.

## Intent Aliases

- validasi = validate_drillhole
- validate = validate_drillhole
- validator = validate_drillhole
- cek error = validate_drillhole
- periksa data = validate_drillhole
- cek interval = validate_drillhole
- cek overlap = validate_drillhole
- cek gap = validate_drillhole


## File Role Aliases

- collar = collar
- site = collar
- gb_site = collar
- hole = collar
- lubang = collar
- lobang = collar

- survey = survey
- site_survey = survey
- gb_site_survey = survey

- downhole_survey = downhole survey
- gb_downhole_survey = downhole survey

- lithology = lithology
- litologi = lithology
- gb_lithology = lithology

- assay = assay
- gb_assay = assay

- mineralization = mineralization
- mineralisasi = mineralization
- gb_mineralization = mineralization

- oxidation = oxidation
- oksidasi = oxidation
- gb_oxidation = oxidation

- geotech = geotech
- gb_geotech = geotech

- rqd = rqd
- gb_rqd = rqd

- vein = vein
- gb_vein = vein

- alteration = alteration
- alterasi = alteration
- gb_alteration = alteration

- density = density
- densitas = density
- gb_density = density

## Required Companion Files

- survey requires collar
- lithology requires collar
- assay requires collar
- mineralization requires collar
- oxidation requires collar
- geotech requires collar
- rqd requires collar
- vein requires collar
- alteration requires collar
- density requires collar
