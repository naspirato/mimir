
RFC: Universal Time-Series Detector V2
Version: 0.7
Status: Draft
Author: ChatGPT & User

============================================================
1. PURPOSE
============================================================
Цель — создать универсальную систему анализа временных рядов,
способную автоматически определять:

- улучшение (improvement)
- ухудшение (regression)
- стабильное состояние (stable)

Причём:
- момент начала события,
- силу изменения,
- риск,
- контекст (branch, build_type, testname),
- мета-поля (commit),
- работу в исследовательском режиме (debug timeline),
- работу в продовом режиме (stateful alerting c гистерезисом).

Система должна работать как для 10 точек, так и для 10 000.

============================================================
2. REQUIREMENTS — FUNCTIONAL
============================================================

2.1 Input requirements
----------------------
Система принимает:
- DataFrame (CSV или SQL)
- Поля времени: timestamp
- Значения ряда: value
- Поля контекста (например branch, build_type, testname)
- Meta-поля (например commit)

DataFrame должен позволять группировать несколько рядов.

2.2 Metric type
---------------
Каждая серия имеет:
- metric_kind: тип метрики, определяющий стратегию трансформации
- direction:
    - higher_is_better  (пример: throughput)
    - lower_is_better   (пример: latency, error_rate)

Поддерживаемые типы метрик:

**duration / latency**
- Описание: Время выполнения, задержки, длительность операций
- Примеры: `login_time`, `api_response_time`, `query_duration`, `rendering_time`
- Трансформация: log-transform (log1p)
- Причина: Правостороннее распределение с длинным хвостом
- Direction: обычно `lower_is_better`
- Типичный диапазон: миллисекунды - секунды

**error_rate / failure_rate**
- Описание: Процент ошибок, доля неудачных запросов (0-1 или 0-100%)
- Примеры: `error_rate`, `failure_percentage`, `crash_rate`, `timeout_rate`
- Трансформация: logit-transform (стабилизирует дисперсию для биномиального распределения)
- Причина: Ограниченный диапазон, биномиальное распределение
- Direction: `lower_is_better`
- Типичный диапазон: [0, 1] или [0, 100%]

**count / rate**
- Описание: Количество событий в единицу времени, частота
- Примеры: `request_count`, `events_per_second`, `page_views`, `transactions_per_hour`
- Трансформация: square-root (стабилизирует дисперсию для пуассоновских данных)
- Причина: Счетные данные, дисперсия пропорциональна среднему
- Direction: зависит от контекста
- Типичный диапазон: неотрицательные целые числа

**throughput / capacity**
- Описание: Пропускная способность, производительность
- Примеры: `requests_per_second`, `throughput`, `bandwidth`, `qps`
- Трансформация: log-transform (log1p) для стабилизации дисперсии
- Причина: Часто правостороннее распределение, вариативность растет с ростом
- Direction: `higher_is_better`
- Типичный диапазон: положительные значения

**percentage / ratio**
- Описание: Проценты, доли, соотношения (0-1 или 0-100%)
- Примеры: `cpu_usage_percent`, `memory_usage`, `cache_hit_ratio`, `success_rate`
- Трансформация: arcsine-sqrt (arcsine transformation) или logit
- Причина: Ограниченный диапазон, стабилизация дисперсии на границах
- Direction: зависит от метрики
- Типичный диапазон: [0, 1] или [0, 100%]

**binary / boolean**
- Описание: Бинарные метрики (0/1), наличие/отсутствие события
- Примеры: `is_error`, `test_passed`, `feature_enabled`, `health_check`
- Трансформация: без трансформации (требует агрегации)
- Причина: Дискретные значения, требуют агрегации по окну
- Direction: `lower_is_better` (для ошибок), `higher_is_better` (для успехов)
- Типичный диапазон: 0 или 1

**gaussian / normal**
- Описание: Метрики с приблизительно нормальным распределением
- Примеры: `temperature`, `cpu_load`, `balanced_score`, `normalized_metric`
- Трансформация: без трансформации (или Z-score normalization)
- Причина: Симметричное распределение, стабильная дисперсия
- Direction: зависит от контекста
- Типичный диапазон: любой диапазон

**size / bytes**
- Описание: Размеры файлов, памяти, данных
- Примеры: `file_size`, `memory_usage_bytes`, `payload_size`, `database_size`
- Трансформация: log-transform (log10) для больших значений
- Причина: Правостороннее распределение, большие разбросы значений
- Direction: обычно `lower_is_better` (для оптимизации)
- Типичный диапазон: байты, килобайты, мегабайты

**other / generic**
- Описание: Общий тип для неизвестных метрик
- Примеры: любые метрики без специфической обработки
- Трансформация: без трансформации (или auto-detect на основе статистики)
- Причина: Универсальность, минимальная обработка
- Direction: указывается явно
- Типичный диапазон: любой диапазон

Автоматическое определение типа:
- Система может автоматически определять тип метрики на основе статистических характеристик:
  * Диапазон значений (bounded/unbounded)
  * Распределение (skewness, kurtosis)
  * Тип значений (integer-like, binary)
  * Отношение дисперсии к среднему (для пуассоновских данных)
- Автоопределение можно включить через `auto_detect_metric_type=True`
- Можно предоставить hint через `metric_name_hint` для улучшения определения
- Пользователь может проверить определенный тип в результатах анализа через `metric_type_detection`

2.3 Multi-series handling
-------------------------
- автоматически выделять уникальные комбинации context_fields
- над каждой комбинацией выполнять анализ независимо
- отдавать структурированный JSON-like результат

2.4 Result structure for each series
------------------------------------
Каждая серия возвращает:
- context (branch/test/etc)
- meta_last (commit)
- detector_result:
    - state (stable/regression/improvement)
    - z_score
    - rel_change
    - severity
    - risk
    - confidence
    - change_point
- debug (если включён) содержащий:
    - raw_series
    - signal (после лог/seasonal corrections)
    - smoothed short/long
    - rel
    - z
    - CUSUM
    - meta timeline

2.5 "Now state" detection
-------------------------
Система должна уметь ответить:
"Сейчас мы где?"
- В стабильной фазе?
- В фазе регрессии?
- В фазе улучшения?

2.6 Change-point detection
--------------------------
Система определяет:
- когда началось текущее улучшение/ухудшение

Методы:
- robust z-threshold
- CUSUM
- ruptures (если доступно)

2.7 Research mode
-----------------
Выводит ВСЕ временные ряды для визуализации (plotly):
- raw
- signal
- short
- long
- rel
- z
- cusum_pos
- cusum_neg
- meta timeline

2.8 CI / PROD режим
-------------------
Поддержка stateful alerting:
- хранить состояние между прогонами
- поддержка гистерезиса:
    - min_risk_start
    - min_risk_end
    - min_persist_start
    - min_persist_end
- генерировать:
    - start события
    - end события
    - смена режима improvement↔regression

============================================================
3. HIGH-LEVEL PIPELINE
============================================================

Mermaid диаграмма v1 (первоначальная):

```mermaid
flowchart TD
    A[Сырые данные] --> B[Очистка / Удаление выбросов]
    B --> C[Нормализация / Лог-трансформ]
    C --> D[Десезонализация (STL)]
    D --> E[Сглаживание (EWMA short/long)]
    E --> F[Относительное изменение short-long]
    F --> G[Robust Z-score по rel]
    G --> H[CUSUM]
    H --> I[Опционально Ruptures Change-point]
    I --> J[State Classification]
    J --> K[Расчет severity/confidence/risk]
    K --> L[Stateful Alerting + Hysteresis]
    L --> M[Результаты для визуализации / CI]
```

============================================================
4. DETAILED PIPELINE
============================================================

4.1 Preprocessing
-----------------
- сортировка по timestamp
- удаление NaN
- трансформация согласно metric_kind:
  - duration: log-transform (log1p)
  - error_rate: logit-transform
  - count: square-root transform
  - throughput: log-transform (log1p)
  - percentage: arcsine-sqrt transform
  - binary: без трансформации (требует агрегации)
  - gaussian: без трансформации
  - size: log10-transform
  - other: без трансформации (или auto-detect)

4.2 Seasonality removal
-----------------------
Если доступен statsmodels:
- делаем STL(period=k)
- берём trend + resid

4.3 EWMA smoothing
------------------
- short = EWM(window_short)
- long = EWM(window_long)

window_short, window_long выбираются автоматически:
- small series: small windows
- long series: longer windows

4.4 Relative change
-------------------
rel = (short - long) / (|long| + eps)

4.5 Robust Z
------------
median = rel.median()
MAD = median(|rel - median|)

z = (rel - median) / MAD

Интерпретация:
- |z| < z_stable_threshold → stable
- z > 0 → improvement (if direction higher_is_better)
- z < 0 → improvement (if direction lower_is_better)

4.6 Simple CUSUM
----------------
Ведём два накопителя:
- cpos = max(0, previous + z - k)
- cneg = min(0, previous + z + k)

4.7 Ruptures (optional)
-----------------------
Если установлен ruptures:
- применяем Binseg(L2)
- ограничиваемся 3 breakpoints
- берём последний как candidate change point

4.8 State decision
------------------
Rules:

IF |z_last| < 0.8 → state = stable  
ELSE:  
  IF direction = higher_is_better:
        rel_last > 0 → improvement  ELSE → regression
  IF direction = lower_is_better:
        rel_last < 0 → improvement  ELSE → regression

4.9 Severity & Risk
-------------------
severity = min(1, |z| / 2.5)  
confidence = 0.5 + 0.5 * severity  
risk = severity * confidence

============================================================
5. STATEFUL ALERT ENGINE V2
============================================================

Цель: не спамить алертами при продолжающейся регрессии.

Используем hysteresis:

- min_risk_start = 0.6
- min_risk_end = 0.2
- min_persist_start = 2
- min_persist_end = 2

Логика:

prev_state = stable
now_state = regression
count >= min_persist_start
risk >= min_risk_start

→ emit START regression

Когда регрессия заканчивается:

prev_state = regression
now_state = stable
count >= min_persist_end
risk <= min_risk_end

→ emit END regression

Если произошла смена improvement <-> regression, делаем:
- END previous
- START new

Состояние хранится в JSON:

{
  "branch=main|build=release|test=login": {
    "last_state": "...",
    "same_state_count": ...,
    "last_change_point": "...",
    "last_commit": "..."
  }
}

============================================================
6. MULTI-SERIES FRAMEWORK
============================================================

Один DataFrame может содержать много рядов.

context_fields определяют уникальную серию:
- branch
- build_type
- testname

meta_fields передаются внутрь результата:
commit_last: commit для последней точки

analyze_many:
- группируем df.groupby(context_fields)
- каждую серию прогоняем через analyze()
- собираем dict:
  {
    (branch, build_type, testname): result
  }

============================================================
7. DEBUG MODE
============================================================

При debug=True возвращаются временные ряды:
- raw_series
- signal
- short
- long
- rel
- z
- cusum_pos
- cusum_neg
- meta timeline

Эти данные позволяют построить Plotly графики.

============================================================
8. GITHUB ACTIONS WORKFLOW
============================================================

Pipeline:
- checkout
- pip install -r requirements.txt
- pytest
- run example
- сохранить alert_state.json

============================================================
9. FUTURE WORK
============================================================

- SLA-aware режим (normal/near_breach/breach)
- Автокалибровка порогов
- Многомерные метрики → интегральный health score
- Автоматическая оптимизация окон
- ML-based regimes classification

============================================================
END OF RFC
============================================================
