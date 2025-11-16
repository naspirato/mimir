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

# Создание детектора с явным типом метрики
detector = UniversalTSDetectorV2(
    metric_kind="duration",
    direction="lower_is_better",
)

# Или с автоматическим определением типа
detector_auto = UniversalTSDetectorV2(
    metric_kind=None,  # Будет определен автоматически
    auto_detect_metric_type=True,
    metric_name_hint="login_time",  # Опциональный hint для лучшего определения
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

# Проверка автоматически определенного типа
for ctx, res in results.items():
    if "metric_type_detection" in res:
        detection = res["metric_type_detection"]
        print(f"Detected type: {detection['detected_type']}")
        print(f"Description: {detection['description']['name']}")
        print(f"Transformation: {detection['description']['transformation']}")

# Stateful алертинг
state_store = {}
engine = AlertEngineV2(state_store)

for ctx, res in results.items():
    alerts = engine.process(ctx, res)
    if alerts:
        print(f"Alerts for {ctx}: {alerts}")
```

## Поддерживаемые типы метрик

Система поддерживает 9 типов метрик с соответствующими трансформациями:

- **duration** / **latency** - log-transform (для времени выполнения)
- **error_rate** / **failure_rate** - logit-transform (для процентов ошибок)
- **count** / **rate** - square-root (для счетных данных)
- **throughput** / **capacity** - log-transform (для пропускной способности)
- **percentage** / **ratio** - arcsine-sqrt (для процентов и долей)
- **binary** / **boolean** - без трансформации (для бинарных метрик)
- **gaussian** / **normal** - без трансформации (для нормального распределения)
- **size** / **bytes** - log10-transform (для размеров)
- **other** / **generic** - без трансформации (универсальный тип)

Подробнее см. [RFC_mimir.md](RFC_mimir.md) раздел 2.2.

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

## Веб‑приложение (Flask)

Интерактивный UI для запуска по конфигу, скачивания данных, анализа и просмотра графиков (Plotly).

Запуск:

```bash
pip install -r requirements.txt
export FLASK_APP=flask_app.app
flask run
# или
python -m flask_app.app
```

Функции:
- выбор YAML‑конфига из `configs/`;
- скачивание датасета в `data/{config}/raw/` (`dataset.csv` или `dataset.jsonl`);
- анализ “live” (через адаптер) или по сохранённому датасету;
- браузер результатов по контекстам, графики сырых рядов и диагностик (debug в конфиге должен быть включён).

## Конфигурационный запуск (YAML)

Можно описать источник данных и параметры анализа в одном YAML и запустить анализ без кода.

Пример для CSV: `configs/example_csv.yaml`

```yaml
version: 1
dataset:
  adapter: csv
  adapter_config:
    path: examples/metrics_example.csv
    parse_dates: true
  timestamp_field: timestamp
  value_field: value
analysis:
  context_fields: [branch, build_type, testname]
  meta_fields: [commit]
  metrics:
    name: api_latency
    direction: lower_is_better
    metric_kind: duration
    auto_detect_metric_type: true
  event_types: [regression, improvement]
  output:
    debug: true
```

Запуск:

```python
from detector.run_from_config import run_from_file
results = run_from_file("configs/example_csv.yaml")
```

### Двухэтапный режим: скачать → анализировать

1) Скачивание данных по конфигу и сохранение на диск:

```python
from detector.run_from_config import load_config, fetch_dataset_to_file

cfg = load_config("configs/example_csv.yaml")
fetch_dataset_to_file(cfg, "dataset.csv", fmt="csv")  # или fmt=\"jsonl\"
```

2) Аналитика по сохранённым данным:

```python
from detector.run_from_config import analyze_from_saved

results = analyze_from_saved(cfg, "dataset.csv", fmt="csv")
```

## Подробная документация

См. [RFC_mimir.md](RFC_mimir.md) для полного описания архитектуры и требований.

## Лицензия

MIT
