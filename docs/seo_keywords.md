# 🔑 Ключевые слова для WinVosk

Разбито по кластерам и интенту. Английский + русский. Подходит для SEO, ASO,
контент-маркетинга, PPC.

> **Проверено автодополнением, 2026-10.** Каждый кластер помечен вердиктом:
> `TARGET` — целимся в выдачу, `CONTENT` — годится только как формулировка в
> тексте, `DROP` — мёртвый или чужой запрос. Метод и его ограничения — в
> § «Как это проверено».

---

## 0. Что изменилось и почему

Предыдущая версия файла была написана под **whisper-based** продукт. WinVosk
использует **Vosk/Kaldi**: 44 МБ модель, CPU, без CUDA, без BYOK, без подписки.
Из этого следует всё остальное:

- Кластер `whisper dictation *` **остаётся целевым**, но не как «мы на whisper»,
  а как вход в категорию: «whisper alternatives», «free/local whisper
  alternative». Говорить «мы whisper» нельзя — это проверяемо и ломает доверие.
- `faster-whisper`, `whisper.cpp`, `whisper large v3`, `CUDA/GPU accelerated
  whisper` — **DROP**, другой движок. Люди ищут, мы не отвечаем.
- Появились кластеры, которых в файле не было: **размер модели**, **open
  source**, **свои слова**, **Vosk-модели**. Это ровно то, чем WinVosk
  отличается, и по этим словам конкуренты не стоят.

## 0.1. Сводка приоритета

| Ранг | EN-кластер | RU-кластер | Куда |
|---|---|---|---|
| 1 | `whisper alternatives 2026`, `free/local/open source whisper alternative` | `аналог wispr flow` | Title / H1 |
| 2 | `aqua voice open source alternative`, `superwhisper for windows`, `macwhisper for windows` | `программа для диктовки текста на компьютер` | Title / H1 / лендинг |
| 3 | `wispr flow alternative open source/local/free` | `набор текста голосом на компьютере` | Лендинг |
| 4 | `offline voice dictation`, `offline dictation app/software for windows` | `голосовой ввод windows 11 на русском` | Лендинг / meta |
| 5 | `open source voice dictation software`, `open source voice typing` | `офлайн распознавание речи` (+`vosk`) | Meta / блог |
| 6 | `small speech to text model`, `speech to text custom vocabulary` | `диктовка на русском`, `диктовка в ворде на русском` | Блог / ASO |
| 7 | `voice typing not working windows 11` (воронка замены) | `диктовка текста на русском` | Блог-статья |

---

## 1. 🏆 Конкурентные запросы — ранг 1 и 2

Самая плотная и самая платёжеспособная зона. Всё это ** unmet need**: у
конкурентов нет Windows-версии, бесплатной версии или открытого кода.

**EN — `TARGET`:**
- whisper alternatives 2026
- whisper alternatives
- free whisper alternative
- local whisper alternative
- whisper alternative app
- whisper alternatives open source
- whisper alternatives reddit
- aqua voice open source alternative ← **лучший одиночный запрос**: человек
  уже ищет именно «бесплатное и с исходниками»
- aqua voice alternative free
- superwhisper for windows ← Superwhisper заточен под macOS
- macwhisper for windows ← MacWhisper существует только под macOS
- wispr flow alternatives
- wispr flow alternatives free
- wispr flow alternative open source
- wispr flow alternative local
- wispr flow alternative for windows
- wispr flow alternatives reddit

**RU — `TARGET`:**
- аналог wispr flow
- бесплатный аналог wispr flow

**Контент, который по этому закрывается:** «Whisper alternative», «Aqua Voice
open source alternative», «Superwhisper for Windows», «Wispr Flow alternative
open source». Честная рамка каждого: *мы не whisper и не облако — 44 МБ, CPU,
Apache-2.0, работает без интернета*. Это сильнее, чем притворяться.

> `aqua voice alternative` без `open source` — **CONTENT**: в выдаче смысл
> уходит в «aqua singers», «aqua names». Целевой вариант — только с
> `open source`.

## 2. 🖥️ Технические запросы

**EN — `TARGET`:**
- offline voice dictation
- offline voice to text
- offline dictation app
- offline dictation software
- offline dictation software for windows
- offline speech to text windows
- offline speech recognition app
- best offline dictation app
- open source voice dictation
- open source voice dictation software
- open source voice typing
- open source voice input
- open source speech to text software
- speech to text without internet
- speech to text app without internet
- speech to text no internet
- do you need internet to text
- dictation hotkey windows
- windows 11 dictation hotkey
- dictation software for windows
- dictation software for windows 11
- dictation software free
- dictation software for pc
- speech to text windows free
- small speech to text model ← размер модели, см. § 9
- best small speech to text model
- smallest speech to text model
- lightweight speech to text model
- vosk models
- vosk model download
- vosk model small
- vosk kaldi speech recognition

**RU — `TARGET`:**
- офлайн распознавание речи
- vosk офлайн распознавание речи ← **живое автодополнение, конкуренции нет**
- программа для диктовки текста на компьютер ← точная форма RU-запроса
- программа для диктовки текста
- программа для диктовки текста на русском языке
- программа голосового ввода текста
- набор текста голосом на компьютере
- голосовой ввод windows 11
- голосовой ввод windows 10
- голосовой ввод windows на русском
- голосовой ввод текста windows 11 на русском
- голосовой ввод текста windows 10 на русском

**`DROP`:**
- `whisper dictation *` как **свой** продуктовый ключ — по нему ищут whisper.
  Годится только в сравнительных статьях.
- `faster-whisper dictation`, `whisper.cpp dictation`, `whisper large v3
  dictation`, `GPU accelerated whisper`, `CUDA whisper dictation` — другой
  движок, у нас нет ни CUDA-пути, ни phrase-level моделей.
- `BYOK voice dictation`, `self-hosted speech to text` — у нас нет ключей и
  серверного режима.
- `Python / Electron / Tauri voice dictation` — никто не ищет «диктовку на
  Python», чтобы её купить. Это для разработчиков, не покупателей.
- `vosk` **без хвоста** — см. § «Ловушки».

## 3. 🆓 Бесплатные и встроенные решения

**EN — `TARGET`:**
- free voice typing app
- free speech to text windows
- free dictation software
- free voice typing app free
- best free dictation software
- best free dictation app for writers
- free dictation apps for writers
- voice typing windows 11 free
- speech to text windows 11 free
- voice typing windows free

**RU — `CONTENT`:** ру-сет ищет **онлайн**-сервисы (`диктовка онлайн`,
`диктовка текста онлайн`, `набор текста голосом онлайн`) и не ищет «бесплатную
программу для диктовки» — запрос пустой. Продавать «бесплатно» в RU надо
в тексте лендинга, а не в заголовке.

**`DROP` (формулировки мёртвые):**
- `no subscription dictation app` — пусто
- `one time purchase dictation software` — пусто
- `lifetime license voice typing` — пусто
- `бесплатная программа для диктовки` — пусто

## 4. 🗣️ Пользовательские запросы (по сценарию)

**EN — `TARGET`:**
- voice to text app windows
- speech to text for pc
- dictation software for pc
- dictation software for writers ← плотный кластер с модификаторами
- dictation software for writers free
- dictation app for writers
- dictation app for writing a book
- dictation app for authors
- best dictation software for writers
- dictation for medical / for healthcare ← **CONTENT**, только если не заявляем
  комплаенс (см. § 8)
- voice to text windows 11
- voice to text windows
- how to dictate on computer
- how to use voice typing on windows
- dictation for long text
- multilingual dictation windows
- multilingual speech to text
- multilingual speech recognition
- dictation in russian

**RU — `TARGET`:**
- диктовка
- диктовка текста
- диктовка текста на русском
- диктовка на русском
- диктовка в ворде на русском
- диктовка в ворде
- набор текста голосом в word
- программа для диктовки текста на компьютер

**`DROP`:** `голосовой ввод в telegram / notion / discord / vs code` как
целевые ключи — по ним нет объёма, это перечисление ради перечисления.
Оставить как **CONTENT** (одно предложение в HOWTO: работает везде, где есть
каретка).

## 5. 🔍 Информационные запросы (блог, статьи)

**EN — `TARGET`:**
- how to use voice typing windows
- how to use voice dictation
- voice typing windows 11 shortcut
- windows voice typing windows+h
- windows 11 dictation hotkey
- how to dictate punctuation
- how to dictate in another language
- does voice typing work offline
- is voice typing accurate
- dictation software for mac ← **CONTENT** как честное «у нас Windows»
- best dictation software 2026 ← год обновлён, «2025» больше не в выдаче

**RU — `TARGET`:**
- как включить голосовой ввод на windows
- как пользоваться голосовым вводом
- как набирать текст голосом на компьютере
- как диктовать текст на компьютере
- голосовой ввод windows 11 shortcut
- как работает голосовая диктовка
- работает ли диктовка офлайн
- точность голосового ввода
- можно ли диктовать код

## 6. 💢 Болевые запросы — воронка замены

Самая недооценённая группа в исходном файле. Люди ищут не «лучшую
программу», а **«у меня не работает»** — и это готовый спрос на замену.

**EN — `TARGET`:**
- voice typing not working
- voice typing not working windows 11 ← **высокочастотная форма**
- voice typing not working windows 10
- voice typing not working in word
- voice typing not working in google docs
- windows 11 voice to text not working
- windows speech to text not working
- why is my voice typing not working
- speech to text windows 11 not working
- windows voice typing problems
- dictation cuts off
- dictation keeps stopping

**RU — `CONTENT`:** русские болевые формулировки («диктовка windows не
работает», «голосовой ввод windows неточный») не подтверждаются автодополнением.
Их стоит держать в тексте статьи, но не в заголовке.

**`DROP` как ключи (мертвые или чужие):**
- `диктовка windows не работает` — пусто
- `словарь распознавания речи` — пусто
- `горячая клавиша диктовка` — пусто
- `диктовка без интернета` — **пусто**, хотя это главный «оффлайн-страх».
  Честно: офлайн подаётся через `offline voice dictation` в EN и через
  `офлайн распознавание речи` в RU, а не через «без интернета».

## 7. 🤖 AI / нейросетевые запросы

**`CONTENT`:** `AI voice dictation windows`, `AI transcription app`,
`AI post processing dictation`, `диктовка с GPT`, `ИИ обработка текста
диктовки` — работают в описании, но **низкочастотные**. Мы не LLM-обвязка:
у нас Vosk + `corrector.py` на difflib, без нейросети. Заявлять «AI» в H1 —
перебор; честная формулировка — «on-device распознавание речи плюс
собственный словарь».

**`DROP`:** `GPT dictation app`, `dictation with GPT correction`,
`ChatGPT voice typing windows`, `LLM voice typing` — обещают то, чего в
продукте нет.

## 8. 🏢 Профессиональные / корпоративные

**`DROP` по существу, `CONTENT` по совпадению интереса:**
- `enterprise dictation software`, `team dictation tool` — нет
- `HIPAA compliant dictation`, `medical dictation software`, `legal dictation
  software`, `EHR / CRM` — продукт не проходил комплаенс-разбор, заявлять
  нельзя. `dictation software medical` в автодополнении есть, но это чужая
  категория с чужими требованиями.
- `RSI / carpal tunnel / accessibility voice typing`, `dictation for disabled
  users` — **CONTENT**, единственная честная точка: набор голосом не требует
  рук вовсе, это правда.

## 9. 🧠 Технические кластеры с нулевой конкуренцией

Низкий объём, но **никто не занят**, а интент максимальный. Это контент,
который делается один раз и годами приводит целевой трафик.

**Размер модели — `TARGET`:**
- small speech to text model
- best small speech to text model
- smallest speech to text model
- lightweight speech to text model
- small speech recognition model

Отвечать надо measured-цифрами проекта (44 МБ на русском, список 20+ языков у
публикатора). Это сильнее любого «лёгкого» обещания.

**Свой словарь — `TARGET`:**
- speech to text custom vocabulary
- how to add words to voice typing
- add custom words to speech to text
- custom words dictation

Прямое попадание в `phrases.txt` + `corrector.py` и в `--vocab-check`.

**Vosk как технология — `TARGET`, только с хвостом:**
- vosk models
- vosk model download
- vosk model small
- vosk kaldi speech recognition
- офлайн распознавание речи
- vosk офлайн распознавание речи

Здесь живёт и setup-справочник, и FAQ. Голый `vosk` не целим (см. § «Ловушки»).

## 10. 🌍 Локализованные / языковые

- dictation in russian / диктовка на русском — `TARGET`
- multilingual dictation windows / мультиязычное распознавание речи — `TARGET`
- code switch dictation / двуязычная диктовка — `CONTENT`
- dictation in spanish / german / french / chinese — `CONTENT`: работает, если
  положить модель, но **не проверено в этом репозитории**. Заявлять «20+
  языков» можно со ссылкой на список издателя, а не как «мы это проверили».

## 11. 🎯 Длинные хвосты

**`TARGET`:**
- free whisper based dictation for windows ← переписать в «whisper-free»
- how to dictate into any windows app ← `CONTENT` (пустой запрос)
- local speech to text without internet
- best offline voice dictation app for windows 11
- push to talk dictation for coding
- dictation app for writing a book
- how to dictate emails on windows
- private voice typing for programmers

**`DROP` (мертво, проверено автодополнением — пустой результат):**
- hold key to dictate
- dictate into any app
- type with voice anywhere
- диктовка в любую программу
- speech to text cpu only
- speech to text on old laptop
- dictation tray
- free voice typing app no subscription
- offline dictation no subscription
- speech to text without sending audio
- audio never leaves your computer
- микрофон не отправляет
- voice typing for people with dyslexia

---

## 🪤 Ловушки

Три места, где запрос выглядит подходящим, но уводит не туда.

1. **`vosk` без хвоста** — в EN-выдаче это камеры видеонаблюдения **Vosker**
   (`vosker v300`, `vosker reviews`). Целиться можно только в
   `vosk models` / `vosk kaldi …` / RU `vosk офлайн распознавание речи`.
2. **`push to talk`** — в RU это софт рации (`push to talk скачать на пк`,
   `push to talk obs`, `push to talk discord`), в EN — фича Claude Code
   (`claude push to talk dictation`, `/voice`). Голый «push to talk» в H1
   сравнивают с чужим продуктом. В RU вообще не использовать.
3. **MacWhisper / Superwhisper / Aqua Voice** — macOS-ориентированные.
   `… alternative for windows` и `… open source alternative` — это запросы
   unmet need, в которых мы и есть ответ. А вот `macwhisper transcription`
   и `aqua voice` без хвоста — чужие.

## 🧭 Формулировки: CONTENT, не ключи

Их нет в спросе, но они отличают продукт. Годится для H2, подзаголовка, README
и мета-описания, **не** для таргетинга:

- работает без видеокарты / без GPU, только CPU
- 44 МБ вместо гигабайтных моделей
- печатает в то окно, где стоял курсор, без буфера обмена
- микрофон никуда не отправляется, сети нет вообще
- бесплатно навсегда, без ключа API, без подписки
- история распознанного в текстовом файле по дням
- свой словарь: свои слова и склейка разорванных слов
- своя горячая клавиша, удержание = запись

## 📌 Как это проверено

Источник — **автодополнение Google и Bing** (`suggestqueries.google.com`,
`api.bing.com/osjson`), RU-выборка через `hl=ru&gl=ru`, EN через
`hl=en&gl=us`. Проверено 2026-10-03.

Чего этот метод **не** даёт:

- **Это не объём.** Автодополнение показывает, что запрос формулируют, а не
  сколько раз. Порядок подсказок ≠ частота, а пустой результат означает лишь
  «не набирают в этих регионах».
- **Нет конкурентной разметки.** Difficulty, CPC и SERP не измерялись —
  платные инструменты не использовались.
- **Регион фиксирован.** RU-срез с `gl=ru` может отличаться от СНГ-трафика.

Чтобы получить настоящие цифры, нужны Google Keyword Planner и Ahrefs/Semrush
по этому же списку. До этого файл — **гипотеза приоритетов, а не измерение**,
и вердикты в нём — обоснованные, но не доказанные объёмом.

**Правило пересмотра:** перепроверять раз в квартал. Термин «2026» в
`whisper alternatives 2026` протухает — заменить на следующий год в январе.

## 📌 Как использовать

| Цель | Кластеры |
|------|---------|
| **Title / H1** | 1, 2 (rank 1-3), 11 |
| **Meta description** | 2 (rank 4-5), 9 |
| **Лендинг** | 1, 2, 4, 11 |
| **Блог-статьи** | 5, 6, 9, 10 |
| **ASO (Microsoft Store)** | 2 (RU), 4 |
| **Google Ads** | 1 |
| **Reddit / HN посты** | 1, 2, 6, 9 |
| **Setup / FAQ** | 9 (vosk models), 10 |

**Приоритет для WinVosk (локальная, бесплатная, без облака, на Vosk):**

1. `whisper alternatives 2026` / `whisper alternatives open source` —
   самый широкий вход в категорию, `2026` держит свежесть
2. `aqua voice open source alternative` — самая горячая отдельная фраза
3. `offline voice dictation` / `офлайн распознавание речи` — суть продукта
   словами пользователя
4. `программа для диктовки текста на компьютер` — точная RU-форма на нашу
   категорию
5. `small speech to text model` — метрика, которой нет ни у кого из
   конкурентов, и она проверяема

Пункты 1-2 приводят трафик, 3-5 превращают его в загрузки: у нас 44 МБ, Apache-2.0,
`KEYEVENTF_UNICODE` и ноль сетевых вызовов — это не обещание, а то, что видно
в коде и в `--diagnose`.
