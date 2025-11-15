# MiMiR

Продовый прототип универсального анализатора временных рядов с поддержкой:

- авто-диагностики ряда (регулярность, шум, сезонность);
- лог-трансформа для `duration` / latency;
- относительных изменений и robust z-score;
- CUSUM-подобного индикатора;
- опционального STL-десезонализирования (`statsmodels`);
- опционального поиска change-points (`ruptures`);
- multi-series анализа (`analyze_many`);
- stateful-алертинга с гистерезисом (`AlertEngineV2`);
- простых тестов через `pytest`;
- CI workflow для GitHub Actions.

## Установка

```bash
pip install -r requirements.txt
```

## Быстрый старт

```python
import pandas as pd
from detector import UniversalTSDetectorV2, AlertEngineV2

# Загрузка данных
df = pd.read_csv("metrics_example.csv")

# Создание детектора
detector = UniversalTSDetectorV2(
    metric_kind="duration",
    direction="lower_is_better",
)

# Анализ нескольких рядов
results = detector.analyze_many(
    df,
    context_fields=["branch", "build_type", "testname"],
    meta_fields=["commit"],
    value_field="value",
    timestamp_field="timestamp",
)

# Stateful алертинг
state_store = {}
engine = AlertEngineV2(state_store)

for ctx, res in results.items():
    alerts = engine.process(ctx, res)
    if alerts:
        print(f"Alerts for {ctx}: {alerts}")
```

## Структура проекта

```
mimir/
├── detector/          # Основной код детектора
├── examples/          # Примеры использования
├── tests/             # Тесты
└── .github/          # CI/CD workflows
```

## Тестирование

```bash
pytest tests/
```

## Подробная документация

См. [RFC_mimir.md](RFC_mimir.md) для полного описания архитектуры и требований.

## Лицензия

MIT
