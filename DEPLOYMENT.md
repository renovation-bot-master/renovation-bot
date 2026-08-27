# 🚀 РАЗВЁРТЫВАНИЕ НА RAILWAY

## ШАГ 1: Подготовка

```bash
# Клонируем/загружаем проект
git clone <your-repo> renovation-bot
cd renovation-bot
```

## ШАГ 2: Получи Telegram TOKEN

1. Найди @BotFather в Telegram
2. Отправь `/newbot`
3. Скопируй токен

## ШАГ 3: Создай Railway проект

1. Зайди на https://railway.app
2. Нажми "New Project"
3. Выбери "Deploy from GitHub"
4. Подключи GitHub репо

## ШАГ 4: Добавь переменные окружения

В Railway Dashboard → Variables:
```
TELEGRAM_TOKEN=твой_токен_от_BotFather
```

## ШАГ 5: Добавь Procfile

```
web: python main.py
```

## ШАГ 6: Готово!

Railway автоматически разовьёт проект.
Бот будет работать 24/7!

---

## ЛОКАЛЬНЫЙ ТЕСТ

```bash
pip install -r requirements.txt
export TELEGRAM_TOKEN="твой_токен"
python main.py
```

Затем в Telegram: @calcoboi_bot /start

---

## СТРУКТУРА БАЗЫ ДАННЫХ

- **master_data.db** - SQLite база
  - masters: профили мастеров
  - estimates: сметы

---

## ФУНКЦИИ

✅ Сохранение профиля мастера (один раз)
✅ Кнопки-чекбоксы для услуг
✅ PDF с выбранной цветовой гаммой
✅ Личный кабинет с историей смет
✅ Скачивание старых смет
✅ Работает 24/7 на Railway

---

## УЛУЧШЕНИЯ ДЛЯ СЛЕДУЮЩЕЙ ВЕРСИИ

1. Загрузка фото мастера
2. Выбор цветовой схемы в боте
3. Редактирование услуг (добавление своих)
4. Экспорт всех смет в один файл
5. Статистика (сколько смет, средняя стоимость)
6. Интеграция с платежами (Яндекс.Касса, PayPal)
