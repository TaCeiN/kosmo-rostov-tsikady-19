"""Пачка 4: чистим набор от того, что абляции признали балластом, и добираем сидами."""
LR = {"learning_rate": 0.02}
FAIR = {"learning_rate": 0.02, "objective": "fair"}
CONFIGS = [
    {"name": "v4_noharm", "drop_features": ["harm"], "params": LR, "n_estimators": 2500},
    {"name": "v4_noharm_analog", "drop_features": ["harm", "analog"],
     "params": LR, "n_estimators": 2500},
    {"name": "v4_noharm_fair", "drop_features": ["harm"], "params": FAIR, "n_estimators": 2500},
    {"name": "v4_noharm_analog_fair", "drop_features": ["harm", "analog"],
     "params": FAIR, "n_estimators": 2500},
    {"name": "v4_lean_fair", "drop_features": ["harm", "analog", "sm_", "whit_scale"],
     "params": FAIR, "n_estimators": 2500},
    {"name": "v4_noharm_fair_md15",
     "drop_features": ["harm"], "params": {**FAIR, "min_data_in_leaf": 15},
     "n_estimators": 2500},
    {"name": "v4_noharm_fair_ff09", "drop_features": ["harm"],
     "params": {**FAIR, "feature_fraction": 0.9}, "n_estimators": 2500},
    {"name": "v4_noharm_fair_l2_5", "drop_features": ["harm"],
     "params": {**FAIR, "lambda_l2": 5.0}, "n_estimators": 2500},
]
