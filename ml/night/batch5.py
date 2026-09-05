"""Пачка 5: больше обучающих данных (rounds=15) + усреднение по сидам.

Мультисид — самый надёжный способ снять последние доли процента: разброс между
сидами сопоставим с разницей между конфигурациями, и усреднение его гасит.
"""
FAIR = {"learning_rate": 0.02, "objective": "fair"}
CONFIGS = [
    {"name": "r15_lr02_fair", "params": FAIR, "n_estimators": 2500},
    {"name": "r15_lr02", "params": {"learning_rate": 0.02}, "n_estimators": 2500},
    {"name": "r15_noharm_fair", "drop_features": ["harm"], "params": FAIR, "n_estimators": 2500},
    {"name": "r15_baseline"},
]
