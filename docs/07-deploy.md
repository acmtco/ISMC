# Развёртывание на сервере

Приложение собирается в один образ: интерфейс и API отвечают с одного
адреса. Дальше два пути, в зависимости от того, занят ли на сервере
веб-сервером порт 443.

- **На сервере уже есть nginx с другими сайтами** — раздел «Рядом с
  существующим nginx». Наш контейнер слушает только localhost, наружу его
  отдаёт ваш nginx, он же выпускает сертификат.
- **Сервер пустой** — раздел «На пустом сервере». Поднимается Caddy,
  который сам получает и продлевает сертификат Let's Encrypt.

---

# Рядом с существующим nginx

Сайты, которые уже работают на сервере, этот способ не затрагивает.

## 1. Домен

В Cloudflare создайте запись для поддомена:

| Поле | Значение |
|---|---|
| Тип | `A` |
| Имя | `ismc` |
| Значение | публичный IP сервера |
| Проксирование | **выключено**, серое облако |

Проксирование на время выпуска сертификата нужно выключить, иначе certbot
не пройдёт проверку владения доменом. Включить обратно можно потом, выбрав
режим шифрования Full (strict).

Дождитесь, пока запись разойдётся: `dig +short ismc.urbanconstruction.ru`
должен вернуть IP сервера.

## 2. Приложение

```bash
git clone https://github.com/acmtco/ISMC.git && cd ISMC
docker compose -f docker-compose.prod.yml up -d --build app
```

Собирается 5–10 минут. Контейнер слушает `127.0.0.1:8000` и снаружи
недоступен — это намеренно. Проверка с самого сервера:

```bash
curl -s http://127.0.0.1:8000/health
```

Ожидаемый ответ — `{"status":"ok"}`.

Если порт 8000 на сервере занят, задайте другой в `.env`: `HG_PORT=8010`,
и поправьте `proxy_pass` в конфиге nginx на тот же номер.

## 3. nginx

```bash
sudo cp deploy/nginx/hronograf.conf /etc/nginx/sites-available/hronograf
sudo sed -i 's/ismc.example.ru/ismc.urbanconstruction.ru/' \
    /etc/nginx/sites-available/hronograf
sudo ln -s /etc/nginx/sites-available/hronograf /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

`nginx -t` обязателен: он проверит, что конфигурация цела, и вы не уроните
остальные сайты.

## 4. Сертификат

```bash
sudo certbot --nginx -d ismc.urbanconstruction.ru
```

Certbot сам допишет блок для 443 и перенаправление с http. Продление уже
настроено системным таймером, ничего добавлять не нужно.

Готово: https://ismc.urbanconstruction.ru

## Обновление

```bash
cd ISMC && git pull
docker compose -f docker-compose.prod.yml up -d --build app
```

---

# На пустом сервере

Если порты 80 и 443 свободны, nginx не нужен: Caddy сделает всё сам.

## Сервер

Годится любой с Ubuntu и Docker. Инструкция ниже написана под Oracle Cloud
Always Free, но шаги те же для Timeweb, Selectel и Yandex Cloud.

В панели Oracle Cloud: **Compute → Instances → Create Instance**.

- образ: **Canonical Ubuntu 22.04**
- форма: **VM.Standard.A1.Flex** (ARM), 2 ядра и 12 ГБ памяти достаточно
- сохраните приватный ключ SSH, второй раз его не покажут

Если ARM-инстансов нет в наличии, попробуйте другую зону доступности в том
же регионе или повторите через несколько часов: на бесплатном тарифе они
разбираются быстро.

**Откройте порты.** В Oracle это делается в двух местах, и забыть про
второе — самая частая причина «сервер не отвечает»:

1. Networking → Virtual Cloud Networks → ваша сеть → Security Lists →
   добавить Ingress Rules для TCP 80 и 443 с источником `0.0.0.0/0`.
2. На самом сервере ubuntu по умолчанию фильтрует трафик:

```bash
sudo iptables -I INPUT 1 -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT 1 -p tcp --dport 443 -j ACCEPT
sudo netfilter-persistent save
```

## 2. Docker

```bash
sudo apt update && sudo apt install -y docker.io docker-compose-v2 git
sudo usermod -aG docker $USER
```

Выйдите и зайдите снова, чтобы членство в группе применилось.

## 3. Домен

Создайте у регистратора или в Cloudflare запись:

| Поле | Значение |
|---|---|
| Тип | `A` |
| Имя | поддомен, например `ismc` |
| Значение | публичный IP сервера |
| Проксирование | **выключено** (в Cloudflare — серое облако) |

Проксирование Cloudflare нужно выключить, иначе Caddy не сможет пройти
проверку владения доменом и не выпустит сертификат. Включить обратно можно
позже, когда сертификат уже получен.

Дождитесь, пока запись разойдётся:

```bash
dig +short ismc.example.ru
```

Пока команда не вернёт IP сервера, дальше идти бессмысленно.

## 4. Запуск

```bash
git clone https://github.com/acmtco/ISMC.git && cd ISMC
echo "HG_DOMAIN=ismc.example.ru" > .env
docker compose -f docker-compose.prod.yml --profile tls up -d --build
```

Первая сборка занимает 5–10 минут: ставятся зависимости и собирается
интерфейс. PyTorch в образ не входит, поэтому на ARM это терпимо.

Проверка:

```bash
docker compose -f docker-compose.prod.yml ps
curl -s https://ismc.example.ru/health
```

Ожидаемый ответ — `{"status":"ok"}`.

## 5. Что происходит при старте

База данных создаётся в именованном томе `hronograf-data` и переживает
пересборку образа. При первом запуске она пуста, и приложение само:

1. заполняет справочники объекта, камер и зон;
2. импортирует календарный график;
3. пересчитывает машино-часы и отклонения из `data/interim/detections/`
   тем же кодом, что и ночной пересчёт.

Никакие числа не подставляются готовыми: всё считается из накопленных
детекций. Шаг идемпотентен, при непустой базе он пропускается.

## Обновление

```bash
git pull && docker compose -f docker-compose.prod.yml up -d --build
```

## Полезные команды

```bash
docker compose -f docker-compose.prod.yml logs -f app     # логи приложения
docker compose -f docker-compose.prod.yml logs -f caddy   # логи сертификата
docker compose -f docker-compose.prod.yml restart app     # перезапуск
docker compose -f docker-compose.prod.yml down            # остановка
```

Сбросить базу и пересчитать всё заново:

```bash
docker compose -f docker-compose.prod.yml down
docker volume rm ismc_hronograf-data
docker compose -f docker-compose.prod.yml up -d
```

## Если что-то не работает

**Сертификат не выпускается.** Смотрите логи Caddy. Обычные причины: домен
ещё не разошёлся по DNS, закрыт порт 80 (он нужен для проверки владения),
включено проксирование Cloudflare.

**Сервер не отвечает, хотя контейнеры запущены.** Порты открыты только в
одном из двух мест — проверьте и Security List, и iptables на сервере.

**Экраны пустые.** Посмотрите `docker compose logs app`: при успешном
старте там есть строка «стартовый пересчёт OBJ-001». Если её нет, значит не
нашёлся файл детекций.

## Перевод на PostgreSQL

SQLite достаточно для демонстрации. Для постоянной эксплуатации добавьте
сервис базы в compose и смените одну переменную:

```yaml
HG_DB_URL: postgresql+psycopg://hronograf:пароль@db:5432/hronograf
```

Правки кода не требуется.
