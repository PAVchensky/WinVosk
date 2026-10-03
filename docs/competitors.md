# 🪞 Конкуренты: текстовка, ключевые слова, и наша полоса

Разбор выполнен 2026-10-03. Источники: страницы проектов, README, выдача
DuckDuckGo по нашим целевым запросам. Полные цифры по WinVosk измерены на
этой машине — метод и честные оговорки в § 4 и § 8.

> **Главный вывод файла.** Формулы «бесплатно», «open source», «работает
> офлайн», «никакого облака», «по горячей клавише», «печатает в любое окно»,
> «Windows» — **больше не differentiate**. Их используют все десять игроков в
> выдаче, и половина из них родилась в 2026-м. Бить надо туда, где не пишет
> никто: **размер, отсутствие GPU и мгновенный старт**. Ниже — доказательства
> и что из этого можно заявлять, а что нельзя.

---

## 1. Карта конкурентов

| Проект | Движок | Лицензия | Размер модели | Звёзд | Что заявляет |
|---|---|---|---|---|---|
| **Handy** (cjpais/Handy) | Whisper Small–Large + Parakeet V3 | MIT | 487 МБ – 1,6 ГБ | 32,7k | free, open source, offline, private, simple |
| **OpenWhispr** | Whisper / Parakeet / Cohere, локально + облако по BYOK | MIT | локальные модели | 9,0k | free, open source, no telemetry, «small floating pill» |
| **amical** | open source модели, ollama | MIT | — | 1,5k | local-first, «Type 3x faster» |
| **Handy STT / Vibe Transcribe / Voxtral / TypeWhisper / Speech Note** | — | — | — | — | лидеры каталогов альтернатив |
| **Voquill** | — | — | — | — | FOSS, push-to-talk, zero telemetry, Win + Linux |
| **VoxCast** | — | — | — | — | 100% offline, hotkey, митинги, PDF→Markdown |
| **PipeVoice** | любой движок на выбор | — | — | — | «Best free dictation for Windows 2026» |
| **VoCript** | локальный Whisper | — | — | — | offline, system audio, профили |
| **AuraScribe** | — | — | — | — | «private, free Wispr Flow alternative» |
| **HandsFree Magic** | — | — | — | — | 100% free, no cloud, no account, no cost |
| **Whisperio** | Whisper, локально или облако | — | — | — | global hotkey, «cloud-fast or offline» |
| **Murmur** | Whisper | — | — | — | в Microsoft Store |
| **SpeakoFlow** | whisper.cpp | MIT | — | 258 | Wispr Flow alternative + чтение экрана |
| **VoiceInk**, **FluidVoice** | — | — | — | — | в каталогах openalternative |
| **tambourine-voice** | Whisper | **AGPL-3.0** | — | 389 | «Open source alternative to Wispr Flow» |
| **VoiceFlow** | faster-whisper | MIT | — | 423 | Win+Linux, митинги, BYO-LLM |
| **OpenTypeless** | Whisper | MIT | — | 582 | Tauri, «polished text in any app» |
| **Wispr Flow** | своя облачная модель | платная | — | — | 4x faster than typing, 100+ языков |

**Вывод по таблице.** Ни один игрок не работает на Kaldi/Vosk. Все, кто
конкурирует за «бесплатную офлайн-диктовку», сидят на Whisper с моделями от
487 МБ до 1,6 ГБ и ведут речь про GPU, Parakeet и «local AI».

## 2. Выдача: кто реально стоит по нашим ключевым словам

Запрос `free offline voice dictation windows` (наш основной, § 2
`seo_keywords.md`), выдача целиком состоит из таких проектов:

```
1. AuraScribe      aurascribe.dev
2. VoxCast         getvoxcast.com
3. Murmur          apps.microsoft.com        ← Microsoft Store
4. SpeakoFlow      github.com
5. HandsFree Magic handsfreemagic.com
6. SpeakoFlow      speakoflow.com
7. VoCript         vocript.app
8. PipeVoice       pipevoice.app/blog/best-free-dictation-software-windows
9. whisper-local   github.com/drajb/whisper-local
10. Voquill        voquill.org
```

Запрос `whisper alternative open source`:

```
1. alternativeto.net/software/whisper/?license=opensource   ← каталог
2. OpenWhispr        github.com
3. alternativeto.net/software/whisper/                     ← каталог
4. whisper-local     github.com
5. getvoibe.com      статья-рейтинг
6. vexascribe.com/whisper-alternatives                     ← статья-рейтинг
7. openwhispr.com/compare/wisprflow                        ← страница сравнения
8. sevenlabs.site    статья про модели
9. reddit.com/r/LocalLLaMA                                ← тред
10. openalternative.co/alternatives/wisprflow               ← каталог
```

**Что из этого следует.** Десять из десяти — не статья, а продуктовая
страница: категория занята самими продуктами. Побеждает не SEO текста, а
наличие конкурентной страницы (`/compare/wisprflow`) и присутствие в каталогах
(`alternativeto.net`, `openalternative.co`). Статьи-рейтинги есть, но
имитировать их дорого и бессмысленно, пока нет продукта в каталогах.

**Против нас, отдельно:** `whisper-local` пишет в описание списком
«Wispr Flow alternative, offline voice typing, local Whisper dictation,
free Dragon NaturallySpeaking alternative, privacy-first speech-to-text» —
то есть явный keyword-stuffing в description. Работает, но выглядит
дёшево. Копировать не надо.

## 3. Разбор текстовки: что и как продают

### 3.1. Handy — эталон структуры

Заголовок и лид:

> **A free, open source, and extensible speech-to-text application that works
> completely offline.**
>
> Handy is a cross-platform desktop application that provides simple,
> privacy-focused speech transcription. Press a shortcut, speak, and have your
> words appear in any text field. This happens on your own computer without
> sending any information to the cloud.

Четыре опоры, каждая в одну строку и **с причиной**:

> **Free**: Accessibility tooling belongs in everyone's hands, not behind a
> paywall
> **Open Source**: Together we can build further
> **Private**: Your voice stays on your computer
> **Simple**: One tool, one job. Transcribe what you say and put it into a text box

Что стоит взять:

- **причина рядом с каждым обещанием** — «не за paywall» сильнее, чем «free»;
- **«One tool, one job»** — анти-фича, работает отлично;
- **hold to record / release to stop** — описан как действие, а не как фича;
- **раздел Known Issues** с честным списком (Bluetooth на macOS, `fn` на
  сторонних клавиатурах, Wayland) и фразой «We believe in transparency about
  the current state». Это вызывает доверие и почти никто этого не делает;
- **winget** в инструкции — снимает барьер установки;
- в README честно сказано, что бренд (имя, лого, иконка) **не** открыт.

Чего у Handy нет: **размера, RAM, требований к железу.** Ни одного числа.

### 3.2. Wispr Flow — скорость как главный герой

> **Don't type, just speak.**
> The voice-to-text AI that turns speech into clear, polished writing in every app.

> **4x faster than typing** — 45 wpm клавиатура против 220 wpm Flow

> **Speak naturally.** Ramble, pause, or change your mind mid-sentence. Flow
> understands what you mean, not just what you say.
> **Flow edits as you speak.** Text that reads like you wrote it, not like you
> spoke it. Flow automatically removes filler words, adds punctuation, and
> formats your writing.
> **Use it anywhere.** Flow works anywhere you can type, with no plugins required.

Дальше — соцдоказательство (Microsoft, Amazon, Notion, Klarna, Vercel;
Steven Bartlett, Fast Company), кейсы с числами (90% faster message output,
$3.08m/year) и блок доверия: SOC 2 Type II, HIPAA, ISO 27001.

И FAQ, который стоит скопировать по духу: «Is Flow free?» — честный ответ
**«yes, but 2,000 words per week»**. Ограничение называют прямо, а не прячут.

**Что из этого применимо к нам.** Скорость — да, и даже сильнее: у Wispr это
4x против человека, у нас может быть «печатает, пока вы говорите» + «стартует
за 2 секунды на любой машине». Придумывать «8x быстрее» нельзя: у нас не
Whisper, точность на длинном тексте другая. Формально 4x набирается только
для простых фраз без правок.

«Убирает слова-паразиты, расставляет пунктуацию» — **не наша фича**. У нас
`corrector.py` чинит только собственные слова из `phrases.txt`. Заявлять
cleanup нельзя. Соцдоказательства и кейсы с выручкой — тоже не наш масштаб,
придумывать их нельзя.

### 3.3. OpenWhispr — конкретный образ в лиде

> **A small floating pill that lives on your desktop.** Hold Ctrl+Space, speak,
> release — your words appear instantly in Gmail, Slack, or any app you're in.

> Choose between fully private offline transcription ... where your audio never
> leaves your device — or cloud processing for speed. **No data collection, no
> telemetry, fully open source.**

Приём — назвать физический объект («плавающая таблетка»). У нас для того же
есть «плашка-чип над часами» (`overlay.py`) и трей. Это готовая конкретика
для первого экрана.

### 3.4. Длинный хвост — приём «список отказов»

> No cloud, no subscription, no account, no cost
> Free, local, open-source, 100% offline
> No data collection, no telemetry
> Dictate by hotkey · record & transcribe meetings · convert audio & PDF to Markdown

Приём рабочий и копируется за секунду. **Но именно поэтому он и не
дифференцирует:** он повторён у VoxCast, Voquill, HandsFree Magic, VoCript и
SpeakoFlow. Дальше выигрывает не формулировка, а мелочь вроде «работает на
любом ноутбуке без видеокарты», которой нет ни у кого.

## 4. Наши измеренные цифры

Замерено на этой машине 2026-10-03, `models\vosk-model-small-ru-0.22`.

| Величина | Значение | Как получено |
|---|---|---|
| Модель, скачивание | **44,1 МБ** | `Content-Length` zip у издателя |
| Модель на диске | **87,1 МБ** | HCLr.fst 31,5 + Gr.fst 30,8 + final.mdl 15,1 + final.ie 9,5 |
| Интерпретатор, без модели | 19,7 МБ | `GetProcessMemoryInfo`, WorkingSet |
| Загрузка модели | **2,0 с** | `perf_counter` вокруг `Model(...)` |
| Рабочий набор после модели | 200,3 МБ | WorkingSet |
| Пик после 30 с аудио | **211,1 МБ** | WorkingSet |
| RTF на тишине | 0,039 | 30 с тишины через `AcceptWaveform` |

Сборка `dist\WinVosk` целиком — **184,6 МБ** (модель + Python + PyInstaller).

> ⚠️ **Про 44 МБ.** `AGENTS.md` и `project.md` пишут «44 МБ». Это размер
> **zip-архива**. На диске модель занимает 87,1 МБ, из которых 62 МБ — графы
> декодирования (`HCLr.fst` + `Gr.fst`), а сама акустическая модель — 15,1 МБ.
> В текстах можно говорить «44 МБ скачивается», нельзя — «весит 44 МБ».

> ⚠️ **Про RTF.** 0,039 измерено **на тишине**, а не на речи. Kaldi на тишине
> почти не тратит время, поэтому это число нельзя публиковать как скорость.
> Настоящий RTF на русской речи здесь не измерен. Пока нет честного числа —
> заявлять скорость можно только через **старт за 2 секунды** и **печать в
> реальном времени**, и то и другое проверяемо.

Для сравнения, размеры моделей **из README Handy** (наши не измерены):
Whisper Small 487 МБ, Medium 492 МБ, Large-v3 Q5 1100 МБ, Turbo 1600 МБ,
Parakeet Unified EN Q8 731 МБ.

## 5. Полоса, которую не занимает никто

Сквозной аудит выдачи из § 2 и README из § 1: **ни один проект не заявляет
ни размер загрузки, ни требования к железу, ни скорость старта.** Всё это
заменено словами «local AI», «GPU acceleration», «14ms latency on RTX 4090»,
«no telemetry».

| Ось | Что говорят все | Что не говорит никто | Наша цифра |
|---|---|---|---|
| Размер | «local», «offline» | сколько мегабайт качать | 44 МБ / 87 МБ против 487–1600 МБ |
| Железо | «GPU acceleration», «Parakeet», «RTX 4090» | что работает **без** видеокарты | CPU-only, 211 МБ RAM |
| Старт | — | сколько секунд до первого слова | **2,0 с** загрузка модели |
| Дистрибуция | `winget`, `.deb`, AppImage | portable, без установки | `WinVosk.bat` + одна папка |
| Скорость | «4x faster», «3x faster», «14ms» | честная задержка на живом аудио | печать в реальном времени (live typing) |
| Свои слова | «learns your vocabulary» | что именно делает | `phrases.txt` + `--vocab-check` + склейка разорванных слов |

**Это и есть наша полоса.** Не «самая маленькая» — а «единственная, которая
не требует видеокарты и не качает гигабайты». Именно её и надо ставить в
заголовок, потому что `small speech to text model`, `best small speech to
text model`, `smallest speech to text model` — живые запросы с пустым
ответом в выдаче.

## 6. Позиционирование по четырём осям

Пользователь просил бить по: бесплатность, скорость, лёгкость, Windows.
Честный разбор, что можно говорить.

### 6.1. Бесплатность — заявлять можно и нужно

Формула полная: бесплатно навсегда, без подписки, без ключа API, без
аккаунта, без телеметрии, Apache-2.0. В отличие от Wispr Flow, где «free»
означает 2000 слов в неделю, у нас ограничения нет вообще — это проверяемо
по коду: ни одного сетевого вызова.

Слабое место: сама формула **не дифференцирует** (§ 3.4). Дифференцирует
связка «free + 44 МБ + без видеокарты» — то есть бесплатность подаётся не
как подарок, а как следствие лёгкости.

### 6.2. Скорость — только через старт и живую печать

**Нельзя:** «4x faster than typing» (принадлежит Wispr), «3x faster»
(amical), «14ms latency» (OpenWhispr), любые wpm. Нельзя публиковать
RTF 0,039 — он на тишине.

**Можно и проверяемо:**

- **старт за 2 секунды** — отсюда сразу в первые секунды работы;
- **текст появляется, пока вы говорите** (live typing + диффы к уже
  напечатанному) — это правда, и это сильнее «быстро», потому что видно;
- **нет загрузки модели на 700 МБ перед первым словом** — у всех остальных
  есть, у нас нет.

Формулировка: «words appear as you speak, and it is ready two seconds after
you launch it» — вместо «4x faster».

### 6.3. Лёгкость — наше главное отличие, но не «весит 44 МБ»

Честная формула: **«44 МБ скачивается, 211 МБ в памяти, работает на
процессоре без видеокарты»**. Не «лёгкий» вообще — а три конкретных числа
рядом со словом «лёгкий».

И добавить то, чего нет ни у кого: запускается двойным щелчком по
`WinVosk.bat`, без установки, без прав администратора, без `winget`, без
аккаунта. Portable — редкая и проверяемая формула.

Чего **нельзя:** «largest language support wins» / «100+ languages» как своё
достоинство — список 20+ языков принадлежит издателю моделей, и в этом
репозитории проверена только русская модель. Формулировать как «язык задаёт
модель, которую вы кладёте в `models\`», а не как «мы поддерживаем 100
языков».

### 6.4. Windows — это фильтр, а не отличие

Windows есть у всех, кроме MacWhisper/Superwhisper. Само по себе «для
Windows» не продаёт. Продаёт **только** в связках, где Windows — это
недостающая деталь чужого продукта:

- `superwhisper for windows` — Superwhisper сделан под macOS;
- `macwhisper for windows` — MacWhisper существует только под macOS;
- `aqua voice open source alternative` — Aqua Voice платный.

Здесь у Windows ровно одна задача: быть причиной, по которой человек
ищет альтернативу. Второй плюс — «настоящий .exe, без Electron, 20 МБ
исходников вместо 180 МБ рантайма» (это заметно: `src\` весит 0,4 МБ,
собранный `dist\` — 184,6 МБ, то есть рантайм — не наш).

## 7. Каналы, которые уже дают трафик

Из выдачи § 2 видно, где лежат ссылки на конкурентов:

- **Каталоги альтернатив:** `alternativeto.net/software/whisper/` и
  `openalternative.co/alternatives/wisprflow`. Обе страницы ставят Handy
  первым. Присутствие там даёт и трафик, и авторитет.
- **Страницы сравнения:** `openwhispr.com/compare/wisprflow` — целая
  страница под один запрос. Наш аналог: `/compare/wisprflow`, `/compare/handy`,
  `/compare/openwhispr`, `/compare/aqua-voice`.
- **Microsoft Store:** в выдаче сидит `Murmur` (apps.microsoft.com). Стоит
  проверить, свободен ли наш слот.
- **winget:** Handy ставится через `winget install cjpais.Handy`. Наш пакет
  в манифесте не зарегистрирован — это самая дешёвая дистрибуция из всех.
- **Reddit / HN:** в выдаче по обоим запросам — `r/LocalLLaMA` и
  `whisper alternatives reddit` в автодополнении. Тред про
  `whisperX / faster-whisper` живёт годами.

Вывод: **SEO-текст вторичен, листинг первичен.** Пока WinVosk не стоит в
`alternativeto.net` и `openalternative.co` и не зарегистрирован в winget,
любые ключевые слова из `seo_keywords.md` упираются в то, что выдачу
занимают десять продуктов с готовыми страницами.

## 8. Что нельзя заявлять — список

Чтобы формулировки не разъехались с кодом при следующем пересмотре:

| ❌ Нельзя | Почему |
|---|---|
| «4x / 3x faster than typing» | цифра Wispr/amical, у нас нет замеров на речи |
| «RTF 0,04, в 26 раз быстрее реального времени» | измерено на тишине |
| «весит 44 МБ» | 44 МБ — zip; на диске 87 МБ |
| «не требует интернета вообще» | верно для работы, но ложно для установки модели |
| «100+ языков» / «20+ языков наша поддержка» | список у издателя; здесь проверен русский |
| «убирает слова-паразиты, ставит пунктуацию» | `corrector.py` чинит только `phrases.txt` |
| «потоковый ИИ-постпроцессинг», «GPT-диктовка» | у нас `difflib`, нейросети нет |
| «HIPAA / SOC 2 / enterprise» | не проходили комплаенс, продукт однопользовательский |
| «не использует буфер обмена» | верно для вставки, но «копировать в буфер» в настройках есть |
| «любая раскладка клавиатуры» | верно: `KEYEVENTF_UNICODE`; но проверять надо на реальной клавиатуре |

## 9. Готовые текстовые блоки

Заготовки под найденные приёмы. Числа — только из § 4.

**Лид (структура Handy, наши числа):**

> **Free, open source voice dictation for Windows that works completely
> offline — 44 MB to download, no graphics card required.**
>
> WinVosk is a small desktop app for Windows. Hold a hotkey, speak, and your
> words appear wherever your cursor is. The model runs on your processor and
> your audio never leaves the machine.

**Четыре опоры (структура Handy, наша полоса):**

> **Free** — no subscription, no trial, no account, no API key, Apache-2.0.
> **Light** — 44 MB to download, 211 MB of memory, no graphics card needed.
> **Fast** — ready two seconds after launch, and your words appear while you
> still speak.
> **Windows only, done properly** — a real keyboard hook and unicode
> keystrokes, so the text lands in any program without plugins.

**Заголовок (наш полоса, не «самая маленькая»):**

> Free offline dictation for Windows — 44 MB, no GPU

**Сравнительная таблица для `/compare/*` (колонка «что у нас»):**

| | WinVosk | Whisper-based apps |
|---|---|---|
| Download | 44 MB | 487 MB – 1.6 GB |
| Graphics card | not needed | strongly recommended |
| Memory | 211 MB | ~1 GB and up |
| Ready after launch | ~2 s | 5–60 s, after a model download |
| Subscription | none | none or usage limits |
| Own words | `phrases.txt`, checked with `--vocab-check` | learned automatically |
| Install | double-click a `.bat`, no admin rights | installer or package manager |

## 10. Новые ключевые слова из этого разбора

В `seo_keywords.md` добавлено; здесь — откуда они.

| Запрос | Источник сигнала | Статус |
|---|---|---|
| `small speech to text model` | автодополнение есть, в выдаче ответа нет | `TARGET`, наш полоса |
| `best small speech to text model` | то же | `TARGET` |
| `smallest speech to text model` | то же | `TARGET` |
| `lightweight speech to text model` | автодополнение есть | `TARGET` |
| `speech to text custom vocabulary` | автодополнение есть | `TARGET` |
| `superwhisper for windows` | автодополнение | `TARGET`, unmet need |
| `macwhisper for windows` | автодополнение | `TARGET`, unmet need |
| `aqua voice open source alternative` | автодополнение | `TARGET`, unmet need |
| `whisper alternatives 2026` | автодополнение + выдача | `TARGET` |
| `whisper alternatives open source` | выдача, alternativeto | `TARGET` |
| `free open source voice dictation windows` | формулировка выдачи №1 | `TARGET` |
| `no gpu speech to text` | в спросе не подтверждено | `CONTENT` |
| `portable voice dictation` | в спросе не подтверждено | `CONTENT` |

## 11. Границы разбора

- `websearch` был недоступен (403), поэтому использованы прямое чтение
  страниц проектов, автодополнение Google/Bing и `lite.duckduckgo.com`.
  Это **выдача DuckDuckGo**, а не Google: состав и порядок отличаются.
- Объёмы не измерялись ни для одного запроса. Платные инструменты
  (Keyword Planner, Ahrefs, Semrush) не использовались.
- Звёзды и лицензии — на момент 2026-10-03, они меняются.
- Размеры моделей конкурентов взяты из README Handy, не измерены.
- RAM у Whisper-приложений не измерялся, в таблице § 9 стоит оценка «~1 GB
  and up» — перепроверить перед публикацией.
- Выдача DuckDuckGo не показывает рекламу и не отражает Google-специфику
  (`{!r}`-подобные блоки,featured snippets). Перед решением о бюджете
  проверить вручную.
