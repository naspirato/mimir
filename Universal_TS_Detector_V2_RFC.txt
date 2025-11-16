
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
- metric_kind (duration, error_rate, binary_error, count, other)
- direction:
    - higher_is_better  (пример: throughput)
    - lower_is_better   (пример: latency, error_rate)

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
- лог-трансформ если metric_kind = duration:
  value := log1p(value)

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
