"""
Telegram бот для расчёта стоимости ремонта с веб-кабинетом.
Версия 2.0: SQLite + Flask + Telegram Inline Buttons
"""

import os
import sqlite3
import json
import logging
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Optional, Dict, List, Any
import hashlib

from flask import Flask, render_template_string, request, jsonify, send_file
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    ConversationHandler,
    filters,
)

# ============================================================================
# КОНФИГ
# ============================================================================

LOGGER = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parent
DB_PATH = PROJECT_ROOT / "master_data.db"
PDF_FONT_PATH = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
PDF_FONT_BOLD_PATH = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")

# Telegram токен (замень на свой)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "YOUR_TOKEN_HERE")

# Flask app
app = Flask(__name__)
app.secret_key = "secret_key_for_sessions"

# States for conversation
(
    ASK_TELEGRAM_USERNAME,
    ASK_VK_USERNAME,
    ASK_PROFI_PROFILE,
    ASK_PHONE,
    ASK_LENGTH,
    ASK_WIDTH,
    ASK_HEIGHT,
    ASK_SERVICES,
) = range(8)

# Цветовые схемы
COLOR_SCHEMES = {
    "default": {
        "primary": "#163C4A",
        "secondary": "#0B806F",
        "accent": "#EAF5F2",
        "text": "#27343B",
    },
    "blue": {
        "primary": "#003D82",
        "secondary": "#0066CC",
        "accent": "#E6F0FF",
        "text": "#1A1A1A",
    },
    "warm": {
        "primary": "#8B4513",
        "secondary": "#D2691E",
        "accent": "#FFF8DC",
        "text": "#2C1810",
    },
}

# Услуги
SERVICE_RATES = {
    "отделка": {"label": "Отделка стен", "rate": 1200, "basis": "м² стен", "area": "walls"},
    "покраска": {"label": "Покраска стен", "rate": 700, "basis": "м² стен", "area": "walls"},
    "обои": {"label": "Поклейка обоев", "rate": 650, "basis": "м² стен", "area": "walls"},
    "штукатурка": {"label": "Штукатурка стен", "rate": 800, "basis": "м² стен", "area": "walls"},
    "плитка": {"label": "Укладка плитки", "rate": 1800, "basis": "м² пола", "area": "floor"},
    "ламинат": {"label": "Укладка ламината", "rate": 1200, "basis": "м² пола", "area": "floor"},
    "пол": {"label": "Работа с напольным покрытием", "rate": 1200, "basis": "м² пола", "area": "floor"},
    "потолок": {"label": "Отделка потолка", "rate": 900, "basis": "м² потолка", "area": "ceiling"},
    "электрика": {"label": "Электромонтаж", "rate": 1000, "basis": "м² пола", "area": "floor"},
    "сантехника": {"label": "Сантехнические работы", "rate": 1200, "basis": "м² пола", "area": "floor"},
    "демонтаж": {"label": "Демонтажные работы", "rate": 350, "basis": "м² поверхностей", "area": "surfaces"},
    "прочее": {"label": "Прочие работы", "rate": 500, "basis": "м² пола", "area": "floor"},
}

# ============================================================================
# DATABASE
# ============================================================================

def init_db():
    """Инициализация базы данных"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Таблица мастеров
    c.execute("""
        CREATE TABLE IF NOT EXISTS masters (
            master_id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER UNIQUE NOT NULL,
            telegram_username TEXT NOT NULL,
            vk_username TEXT,
            profi_profile TEXT,
            phone TEXT,
            color_scheme TEXT DEFAULT 'default',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Таблица смет
    c.execute("""
        CREATE TABLE IF NOT EXISTS estimates (
            estimate_id INTEGER PRIMARY KEY AUTOINCREMENT,
            master_id INTEGER NOT NULL,
            length REAL NOT NULL,
            width REAL NOT NULL,
            height REAL NOT NULL,
            services TEXT NOT NULL,
            total_cost REAL NOT NULL,
            pdf_data BLOB,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (master_id) REFERENCES masters(master_id)
        )
    """)
    
    conn.commit()
    conn.close()

def get_master_by_telegram_id(telegram_id: int) -> Optional[Dict]:
    """Получить мастера по Telegram ID"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM masters WHERE telegram_id = ?", (telegram_id,))
    result = c.fetchone()
    conn.close()
    return dict(result) if result else None

def save_master(telegram_id: int, username: str, vk: str, profi: str, phone: str, color_scheme: str = "default") -> int:
    """Сохранить/обновить профиль мастера"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    master = get_master_by_telegram_id(telegram_id)
    
    if master:
        c.execute("""
            UPDATE masters 
            SET telegram_username=?, vk_username=?, profi_profile=?, phone=?, color_scheme=?
            WHERE telegram_id = ?
        """, (username, vk, profi, phone, color_scheme, telegram_id))
        master_id = master['master_id']
    else:
        c.execute("""
            INSERT INTO masters (telegram_id, telegram_username, vk_username, profi_profile, phone, color_scheme)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (telegram_id, username, vk, profi, phone, color_scheme))
        master_id = c.lastrowid
    
    conn.commit()
    conn.close()
    return master_id

def save_estimate(master_id: int, length: float, width: float, height: float, services: List[str], total_cost: float, pdf_data: bytes):
    """Сохранить смету"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    services_json = json.dumps(services)
    c.execute("""
        INSERT INTO estimates (master_id, length, width, height, services, total_cost, pdf_data)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (master_id, length, width, height, services_json, total_cost, pdf_data))
    conn.commit()
    conn.close()

def get_master_estimates(master_id: int) -> List[Dict]:
    """Получить все сметы мастера"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("""
        SELECT * FROM estimates WHERE master_id = ? ORDER BY created_at DESC
    """, (master_id,))
    results = c.fetchall()
    conn.close()
    return [dict(row) for row in results]

# ============================================================================
# PDF GENERATOR
# ============================================================================

def register_fonts():
    """Регистрация шрифтов"""
    if PDF_FONT_PATH.exists() and PDF_FONT_BOLD_PATH.exists():
        pdfmetrics.registerFont(TTFont("DejaVuSans", str(PDF_FONT_PATH)))
        pdfmetrics.registerFont(TTFont("DejaVuSansBold", str(PDF_FONT_BOLD_PATH)))

def format_money(value: float) -> str:
    """Форматирование денег"""
    return f"{round(value):,.0f}".replace(",", " ") + " ₽"

def generate_pdf(master_data: Dict, room_data: Dict, services: List[str], colors_scheme: str = "default") -> bytes:
    """Генерация PDF сметы"""
    register_fonts()
    
    colors_dict = COLOR_SCHEMES.get(colors_scheme, COLOR_SCHEMES["default"])
    
    length = room_data["length"]
    width = room_data["width"]
    height = room_data["height"]
    
    floor_area = length * width
    ceiling_area = floor_area
    walls_area = 2 * (length + width) * height
    surfaces_area = floor_area + walls_area
    
    # Расчёты
    rows = []
    total = 0.0
    
    for service_key in services:
        if service_key in SERVICE_RATES:
            service = SERVICE_RATES[service_key]
            area_type = service["area"]
            
            if area_type == "floor":
                area = floor_area
            elif area_type == "ceiling":
                area = ceiling_area
            elif area_type == "walls":
                area = walls_area
            else:
                area = surfaces_area
            
            cost = area * service["rate"]
            total += cost
            rows.append({
                "label": service["label"],
                "area": area,
                "basis": service["basis"],
                "rate": service["rate"],
                "cost": cost,
            })
    
    room_title = f"{length:g} × {width:g} × {height:g} м"
    created_at = datetime.now().strftime("%d.%m.%Y %H:%M")
    
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=16 * mm,
        leftMargin=16 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
    )
    
    styles = getSampleStyleSheet()
    
    # Стили
    logo_title = ParagraphStyle(
        "LogoTitle",
        parent=styles["Title"],
        fontName="DejaVuSansBold",
        fontSize=22,
        textColor=colors.white,
        alignment=TA_LEFT,
    )
    
    section_style = ParagraphStyle(
        "Section",
        parent=styles["Heading2"],
        fontName="DejaVuSansBold",
        fontSize=14,
        textColor=colors.HexColor(colors_dict["primary"]),
        spaceBefore=12,
        spaceAfter=8,
    )
    
    normal_style = ParagraphStyle(
        "Normal",
        parent=styles["Normal"],
        fontName="DejaVuSans",
        fontSize=9,
        textColor=colors.HexColor(colors_dict["text"]),
    )
    
    table_header_style = ParagraphStyle(
        "TableHeader",
        parent=normal_style,
        fontName="DejaVuSansBold",
        textColor=colors.white,
        fontSize=8.5,
    )
    
    # Логотип
    logo_table = Table(
        [["Смета на ремонт"]],
        colWidths=[172 * mm],
    )
    logo_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(colors_dict["primary"])),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 16),
        ("TOPPADDING", (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
    ]))
    logo_para = Paragraph("Смета на ремонт", logo_title)
    
    # Метрики
    metrics_data = [
        ["РАЗМЕРЫ", "ПЛОЩАДЬ ПОЛА", "ПЛОЩАДЬ СТЕН"],
        [room_title, f"{floor_area:.2f} м²", f"{walls_area:.2f} м²"],
    ]
    metrics_table = Table(metrics_data, colWidths=[57 * mm, 57 * mm, 57 * mm])
    metrics_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(colors_dict["primary"])),
        ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor(colors_dict["accent"])),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "DejaVuSansBold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.grey),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
    ]))
    
    # Таблица услуг
    service_data = [["Услуга", "Объём", "Цена", "Стоимость"]]
    for row in rows:
        service_data.append([
            row["label"],
            f"{row['area']:.2f} {row['basis']}",
            format_money(row["rate"]),
            format_money(row["cost"]),
        ])
    service_data.append(["", "", "ИТОГО", format_money(total)])
    
    service_table = Table(service_data, colWidths=[67 * mm, 37 * mm, 30 * mm, 38 * mm])
    service_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(colors_dict["primary"])),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "DejaVuSansBold"),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor(colors_dict["accent"])),
        ("FONTNAME", (0, -1), (-1, -1), "DejaVuSansBold"),
        ("TEXTCOLOR", (0, -1), (-1, -1), colors.HexColor(colors_dict["secondary"])),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.grey),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.grey),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("ALIGN", (3, 1), (3, -1), "RIGHT"),
    ]))
    
    # Контакты
    contact_text = f"""
    <b>Контакты мастера</b><br/>
    Telegram: @{master_data.get('telegram_username', 'N/A')}<br/>
    VK: {master_data.get('vk_username', 'N/A')}<br/>
    Profi: {master_data.get('profi_profile', 'N/A')}<br/>
    Телефон: {master_data.get('phone', 'N/A')}
    """
    
    contacts_table = Table([[Paragraph(contact_text, normal_style)]], colWidths=[172 * mm])
    contacts_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(colors_dict["accent"])),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.grey),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))
    
    note = Paragraph(
        "Расчёт ориентировочный. Точная стоимость зависит от состояния помещения и фактического объёма работ.",
        ParagraphStyle("Note", parent=normal_style, fontSize=7, alignment=TA_CENTER)
    )
    
    story = [
        Paragraph("Смета на ремонт", logo_title),
        Spacer(1, 3 * mm),
        Paragraph(f"Сформировано {created_at}", normal_style),
        Spacer(1, 5 * mm),
        metrics_table,
        Spacer(1, 5 * mm),
        Paragraph("Перечень работ", section_style),
        service_table,
        Spacer(1, 8 * mm),
        contacts_table,
        Spacer(1, 3 * mm),
        note,
    ]
    
    doc.build(story)
    return buffer.getvalue()

# ============================================================================
# TELEGRAM BOT
# ============================================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Команда /start"""
    telegram_id = update.effective_user.id
    master = get_master_by_telegram_id(telegram_id)
    
    if master:
        # Есть профиль - переходим сразу к размерам
        keyboard = [
            [InlineKeyboardButton("Новая смета", callback_data="new_estimate")],
            [InlineKeyboardButton("Мой кабинет", callback_data="cabinet")],
            [InlineKeyboardButton("Обновить профиль", callback_data="update_profile")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f"Добро пожаловать, {master['telegram_username']}!\n\nЧто вы хотите сделать?",
            reply_markup=reply_markup
        )
        return ConversationHandler.END
    else:
        # Новый профиль
        context.user_data.clear()
        await update.message.reply_text(
            "Здравствуйте! 👋\n\n"
            "Я помогу вам создать смету на ремонт.\n\n"
            "Сначала заполним ваш профиль.\n\n"
            "Шаг 1/5: Укажите ваш Telegram юзернейм (можно с @)"
        )
        return ASK_TELEGRAM_USERNAME

async def ask_telegram_username(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Запрос Telegram юзернейма"""
    username = update.message.text.strip().lstrip("@")
    if not username:
        await update.message.reply_text("Юзернейм не может быть пустым. Попробуйте ещё раз.")
        return ASK_TELEGRAM_USERNAME
    context.user_data["telegram_username"] = username
    await update.message.reply_text("Шаг 2/5: Укажите ваш VK юзернейм")
    return ASK_VK_USERNAME

async def ask_vk_username(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Запрос VK юзернейма"""
    username = update.message.text.strip()
    if not username:
        await update.message.reply_text("VK юзернейм не может быть пустым.")
        return ASK_VK_USERNAME
    context.user_data["vk_username"] = username
    await update.message.reply_text("Шаг 3/5: Пришлите ссылку на профиль в Profi.ru\n(например: https://profi.ru/profile/...)")
    return ASK_PROFI_PROFILE

async def ask_profi_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Запрос Profi профиля"""
    profile = update.message.text.strip()
    if not profile.startswith("http"):
        await update.message.reply_text("Нужна полная ссылка, начинающаяся с http:// или https://")
        return ASK_PROFI_PROFILE
    context.user_data["profi_profile"] = profile
    await update.message.reply_text("Шаг 4/5: Укажите ваш номер телефона")
    return ASK_PHONE

async def ask_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Запрос телефона"""
    phone = update.message.text.strip()
    context.user_data["phone"] = phone
    
    # Сохраняем профиль
    telegram_id = update.effective_user.id
    master_id = save_master(
        telegram_id,
        context.user_data["telegram_username"],
        context.user_data["vk_username"],
        context.user_data["profi_profile"],
        phone,
        "default"
    )
    context.user_data["master_id"] = master_id
    
    await update.message.reply_text(
        "✅ Профиль сохранён!\n\n"
        "Теперь готовим смету.\n\n"
        "Шаг 5/5: Укажите длину комнаты в метрах (например: 5 или 5.5)"
    )
    return ASK_LENGTH

async def ask_length(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Запрос длины комнаты"""
    try:
        length = float(update.message.text.replace(",", "."))
        if length <= 0:
            raise ValueError
        context.user_data["length"] = length
        await update.message.reply_text("Укажите ширину комнаты в метрах")
        return ASK_WIDTH
    except:
        await update.message.reply_text("Введите положительное число, например 5 или 5.5")
        return ASK_LENGTH

async def ask_width(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Запрос ширины комнаты"""
    try:
        width = float(update.message.text.replace(",", "."))
        if width <= 0:
            raise ValueError
        context.user_data["width"] = width
        await update.message.reply_text("Укажите высоту потолка в метрах")
        return ASK_HEIGHT
    except:
        await update.message.reply_text("Введите положительное число, например 2.7")
        return ASK_WIDTH

async def ask_height(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Запрос высоты потолка"""
    try:
        height = float(update.message.text.replace(",", "."))
        if height <= 0:
            raise ValueError
        context.user_data["height"] = height
        
        # Показываем услуги с кнопками
        await show_services_keyboard(update, context)
        return ASK_SERVICES
    except:
        await update.message.reply_text("Введите положительное число, например 2.7")
        return ASK_HEIGHT

async def show_services_keyboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать услуги с кнопками-чекбоксами"""
    keyboard = []
    for i, (service_key, service_info) in enumerate(SERVICE_RATES.items()):
        callback = f"service_{service_key}"
        keyboard.append([InlineKeyboardButton(f"☐ {service_info['label']}", callback_data=callback)])
    
    keyboard.append([InlineKeyboardButton("✅ Готово! Создать смету", callback_data="generate_estimate")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Выберите услуги (нажимайте на кнопки):\n\n☐ - не выбрано\n☑ - выбрано",
        reply_markup=reply_markup
    )

async def service_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка выбора услуги"""
    query = update.callback_query
    await query.answer()
    
    if "services" not in context.user_data:
        context.user_data["services"] = []
    
    # Извлекаем ключ услуги из callback_data
    service_key = query.data.replace("service_", "")
    
    # Переключаем выбор
    if service_key in context.user_data["services"]:
        context.user_data["services"].remove(service_key)
    else:
        context.user_data["services"].append(service_key)
    
    # Обновляем клавиатуру
    await show_services_keyboard_updated(query, context)
    return ASK_SERVICES

async def show_services_keyboard_updated(query, context: ContextTypes.DEFAULT_TYPE):
    """Обновить клавиатуру услуг"""
    selected = context.user_data.get("services", [])
    keyboard = []
    
    for service_key, service_info in SERVICE_RATES.items():
        checkbox = "☑" if service_key in selected else "☐"
        label = f"{checkbox} {service_info['label']}"
        callback = f"service_{service_key}"
        keyboard.append([InlineKeyboardButton(label, callback_data=callback)])
    
    keyboard.append([InlineKeyboardButton("✅ Готово! Создать смету", callback_data="generate_estimate")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_reply_markup(reply_markup=reply_markup)

async def generate_estimate_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Генерация и отправка сметы"""
    query = update.callback_query
    await query.answer()
    
    services = context.user_data.get("services", [])
    if not services:
        await query.edit_message_text("❌ Выберите хотя бы одну услугу!")
        return ASK_SERVICES
    
    # Получаем данные мастера
    master_id = context.user_data.get("master_id")
    master = get_master_by_telegram_id(update.effective_user.id)
    
    room_data = {
        "length": context.user_data["length"],
        "width": context.user_data["width"],
        "height": context.user_data["height"],
    }
    
    # Генерируем PDF
    pdf_bytes = generate_pdf(master, room_data, services, master.get("color_scheme", "default"))
    
    # Расчёт стоимости
    length, width, height = room_data["length"], room_data["width"], room_data["height"]
    floor_area = length * width
    walls_area = 2 * (length + width) * height
    ceiling_area = floor_area
    surfaces_area = floor_area + walls_area
    total = 0.0
    
    for service_key in services:
        service = SERVICE_RATES[service_key]
        area_type = service["area"]
        if area_type == "floor":
            area = floor_area
        elif area_type == "ceiling":
            area = ceiling_area
        elif area_type == "walls":
            area = walls_area
        else:
            area = surfaces_area
        total += area * service["rate"]
    
    # Сохраняем смету в БД
    save_estimate(master_id, room_data["length"], room_data["width"], room_data["height"], services, total, pdf_bytes)
    
    # Отправляем PDF
    from telegram import InputFile
    file = InputFile(BytesIO(pdf_bytes), filename="smeta_na_remont.pdf")
    
    text = f"""
✅ Смета готова!

📏 Размеры: {room_data["length"]} × {room_data["width"]} × {room_data["height"]} м
💰 Ориентировочная стоимость: {format_money(total)}

PDF отправлен ниже 👇
    """
    
    await query.edit_message_text(text)
    await query.message.reply_document(document=file, caption="📄 Смета на ремонт")
    
    # Кнопки для продолжения
    keyboard = [
        [InlineKeyboardButton("📋 Новая смета", callback_data="new_estimate")],
        [InlineKeyboardButton("📚 Мой кабинет", callback_data="cabinet")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.reply_text("Что дальше?", reply_markup=reply_markup)
    
    return ConversationHandler.END

async def new_estimate_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Создание новой сметы"""
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    context.user_data["master_id"] = get_master_by_telegram_id(update.effective_user.id)["master_id"]
    
    await query.edit_message_text("Укажите длину комнаты в метрах:")
    return ASK_LENGTH

async def cabinet_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Личный кабинет"""
    query = update.callback_query
    await query.answer()
    
    # Ссылка на веб-кабинет (будет на Flask)
    cabinet_url = f"http://localhost:5000/cabinet/{update.effective_user.id}"
    
    keyboard = [[InlineKeyboardButton("🌐 Открыть кабинет", url=cabinet_url)]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "📚 Ваш личный кабинет\n\nТут вы найдёте все созданные сметы.",
        reply_markup=reply_markup
    )

# ============================================================================
# FLASK WEB APP
# ============================================================================

CABINET_HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Личный кабинет</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: #f5f7fa;
            color: #333;
        }
        .container { max-width: 1000px; margin: 0 auto; padding: 20px; }
        header {
            background: #163C4A;
            color: white;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 30px;
        }
        .master-info {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 15px;
            margin-top: 15px;
            font-size: 14px;
        }
        .estimates {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
            gap: 20px;
        }
        .estimate-card {
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            border-left: 4px solid #0B806F;
        }
        .estimate-card h3 { color: #163C4A; margin-bottom: 10px; }
        .estimate-info { font-size: 14px; color: #666; margin: 8px 0; }
        .estimate-info b { color: #163C4A; }
        .btn {
            display: inline-block;
            padding: 8px 16px;
            background: #0B806F;
            color: white;
            text-decoration: none;
            border-radius: 4px;
            margin-top: 12px;
            border: none;
            cursor: pointer;
            font-size: 14px;
        }
        .btn:hover { background: #055a52; }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>📊 Личный кабинет</h1>
            <div class="master-info">
                <div>Telegram: <b>@{{ master.telegram_username }}</b></div>
                <div>VK: <b>{{ master.vk_username }}</b></div>
                <div>Телефон: <b>{{ master.phone }}</b></div>
                <div>Profi: <b><a href="{{ master.profi_profile }}" style="color: inherit;">Профиль</a></b></div>
            </div>
        </header>
        
        <h2 style="margin-bottom: 20px;">📋 Ваши сметы ({{ estimates|length }})</h2>
        
        {% if estimates %}
            <div class="estimates">
            {% for est in estimates %}
                <div class="estimate-card">
                    <h3>Смета #{{ est.estimate_id }}</h3>
                    <div class="estimate-info">
                        📏 {{ est.length }}м × {{ est.width }}м × {{ est.height }}м
                    </div>
                    <div class="estimate-info">
                        💰 {{ "%.0f"|format(est.total_cost) }} ₽
                    </div>
                    <div class="estimate-info">
                        📅 {{ est.created_at }}
                    </div>
                    <div class="estimate-info">
                        Услуг: <b>{{ est.services|length }}</b>
                    </div>
                    <a href="/download_estimate/{{ est.estimate_id }}" class="btn">📥 Скачать PDF</a>
                </div>
            {% endfor %}
            </div>
        {% else %}
            <p style="text-align: center; color: #999; padding: 40px;">
                У вас ещё нет сметы. Создайте первую через Telegram бота!
            </p>
        {% endif %}
    </div>
</body>
</html>
"""

@app.route("/cabinet/<int:telegram_id>")
def cabinet(telegram_id):
    """Личный кабинет"""
    master = get_master_by_telegram_id(telegram_id)
    if not master:
        return "Master not found", 404
    
    estimates = get_master_estimates(master["master_id"])
    
    # Преобразуем JSON услуг
    for est in estimates:
        est["services"] = json.loads(est["services"])
    
    return render_template_string(CABINET_HTML, master=master, estimates=estimates)

@app.route("/download_estimate/<int:estimate_id>")
def download_estimate(estimate_id):
    """Скачать смету"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT pdf_data FROM estimates WHERE estimate_id = ?", (estimate_id,))
    result = c.fetchone()
    conn.close()
    
    if not result:
        return "Not found", 404
    
    return send_file(
        BytesIO(result["pdf_data"]),
        mimetype="application/pdf",
        as_attachment=True,
        download_name="smeta_na_remont.pdf"
    )

# ============================================================================
# MAIN
# ============================================================================

def main():
    """Запуск бота и веб-приложения"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Инициализируем БД
    init_db()
    
    # Telegram бот
    app_bot = (
        ApplicationBuilder()
        .token(TELEGRAM_TOKEN)
        .build()
    )
    
    conversation_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            ASK_TELEGRAM_USERNAME: [MessageHandler(filters.TEXT, ask_telegram_username)],
            ASK_VK_USERNAME: [MessageHandler(filters.TEXT, ask_vk_username)],
            ASK_PROFI_PROFILE: [MessageHandler(filters.TEXT, ask_profi_profile)],
            ASK_PHONE: [MessageHandler(filters.TEXT, ask_phone)],
            ASK_LENGTH: [MessageHandler(filters.TEXT, ask_length)],
            ASK_WIDTH: [MessageHandler(filters.TEXT, ask_width)],
            ASK_HEIGHT: [MessageHandler(filters.TEXT, ask_height)],
            ASK_SERVICES: [
                CallbackQueryHandler(service_callback, pattern="^service_"),
                CallbackQueryHandler(generate_estimate_callback, pattern="^generate_estimate$"),
            ],
        },
        fallbacks=[],
    )
    
    app_bot.add_handler(conversation_handler)
    app_bot.add_handler(CallbackQueryHandler(new_estimate_callback, pattern="^new_estimate$"))
    app_bot.add_handler(CallbackQueryHandler(cabinet_callback, pattern="^cabinet$"))
    
    # Запускаем бота в отдельном потоке
    import threading
    bot_thread = threading.Thread(target=lambda: app_bot.run_polling())
    bot_thread.daemon = True
    bot_thread.start()
    
    # Запускаем Flask
    LOGGER.info("Запускаю Flask на http://localhost:5000")
    app.run(host="0.0.0.0", port=5000, debug=False)

if __name__ == "__main__":
    main()
