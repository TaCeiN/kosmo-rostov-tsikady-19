"""Пачка 7: rounds=25 — проверяем, не вышли ли на плато по объёму обучающих данных."""
CONFIGS = [
    {"name": "r25_lr02", "params": {"learning_rate": 0.02}, "n_estimators": 2500},
    {"name": "r25_lr02_fair", "params": {"learning_rate": 0.02, "objective": "fair"},
     "n_estimators": 2500},
    {"name": "r25_lr015_3500", "params": {"learning_rate": 0.015}, "n_estimators": 3500},
]
