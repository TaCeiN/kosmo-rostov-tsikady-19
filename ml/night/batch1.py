"""Пачка 1: базовая линия, лоссы, остаточное обучение, чистка битых строк."""
CONFIGS = [
    # опорная точка — должна воспроизвести ~0.0784 из прогона пользователя
    {"name": "baseline"},

    # --- учить поправку к сглаживателю вместо самого NDVI
    {"name": "resid_whittaker", "target": "resid_whittaker"},
    {"name": "resid_savgol", "target": "resid_savgol"},
    {"name": "resid_lin", "target": "resid_lin"},

    # --- битые строки (|NDVI|>1) вон из обучения
    {"name": "drop_broken", "drop_broken": True},
    {"name": "resid_whit_drop", "target": "resid_whittaker", "drop_broken": True},

    # --- устойчивые лоссы: три строки-выброса тянут l2 на себя
    {"name": "huber", "params": {"objective": "huber", "alpha": 0.3}},
    {"name": "fair", "params": {"objective": "fair"}},
    {"name": "mae", "params": {"objective": "regression_l1"}},

    # --- скорость обучения и ёмкость
    {"name": "lr02_2500", "params": {"learning_rate": 0.02}, "n_estimators": 2500},
    {"name": "lr08_700", "params": {"learning_rate": 0.08}, "n_estimators": 700},
    {"name": "leaves127", "params": {"num_leaves": 127}},
    {"name": "leaves31", "params": {"num_leaves": 31}},
]
