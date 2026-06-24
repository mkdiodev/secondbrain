## Query Guidance

### Table Priority
- dbo.GB_SITE
- dbo.GB_SITE_SURVEY
- dbo.GB_DOWNHOLE_SURVEY_TIMAH
- dbo.GB_LITHOLOGY

### Identifier Aliases
- site_id = SITE_ID
- lobang = SITE_ID
- site id = SITE_ID
- hole_id = SITE_ID
- lubang = SITE_ID

### Column Aliases
- kb = BIT_COEFFICIENT
- end_depth = END_DEPTH
- depth = END_DEPTH
- kedalaman = END_DEPTH
- dalam = END_DEPTH
- total depth = END_DEPTH
- elevasi = ELEVATION
- x = EASTING
- y = NORTHING
- z = ELEVATION


# SQL Schema: default

## dbo.GB_ALTERATION
Columns:
- `PROJECT` nvarchar
- `SITE_ID` nvarchar
- `DEPTH_FROM` decimal
- `DEPTH_TO` decimal
- `ALT_INTENSTY` nvarchar
- `ALT_GROUP` nvarchar
- `CHLORITE` nvarchar
- `EPIDOTE` nvarchar
- `CALCITE` nvarchar
- `SMECTITE` nvarchar
- `ALBITE` nvarchar
- `SERICITE` nvarchar
- `KAOLINITE` nvarchar
- `ILLITE` nvarchar
- `FLUORITE` nvarchar
- `TOPAZ` nvarchar
- `TOURMALINE` nvarchar
- `MUSCOVITE` nvarchar
- `SILICA_ALTERATION` nvarchar
- `GARNET` nvarchar
- `CLINOPYROXENE` nvarchar
- `MAGNETITE` nvarchar
- `K_FELDSPAR` nvarchar
- `SEC_BIOTITE` nvarchar
- `ALUNITE` nvarchar
- `PHYROPYLLITE` nvarchar
- `SILIMANITE` nvarchar
- `MICROCLINE` nvarchar
- `PLOGOPITE` nvarchar
- `LEPIDOLITE` nvarchar
- `DICKITE` nvarchar
- `DIOPSIDE` nvarchar
- `WOLLASTONITE` nvarchar
- `HEDENBERGITE` nvarchar
- `COMMENTS` nvarchar
- `DATA_SOURCE` nvarchar
- `DATE_INSERTED` smalldatetime
- `DATE_UPDATED` smalldatetime
- `INSERTED_BY` nvarchar
- `UPDATED_BY` nvarchar
- `VALIDATION_GROUP` nvarchar
- `IGNORE_DURING_VALIDATION` bit
- `QTZ` nvarchar

## dbo.GB_DENSITY
Columns:
- `PROJECT` nvarchar
- `SITE_ID` nvarchar
- `DEPTH` decimal
- `LENGTH_CM` decimal
- `SAMPLE_ID` nvarchar
- `MEASURED_DATE` smalldatetime
- `WRAPPED_METHOD` nvarchar
- `DRY_WEIGHT_GR` decimal
- `WRAPPED_DRY_WEIGHT_GR` decimal
- `WET_WEIGHT_GR` decimal
- `WRAPPED_WET_WEIGHT_GR` decimal
- `CALIPER_L1_CM` decimal
- `CALIPER_L2_CM` decimal
- `CALIPER_L3_CM` decimal
- `CALIPER_D1_CM` decimal
- `CALIPER_D2_CM` decimal
- `CALIPER_D3_CM` decimal
- `REMARKS` nvarchar
- `DATA_SOURCE` nvarchar
- `DATE_INSERTED` smalldatetime
- `INSERTED_BY` nvarchar
- `DATE_UPDATED` smalldatetime
- `UPDATED_BY` nvarchar
- `VALIDATION_GROUP` nvarchar
- `IGNORE_DURING_VALIDATION` bit

## dbo.GB_DOWNHOLE_SURVEY_TIMAH
Columns:
- `PROJECT` nvarchar
- `SITE_ID` nvarchar
- `INSTANCE` smallint
- `READING_NO` smallint
- `DEPTH` decimal
- `RANKING` smallint
- `EXCLUDE` bit
- `PREFERRED` bit
- `DIRECTION` float
- `INCLINATION` float
- `MAGNETIC_INTENSITY` float
- `COMMENTS` nvarchar
- `DATA_SOURCE` nvarchar
- `DATE_INSERTED` smalldatetime
- `INSERTED_BY` nvarchar
- `DATE_UPDATED` smalldatetime
- `UPDATED_BY` nvarchar
- `VALIDATION_GROUP` nvarchar
- `IGNORE_DURING_VALIDATION` bit


## dbo.GB_GCA_RESULT
Columns:
- `PROJECT` nvarchar
- `SITE_ID` nvarchar
- `SAMPLE_ID` nvarchar
- `LAB_ID` nvarchar
- `MINERAL` nvarchar
- `PLUS_48_GRAIN` smallint
- `PLUS_65_GRAIN` smallint
- `PLUS_100_GRAIN` smallint
- `MINUS_100_GRAIN` smallint
- `PLUS_150_GRAIN` smallint
- `MINUS_150_GRAIN` smallint
- `DESCRIPTION` nvarchar
- `DATA_SOURCE` nvarchar
- `DATE_INSERTED` smalldatetime
- `INSERTED_BY` nvarchar
- `DATE_UPDATED` smalldatetime
- `UPDATED_BY` nvarchar
- `VALIDATION_GROUP` nvarchar
- `IGNORE_DURING_VALIDATION` bit

## dbo.GB_GCA_SAMPLE
Columns:
- `PROJECT` nvarchar
- `SITE_ID` nvarchar
- `SAMPLE_ID` nvarchar
- `LAB_ID` nvarchar
- `LAYER_NO` smallint
- `SAMPLE_DATE` smalldatetime
- `MEMO_NO` nvarchar
- `SAMPLE_SOURCE` nvarchar
- `LOCATION` nvarchar
- `KB` decimal
- `WEIGHT_SCALE_LAB` decimal
- `PLUS_48_WEIGHT` decimal
- `PLUS_65_WEIGHT` decimal
- `PLUS_100_WEIGHT` decimal
- `MINUS_100_WEIGHT` decimal
- `PLUS_150_WEIGHT` decimal
- `MINUS_150_WEIGHT` decimal
- `WEIGHT_TOTAL` decimal
- `GRAIN_SHAPE_CASSITERITE` nvarchar
- `MIN_COLOUR_CASSITERITE` nvarchar
- `SAMPLE_TYPE` nvarchar
- `ANALYSIS_METHOD` nvarchar
- `PARENT_SAMPLE_ID` nvarchar
- `STANDARD_ID` nvarchar
- `RECEIVED_DATE` smalldatetime
- `ANALYSIS_DATE` smalldatetime
- `CLIENT` nvarchar
- `DESCRIPTION` nvarchar
- `DATA_SOURCE` nvarchar
- `DATE_INSERTED` smalldatetime
- `INSERTED_BY` nvarchar
- `DATE_UPDATED` smalldatetime
- `UPDATED_BY` nvarchar
- `VALIDATION_GROUP` nvarchar
- `IGNORE_DURING_VALIDATION` bit

## dbo.GB_GCA_WELLSITE
Columns:
- `PROJECT` nvarchar
- `SITE_ID` nvarchar
- `SAMPLE_ID` nvarchar
- `LAYER_NO` smallint
- `WEIGHT_SAMPLE` decimal
- `GR_SN_TAKS` decimal
- `TDH_TAKS` decimal
- `BIT_DIAMETER_START` decimal
- `BIT_DIAMETER_FINISH` decimal
- `COMMENTS` nvarchar
- `DATA_SOURCE` nvarchar
- `DATE_INSERTED` smalldatetime
- `INSERTED_BY` nvarchar
- `DATE_UPDATED` smalldatetime
- `UPDATED_BY` nvarchar
- `VALIDATION_GROUP` nvarchar
- `IGNORE_DURING_VALIDATION` bit

## dbo.GB_GEOTECH
Columns:
- `PROJECT` nvarchar
- `SITE_ID` nvarchar
- `DEPTH` decimal
- `DEFECT_SET_NAME` nvarchar
- `DEFECT_COUNT` smallint
- `DEFECT_TYPE` nvarchar
- `DEFECT_PLANARITY` nvarchar
- `DEFECT_ROUGHNESS` nvarchar
- `ALPHA` smallint
- `BETA` smallint
- `GAMMA` smallint
- `DIP` smallint
- `DIP_DIRECTION` smallint
- `STRIKE` smallint
- `INFILL_TYPE` nvarchar
- `INFILL_TEXTURE` nvarchar
- `INFILL_THICKNESS` decimal
- `INFILL_MIN1` nvarchar
- `INFILL_MIN2` nvarchar
- `DISPLACEMENT_DIRECTION` nvarchar
- `DISPLACEMENT_AMOUNT` nvarchar
- `ORIENTATION_MARK` nvarchar
- `ORIENTATION_MARK_CONFIDENCE` nvarchar
- `ORIENTATION_TOOL` nvarchar
- `LOGGED_BY` nvarchar
- `DATA_SOURCE` nvarchar
- `COMMENTS` nvarchar
- `DATE_INSERTED` smalldatetime
- `DATE_UPDATED` smalldatetime
- `INSERTED_BY` nvarchar
- `UPDATED_BY` nvarchar
- `VALIDATION_GROUP` nvarchar
- `IGNORE_DURING_VALIDATION` bit

## dbo.GB_HIST_ASSAY
Columns:
- `PROJECT` nvarchar
- `SITE_ID` nvarchar
- `DEPTH_FROM` decimal
- `DEPTH_TO` decimal
- `SN_PCT` float
- `SN_PCT_XRF_PORT` float
- `AS_PCT_XRF_PORT` float
- `PB_PCT_XRF_PORT` float
- `CU_PCT_XRF_PORT` float
- `SN_GRAM` float
- `TDH_LAP` decimal
- `TDH_KOREKSI` decimal
- `LAP` nvarchar
- `DESC_LAP` nvarchar
- `URAT` nvarchar
- `KET_LAP` nvarchar
- `EXT_LAP` nvarchar
- `TEMPERATURE` nvarchar
- `WEATH_HYDRO` nvarchar
- `MIN_ASD` nvarchar
- `EASTING` float
- `NORTHING` float
- `ELEVATION` float
- `NO_LAP` smallint
- `COMMENTS` nvarchar
- `DATA_SOURCE` nvarchar
- `DATE_INSERTED` smalldatetime
- `DATE_UPDATED` smalldatetime
- `INSERTED_BY` nvarchar
- `UPDATED_BY` nvarchar
- `VALIDATION_GROUP` nvarchar
- `IGNORE_DURING_VALIDATION` bit

## dbo.GB_HIST_DENSITY
Columns:
- `PROJECT` nvarchar
- `SITE_ID` nvarchar
- `DEPTH_FROM` decimal
- `DEPTH_TO` decimal
- `DENSITY` decimal
- `REMARKS` nvarchar
- `DATA_SOURCE` nvarchar
- `DATE_INSERTED` smalldatetime
- `INSERTED_BY` nvarchar
- `DATE_UPDATED` smalldatetime
- `UPDATED_BY` nvarchar
- `VALIDATION_GROUP` nvarchar
- `IGNORE_DURING_VALIDATION` bit

## dbo.GB_HIST_GCA_GRAIN
Columns:
- `PROJECT` nvarchar
- `SITE_ID` nvarchar
- `GRAIN_SIZE_1` nvarchar
- `GRAIN_SIZE_2` nvarchar
- `GRAIN_SIZE_3` nvarchar
- `GRAIN_SIZE_4` nvarchar
- `GRAIN_SIZE_5` nvarchar
- `GRAIN_SHAPE_1` nvarchar
- `GRAIN_SHAPE_2` nvarchar
- `GRAIN_SHAPE_3` nvarchar
- `GRAIN_SHAPE_4` nvarchar
- `GRAIN_SHAPE_5` nvarchar
- `GRAIN_SHAPE_6` nvarchar
- `COMMENTS` nvarchar
- `DATA_SOURCE` nvarchar
- `DATE_INSERTED` smalldatetime
- `INSERTED_BY` nvarchar
- `DATE_UPDATED` smalldatetime
- `UPDATED_BY` nvarchar
- `VALIDATION_GROUP` nvarchar
- `IGNORE_DURING_VALIDATION` bit

## dbo.GB_HIST_GR_SN
Columns:
- `PROJECT` nvarchar
- `SITE_ID` nvarchar
- `DEPTH_FROM` decimal
- `DEPTH_TO` decimal
- `SAMPLE_ID` nvarchar
- `LAYER_NO` smallint
- `WEIGHT_TOTAL` decimal
- `GR_SN` decimal
- `GR_SN_TAKS` decimal
- `TDH_TAKS` decimal
- `COMMENTS` nvarchar
- `DATA_SOURCE` nvarchar
- `DATE_INSERTED` smalldatetime
- `INSERTED_BY` nvarchar
- `DATE_UPDATED` smalldatetime
- `UPDATED_BY` nvarchar
- `VALIDATION_GROUP` nvarchar
- `IGNORE_DURING_VALIDATION` bit

## dbo.GB_HIST_XRF
Columns:
- `PROJECT` nvarchar
- `SITE_ID` nvarchar
- `DEPTH_FROM` decimal
- `DEPTH_TO` decimal
- `SN_PCT_XRF_PORT` float
- `ZN_PCT_XRF_PORT` float
- `PB_PCT_XRF_PORT` float
- `SN_PPM` float
- `FE_PPM` float
- `MN_PPM` float
- `TI_PPM` float
- `AS_PPM` float
- `PB_PPM` float
- `CU_PPM` float
- `W_PPM` float
- `ZN_PPM` float
- `P_PPM` float
- `CA_PPM` float
- `K_PPM` float
- `S_PPM` float
- `INSTRUMENT` nvarchar
- `LITHOLOGY` nvarchar
- `WEATHERING` nvarchar
- `ALT_INTENSITY` nvarchar
- `ALT_GROUP` nvarchar
- `MINZ_STYLE` nvarchar
- `COMMENTS` nvarchar
- `DATA_SOURCE` nvarchar
- `DATE_INSERTED` smalldatetime
- `DATE_UPDATED` smalldatetime
- `INSERTED_BY` nvarchar
- `UPDATED_BY` nvarchar
- `VALIDATION_GROUP` nvarchar
- `IGNORE_DURING_VALIDATION` bit

## dbo.GB_INTERVAL
Columns:
- `PROJECT` nvarchar
- `SITE_ID` nvarchar
- `INTERVAL_SEQ` int
- `PARENT_INTERVAL` int
- `DEPTH_FROM` decimal
- `DEPTH_TO` decimal
- `INTERVAL_TYPE` nvarchar
- `DATE_INSERTED` smalldatetime
- `INSERTED_BY` nvarchar
- `DATE_UPDATED` smalldatetime
- `UPDATED_BY` nvarchar
- `DATA_SOURCE` nvarchar
- `VALIDATION_GROUP` nvarchar
- `IGNORE_DURING_VALIDATION` bit

## dbo.GB_INTERVAL_ATTRIBUTE
Columns:
- `PROJECT` nvarchar
- `SITE_ID` nvarchar
- `INTERVAL_SEQ` int
- `ATTRIBUTE_SEQ` int
- `ATTR_TYPE` nvarchar
- `ATTR_NAME` nvarchar
- `TEXT_VALUE` nvarchar
- `NUM_VALUE` float
- `DATE_VALUE` datetime
- `DATE_INSERTED` smalldatetime
- `INSERTED_BY` nvarchar
- `DATE_UPDATED` smalldatetime
- `UPDATED_BY` nvarchar
- `DATA_SOURCE` nvarchar
- `VALIDATION_GROUP` nvarchar
- `IGNORE_DURING_VALIDATION` bit

## dbo.GB_INTERVAL_IMAGE
Columns:
- `PROJECT` nvarchar
- `SITE_ID` nvarchar
- `IMAGE_NUMBER` int
- `DEPTH_FROM` decimal
- `DEPTH_TO` decimal
- `IMAGE_FILE` nvarchar
- `IMAGE_BLOB` image
- `DATA_SOURCE` nvarchar
- `DATE_INSERTED` smalldatetime
- `INSERTED_BY` nvarchar
- `DATE_UPDATED` smalldatetime
- `UPDATED_BY` nvarchar
- `VALIDATION_GROUP` nvarchar
- `IGNORE_DURING_VALIDATION` bit
- `CROP_UPPER` float
- `CROP_LOWER` float
- `IMAGE_FROM` decimal
- `IMAGE_TO` decimal
- `IMAGERY_TYPE` nvarchar
- `IMAGE_TYPE` nvarchar
- `IMAGE_RESOLUTION` nvarchar
- `IMAGE_RESOLUTION_TYPE` nvarchar
- `PANORAMA_IMAGE_ID` uniqueidentifier

## dbo.GB_LITHOLOGY
Columns:
- `PROJECT` nvarchar
- `SITE_ID` nvarchar
- `DEPTH_FROM` decimal
- `DEPTH_TO` decimal
- `ROCK_TYPE` nvarchar
- `LITHOLOGY` nvarchar
- `COLOUR` nvarchar
- `TEXTURE` nvarchar
- `STRUCTURE` nvarchar
- `GRAIN_SIZE` nvarchar
- `GRAIN_SHAPE` nvarchar
- `WATER_PRESSURE` smallint
- `STICKINESS` nvarchar
- `RECOVERY_M` decimal
- `TIME_STARTED` time
- `TIME_ENDED` time
- `LOGGER` nvarchar
- `LOGGER_DATE` smalldatetime
- `REMARKS` nvarchar
- `DATA_SOURCE` nvarchar
- `DATE_INSERTED` smalldatetime
- `INSERTED_BY` nvarchar
- `DATE_UPDATED` smalldatetime
- `UPDATED_BY` nvarchar
- `VALIDATION_GROUP` nvarchar
- `IGNORE_DURING_VALIDATION` bit


## dbo.GB_LKP_CODE
Columns:
- `CATEGORY` nvarchar
- `CODE` nvarchar
- `DESCRIPTION` nvarchar
- `ASSIGNED_VALUE` float
- `RANKING` int
- `SORT_ORDER` int
- `PATTERN_NO` int
- `CODE_SEQ` int
- `ACTIVE` bit
- `EXT_DESCRIPTION` nvarchar
- `CODE_GROUP` nvarchar
- `HISTORIC` char
- `BRUSH_COLOUR` nvarchar
- `BRUSH_STYLE` int
- `DATE_INSERTED` smalldatetime
- `INSERTED_BY` nvarchar
- `DATE_UPDATED` smalldatetime
- `UPDATED_BY` nvarchar
- `DATA_SOURCE` nvarchar

## dbo.GB_MINERALIZATION
Columns:
- `PROJECT` nvarchar
- `SITE_ID` nvarchar
- `DEPTH_FROM` decimal
- `DEPTH_TO` decimal
- `MIN_STYLE` nvarchar
- `APY_PCT` nvarchar
- `CAS_PCT` nvarchar
- `CPY_PCT` nvarchar
- `GAL_PCT` nvarchar
- `MAL_PCT` nvarchar
- `MN_PCT` nvarchar
- `MOB_PCT` nvarchar
- `PY_PCT` nvarchar
- `PYM_PCT` nvarchar
- `PYR_PCT` nvarchar
- `SPH_PCT` nvarchar
- `STN_PCT` nvarchar
- `WOL_PCT` nvarchar
- `COMMENTS` nvarchar
- `DATA_SOURCE` nvarchar
- `DATE_INSERTED` smalldatetime
- `DATE_UPDATED` smalldatetime
- `INSERTED_BY` nvarchar
- `UPDATED_BY` nvarchar
- `VALIDATION_GROUP` nvarchar
- `IGNORE_DURING_VALIDATION` bit

## dbo.GB_OXIDATION
Columns:
- `PROJECT` nvarchar
- `SITE_ID` nvarchar
- `DEPTH_FROM` decimal
- `DEPTH_TO` decimal
- `OXIDATION_STATE` tinyint
- `HEMATITE` tinyint
- `GOETHITE` tinyint
- `JAROSITE` tinyint
- `LIMONITE` tinyint
- `REMARKS` nvarchar
- `DATA_SOURCE` nvarchar
- `DATE_INSERTED` smalldatetime
- `INSERTED_BY` nvarchar
- `DATE_UPDATED` smalldatetime
- `UPDATED_BY` nvarchar
- `VALIDATION_GROUP` nvarchar
- `IGNORE_DURING_VALIDATION` bit


## dbo.GB_REFERENCE_DENSITY
Columns:
- `MINERAL` nvarchar
- `DENSITY` decimal
- `COMMENTS` nvarchar
- `DATA_SOURCE` nvarchar
- `DATE_INSERTED` smalldatetime
- `INSERTED_BY` nvarchar
- `DATE_UPDATED` smalldatetime
- `UPDATED_BY` nvarchar
- `VALIDATION_GROUP` nvarchar
- `IGNORE_DURING_VALIDATION` bit

## dbo.GB_RQD
Columns:
- `PROJECT` nvarchar
- `SITE_ID` nvarchar
- `DEPTH_FROM` decimal
- `DEPTH_TO` decimal
- `BIT_SIZE` nvarchar
- `RECOVERY_M` decimal
- `RQD_10cm` decimal
- `WEATHERING` nvarchar
- `STRENGTH` nvarchar
- `ORIENTATION_METHOD` nvarchar
- `STICK_UP` decimal
- `CORE_LOSS_FROM` decimal
- `CORE_LOSS_TO` decimal
- `SHIFT` nvarchar
- `CORE_TECHNICIAN` nvarchar
- `DATA_SOURCE` nvarchar
- `DATE_INSERTED` smalldatetime
- `DATE_UPDATED` smalldatetime
- `INSERTED_BY` nvarchar
- `UPDATED_BY` nvarchar
- `VALIDATION_GROUP` nvarchar
- `IGNORE_DURING_VALIDATION` bit

## dbo.GB_SAMPLE
Columns:
- `PROJECT` nvarchar
- `SITE_ID` nvarchar
- `SAMPLE_ID` nvarchar
- `DEPTH_FROM` decimal
- `DEPTH_TO` decimal
- `QC_TYPE` nvarchar
- `EXCLUDE` bit
- `PREFERRED` bit
- `SAMPLE_TYPE` nvarchar
- `SAMPLE_METHOD` nvarchar
- `PARENT_SAMPLE_ID` nvarchar
- `STANDARD_ID` nvarchar
- `FIELD_PREP` nvarchar
- `MASS` float
- `SAMPLER` nvarchar
- `DATE_SAMPLED` smalldatetime
- `HISTORIC_SAMPLE_ID` nvarchar
- `DATA_SOURCE` nvarchar
- `DESCRIPTION` nvarchar
- `DATE_INSERTED` smalldatetime
- `INSERTED_BY` nvarchar
- `DATE_UPDATED` smalldatetime
- `UPDATED_BY` nvarchar
- `VALIDATION_GROUP` nvarchar
- `IGNORE_DURING_VALIDATION` bit
- `CORE_SIZE` nvarchar
- `FIELD_SPLIT_METHOD` nvarchar
- `SAMPLE_TREATMENT_1` nvarchar
- `SAMPLE_TREATMENT_2` nvarchar
- `SAMPLE_TREATMENT_3` nvarchar
- `SAMPLE_TREATMENT_4` nvarchar

## dbo.GB_SAMPLE_CHECK
Columns:
- `PROJECT` nvarchar
- `SITE_ID` nvarchar
- `SAMPLE_ID` nvarchar
- `PARENT_SAMPLE_ID` nvarchar
- `QC_TYPE` nvarchar
- `EXCLUDE` bit
- `PREFERRED` bit
- `SAMPLE_TYPE` nvarchar
- `SAMPLE_METHOD` nvarchar
- `FIELD_PREP` nvarchar
- `MASS` float
- `SAMPLER` nvarchar
- `DATE_SAMPLED` smalldatetime
- `HISTORIC_SAMPLE_ID` nvarchar
- `DESCRIPTION` nvarchar
- `DATA_SOURCE` nvarchar
- `DATE_INSERTED` smalldatetime
- `INSERTED_BY` nvarchar
- `DATE_UPDATED` smalldatetime
- `UPDATED_BY` nvarchar
- `VALIDATION_GROUP` nvarchar
- `IGNORE_DURING_VALIDATION` bit
- `CORE_SIZE` nvarchar
- `FIELD_SPLIT_METHOD` nvarchar
- `SAMPLE_TREATMENT_1` nvarchar
- `SAMPLE_TREATMENT_2` nvarchar
- `SAMPLE_TREATMENT_3` nvarchar
- `SAMPLE_TREATMENT_4` nvarchar

## dbo.GB_SAMPLE_QAQC
Columns:
- `PROJECT` nvarchar
- `SITE_ID` nvarchar
- `SAMPLE_ID` nvarchar
- `QC_TYPE` nvarchar
- `STANDARD_ID` nvarchar
- `EXCLUDE` bit
- `DATA_SOURCE` nvarchar
- `DATE_INSERTED` smalldatetime
- `DATE_UPDATED` smalldatetime
- `INSERTED_BY` nvarchar
- `UPDATED_BY` nvarchar
- `VALIDATION_GROUP` nvarchar
- `IGNORE_DURING_VALIDATION` bit
- `CORE_SIZE` nvarchar
- `FIELD_SPLIT_METHOD` nvarchar
- `SAMPLE_TREATMENT_1` nvarchar
- `SAMPLE_TREATMENT_2` nvarchar
- `SAMPLE_TREATMENT_3` nvarchar
- `SAMPLE_TREATMENT_4` nvarchar

## dbo.GB_SITE
Columns:
- `PROJECT` nvarchar
- `SITE_ID` nvarchar
- `IUP` nvarchar
- `AREA` nvarchar
- `LOCATION` nvarchar
- `PROSPECT` nvarchar
- `CNS` nvarchar
- `DEPOSIT_TYPE` nvarchar
- `CREW` nvarchar
- `PURPOSE` nvarchar
- `MINE_STATUS` nvarchar
- `PERCENT_TAILING` decimal
- `DATE_STARTED` smalldatetime
- `DATE_COMPLETED` smalldatetime
- `END_DEPTH` decimal
- `BIT_COEFFICIENT` decimal
- `SYMBOL_TB` int
- `SYMBOL_TB_ATAS` int
- `ANALYSIS_METHOD` nvarchar
- `KOLONG_NAME` nvarchar
- `KONG` nvarchar
- `RIG_TYPE` nvarchar
- `WELLSITE_GEOS` nvarchar
- `CONTRACTOR` nvarchar
- `COMMENTS` nvarchar
- `DATA_SOURCE` nvarchar
- `DATE_INSERTED` smalldatetime
- `INSERTED_BY` nvarchar
- `DATE_UPDATED` smalldatetime
- `UPDATED_BY` nvarchar
- `VALIDATION_GROUP` nvarchar
- `IGNORE_DURING_VALIDATION` bit
- `SITE_ID_HIST` nvarchar
- `SYMBOL` int
- `SITE_STATUS` nvarchar
- `STATUS_SET_BY` nvarchar
- `STATUS_SET_DATE` smalldatetime
- `STATUS_COMMENT` nvarchar

## dbo.GB_SITE_SURVEY
Columns:
- `PROJECT` nvarchar
- `SITE_ID` nvarchar
- `INSTANCE` smallint
- `RANKING` smallint
- `EXCLUDE` bit
- `PREFERRED` bit
- `SURVEY_TYPE` nvarchar
- `SURVEY_METHOD` nvarchar
- `DATE_SURVEYED` smalldatetime
- `COORDSYS` nvarchar
- `EASTING` float
- `NORTHING` float
- `ELEVATION` float
- `DATA_SOURCE` nvarchar
- `DATE_INSERTED` smalldatetime
- `SURVEYED_BY` nvarchar
- `INSERTED_BY` nvarchar
- `DATE_UPDATED` smalldatetime
- `UPDATED_BY` nvarchar
- `VALIDATION_GROUP` nvarchar
- `IGNORE_DURING_VALIDATION` bit


## dbo.GB_VEIN
Columns:
- `PROJECT` nvarchar
- `SITE_ID` nvarchar
- `DEPTH` decimal
- `WIDTH_CM` decimal
- `VEIN_STYLE` nvarchar
- `VEIN_TYPE_1` nvarchar
- `VEIN_TEXTURE_1` nvarchar
- `VEIN_PCT_1` nvarchar
- `VEIN_TYPE_2` nvarchar
- `VEIN_TEXTURE_2` nvarchar
- `VEIN_PCT_2` nvarchar
- `VEIN_TYPE_3` nvarchar
- `VEIN_TEXTURE_3` nvarchar
- `VEIN_PCT_3` nvarchar
- `REMARKS` nvarchar
- `DATA_SOURCE` nvarchar
- `DATE_INSERTED` smalldatetime
- `INSERTED_BY` nvarchar
- `DATE_UPDATED` smalldatetime
- `UPDATED_BY` nvarchar
- `VALIDATION_GROUP` nvarchar
- `IGNORE_DURING_VALIDATION` bit

## dbo.VW_ST_RESULT_ROUTINE_PIVOT
Columns:
- `PROJECT` nvarchar
- `SITE_ID` nvarchar
- `SAMPLE_ID` nvarchar
- `DEPTH_FROM` decimal
- `DEPTH_TO` decimal
- `Bi` float
- `As` float
- `Ce` float
- `Cu` float
- `La` float
- `Pb` float
- `Sn` float
- `Th` float
- `U` float
- `W` float
- `Zn` float
- `Zr` float
- `Ag` float
- `Ba` float
- `Br` float
- `CaO` float
- `Cd` float
- `Co` float
- `Cr` float
- `Cs` float
- `Fe2O3` float
- `Ga` float
- `Ge` float
- `Hf` float
- `Hg` float
- `I` float
- `Mn` float
- `Mo` float
- `Nb` float
- `Nd` float
- `Ni` float
- `Rb` float
- `Sb` float
- `Sc` float
- `Se` float
- `Sm` float
- `Sr` float
- `Ta` float
- `Te` float
- `TiO2` float
- `Tl` float
- `V` float
- `Y` float
- `Yb` float

## dbo.VW_ST_RESULT_STANDARD_DATA
Columns:
- `DESPATCH_ID` nvarchar
- `SAMPLE_TAG` nvarchar
- `DESPATCH_PROJECT` nvarchar
- `DESPATCH_SITE_ID` nvarchar
- `DESPATCH_SAMPLE_ID` nvarchar
- `DESPATCH_QC_TYPE` nvarchar
- `QC_SOURCE` nvarchar
- `LAB_JOB_NO` nvarchar
- `LAB_METHOD` nvarchar
- `LAB_ELEMENT` nvarchar
- `EXCLUDE` bit
- `TEXT_RULE` nvarchar
- `LAB_RESULT_TEXT` nvarchar
- `LAB_RESULT_NUMERIC` float
- `LAB_UNITS` nvarchar
- `RESULT` float
- `PARENT_DESPATCH_ID` nvarchar
- `DESPATCH_DESCRIPTION` nvarchar
- `LAB_ID` nvarchar
- `STATUS` nvarchar
- `SEND_DATE` smalldatetime
- `DESPATCH_DELIVERY_METHOD` nvarchar
- `DESPATCH_PERSON` nvarchar
- `CONSIGNMENT_NOTE` nvarchar
- `DESPATCH_REMARKS` nvarchar
- `LAB_DESCRIPTION` nvarchar
- `RECEIPT_DATE` smalldatetime
- `LAB_DATE` smalldatetime
- `RECEIPT_DELIVERY_METHOD` nvarchar
- `INPUT_FILE` nvarchar
- `RECEIPT_PERSON` nvarchar
- `INVOICE_NUMBER` nvarchar
- `INVOICE_AMOUNT` float
- `RECEIPT_CURRENCY_UNIT` nvarchar
- `COST_CODE` nvarchar
- `RECEIPT_REMARKS` nvarchar
- `RANKING` smallint
- `UNITS` nvarchar
- `UPPER_LIMIT` float
- `DETECTION_LIMIT` float
- `ANALYSIS_PRECISION` smallint
- `COST` float
- `COMBO_CURRENCY_UNIT` nvarchar
- `SUBST_LAB_ID` nvarchar
- `PIVOT_VIEW` bit
- `ELEMENT` nvarchar
- `REPEAT` int
- `LAB_ELEMENT_DESCRIPTION` nvarchar
- `ELEMENT_DESCRIPTION` nvarchar
- `NOMINATED_UNITS` nvarchar
- `ELEMENT_GROUP` nvarchar
- `GENERIC_METHOD` nvarchar
- `LAB_DIGEST` nvarchar
- `LAB_DETERMINATION` nvarchar
- `LAB_METHOD_REMARKS` nvarchar
- `DIGEST` nvarchar
- `DETERMINATION` nvarchar
- `GENERIC_METHOD_DESCRIPTION` nvarchar
- `NOMINAL_VALUE_UNITS` nvarchar
- `NOMINAL_VALUE` float
- `STD_DEVIATION` float
- `DESPATCH_STANDARD_ID` nvarchar

## dbo.VW_ST_STANDARD_VS_NOMINAL
Columns:
- `STANDARD_ID` nvarchar
- `SAMPLE_TAG` nvarchar
- `DESPATCH_ID` nvarchar
- `SEND_DATE` smalldatetime
- `LAB_ID` nvarchar
- `RECEIPT_DATE` smalldatetime
- `ELEMENT` nvarchar
- `LAB_METHOD` nvarchar
- `GENERIC_METHOD` nvarchar
- `RESULT` float
- `NOMINATED_UNITS` nvarchar
- `NOMINAL_VALUE` float
- `NOMINAL_VALUE_UNITS` nvarchar
- `STD_DEVIATION` float
- `SD_UPPER_1` float
- `SD_UPPER_2` float
- `SD_UPPER_3` float
- `SD_LOWER_1` float
- `SD_LOWER_2` float
- `SD_LOWER_3` float
- `NOMINAL_10_PERCENT_UP` float
- `NOMINAL_20_PERCENT_UP` float
- `NOMINAL_30_PERCENT_UP` float
- `NOMINAL_10_PERCENT_DOWN` float
- `NOMINAL_20_PERCENT_DOWN` float
- `NOMINAL_30_PERCENT_DOWN` float
