"""Пачка 3: набор признаков v3 (годы-аналоги) + абляции.

Абляции нужны, чтобы понять, какая группа признаков реально несёт сигнал,
а какая просто занимает место — на защите про это спросят.
"""
CONFIGS = [
    {"name": "v3_baseline"},
    {"name": "v3_lr02", "params": {"learning_rate": 0.02}, "n_estimators": 2500},
    {"name": "v3_lr02_fair", "params": {"learning_rate": 0.02, "objective": "fair"},
     "n_estimators": 2500},
    {"name": "v3_lr02_drop", "params": {"learning_rate": 0.02}, "n_estimators": 2500,
     "drop_broken": True},
    {"name": "v3_lr015", "params": {"learning_rate": 0.015}, "n_estimators": 3500},
    {"name": "v3_lr02_md15", "params": {"learning_rate": 0.02, "min_data_in_leaf": 15},
     "n_estimators": 2500},

    # абляции: что будет, если убрать группу признаков
    {"name": "v3_abl_no_analog", "drop_features": ["analog"]},
    {"name": "v3_abl_no_date", "drop_features": ["date_anom", "clim_plus_date"]},
    {"name": "v3_abl_no_harm", "drop_features": ["harm"]},
    {"name": "v3_abl_no_smoothers", "drop_features": ["sm_", "whit_scale"]},
    {"name": "v3_abl_no_weather", "drop_features": ["temp_", "precip_", "gdd", "dry_", "heat_"]},
    {"name": "v3_abl_no_sensors", "drop_features": ["s2_", "landsat_", "modis_", "sensor_"]},
]
