"""Пачка 2: те же конфигурации на расширенном наборе признаков (v2).

Сравнивать надо строго с baseline из этой же пачки — набор признаков другой.
"""
CONFIGS = [
    {"name": "v2_baseline"},
    {"name": "v2_fair", "params": {"objective": "fair"}},
    {"name": "v2_drop_broken", "drop_broken": True},
    {"name": "v2_fair_drop", "params": {"objective": "fair"}, "drop_broken": True},
    {"name": "v2_lr02", "params": {"learning_rate": 0.02}, "n_estimators": 2500},
    {"name": "v2_leaves127", "params": {"num_leaves": 127}},
    {"name": "v2_ff05", "params": {"feature_fraction": 0.5}},
    {"name": "v2_mindata15", "params": {"min_data_in_leaf": 15}},
    {"name": "v2_split_gap16", "split_gap": 16},
    {"name": "v2_w_gap", "weight": "gap"},
]
