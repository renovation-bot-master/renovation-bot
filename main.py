import os
import json
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from io import BytesIO

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

try:
    pdfmetrics.registerFont(TTFont('DejaVu', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'))
except:
    pass

PROFILE_FILE = "profile.json"
ESTIMATES_FILE = "estimates.json"
PRICES_FILE = "prices.json"

DEFAULT_PRICES = {
    "Поклейка виниловых обоев": 350,
    "Демонтаж старых обоев": 100,
    "Грунтовка стен": 80
}

def init_files():
    for file, data in [(PRICES_FILE, DEFAULT_PRICES), (ESTIMATES_FILE, [])]:
        if not os.path.exists(file):
            with open(file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

def load_json(file):
    try:
        with open(file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {} if file == PROFILE_FILE else []

def save_json(file, data):
    with open(file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def format_phone(phone):
    phone = phone.replace('+', '').replace('-', '').replace(' ', '')
    if phone.startswith('7'):
        phone = '8' + phone[1:]
    elif not phone.startswith('8'):
        phone = '8' + phone
    return phone

def get_menu_buttons():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("📋 Смета", callback_data="create_estimate"),
        InlineKeyboardButton("👤 Профиль", callback_data="profile_info"),
        InlineKeyboardButton("📊 История", callback_data="view_history")
    ]])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    profile = load_json(PROFILE_FILE)
    if profile.get('name'):
        text = "👋 Добро пожаловать обратно!"
        await update.message.reply_text(text, reply_markup=get_menu_buttons())
    else:
        text = "👋 <b>Добро пожаловать!</b>\n\n"
        text += "Это бот для составления смет на ремонт.\n\n"
        text += "📋 Функции:\n"
        text += "✅ Выбор услуг\n"
        text += "✅ Расчёт стоимости\n"
        text += "✅ PDF смета\n"
        text += "✅ История\n\n"
        text += "<b>Давайте создадим профиль!</b>"
        keyboard = [[InlineKeyboardButton("➡️ Начать", callback_data="start_setup")]]
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "start_setup":
        context.user_data['setup_step'] = 'name'
        await query.edit_message_text("📝 <b>Шаг 1 из 5</b>\n\nВведите название компании или имя:", parse_mode="HTML", reply_markup=get_menu_buttons())
    elif query.data == "profile_info":
        profile = load_json(PROFILE_FILE)
        text = "👤 <b>Ваш профиль</b>\n\n"
        text += f"Название: <b>{profile.get('name', '—')}</b>\n"
        text += f"Телефон: <b>{profile.get('phone', '—')}</b>\n"
        text += f"ВК: {profile.get('vk', '—')}\n"
        text += f"Telegram: {profile.get('telegram', '—')}"
        keyboard = [[InlineKeyboardButton("✏️ Редактировать", callback_data="edit_profile")], [InlineKeyboardButton("◀️ Назад", callback_data="back_menu")]]
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
    elif query.data == "edit_profile":
        profile = load_json(PROFILE_FILE)
        text = "⚙️ <b>Редактировать</b>\n\n"
        text += f"Название: {profile.get('name', '—')}\n"
        text += f"Телефон: {profile.get('phone', '—')}\n"
        text += f"ВК: {profile.get('vk', '—')}\n"
        text += f"Telegram: {profile.get('telegram', '—')}"
        keyboard = [[InlineKeyboardButton("✏️ Название", callback_data="edit_name")], [InlineKeyboardButton("✏️ Телефон", callback_data="edit_phone")], [InlineKeyboardButton("✏️ ВК", callback_data="edit_vk")], [InlineKeyboardButton("✏️ Telegram", callback_data="edit_telegram")], [InlineKeyboardButton("◀️ Назад", callback_data="back_menu")]]
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
    elif query.data == "edit_name":
        context.user_data['edit_field'] = 'name'
        await query.edit_message_text("✏️ Введите новое название:", reply_markup=get_menu_buttons())
    elif query.data == "edit_phone":
        context.user_data['edit_field'] = 'phone'
        await query.edit_message_text("✏️ Введите новый телефон:", reply_markup=get_menu_buttons())
    elif query.data == "edit_vk":
        context.user_data['edit_field'] = 'vk'
        await query.edit_message_text("✏️ Введите ВК (или 'пропустить'):", reply_markup=get_menu_buttons())
    elif query.data == "edit_telegram":
        context.user_data['edit_field'] = 'telegram'
        await query.edit_message_text("✏️ Введите Telegram (или 'пропустить'):", reply_markup=get_menu_buttons())
    elif query.data == "create_estimate":
        context.user_data['selected'] = {}
        prices = load_json(PRICES_FILE)
        text = "📋 <b>Выберите услуги:</b>"
        keyboard = []
        for service in prices:
            keyboard.append([InlineKeyboardButton(f"☐ {service} ({prices[service]} ₽/м²)", callback_data=f"srv_{service}")])
        keyboard.append([InlineKeyboardButton("✅ Готово", callback_data="confirm_srv")])
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
    elif query.data.startswith("srv_"):
        service = query.data.replace("srv_", "")
        if service in context.user_data['selected']:
            del context.user_data['selected'][service]
        else:
            context.user_data['selected'][service] = True
        prices = load_json(PRICES_FILE)
        text = "📋 <b>Выберите услуги:</b>"
        keyboard = []
        for s in prices:
            icon = "☑️" if s in context.user_data['selected'] else "☐"
            keyboard.append([InlineKeyboardButton(f"{icon} {s} ({prices[s]} ₽/м²)", callback_data=f"srv_{s}")])
        keyboard.append([InlineKeyboardButton("✅ Готово", callback_data="confirm_srv")])
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
    elif query.data == "confirm_srv":
        if not context.user_data['selected']:
            await query.answer("⚠️ Выберите услугу!")
            return
        context.user_data['estimate_step'] = 'size'
        await query.edit_message_text("📐 <b>Размеры (Д Ш В):</b>\n\nПример: 5 4 3", parse_mode="HTML", reply_markup=get_menu_buttons())
    elif query.data == "view_history":
        estimates = load_json(ESTIMATES_FILE)
        if not estimates:
            keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="back_menu")]]
            await query.edit_message_text("📊 История пуста", reply_markup=InlineKeyboardMarkup(keyboard))
            return
        text = "📊 <b>История:</b>"
        keyboard = []
        for i, est in enumerate(reversed(estimates)):
            keyboard.append([InlineKeyboardButton(f"{est['date']} - {est['total']:.0f}₽", callback_data=f"est_{len(estimates)-1-i}")])
        keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="back_menu")])
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
    elif query.data.startswith("est_"):
        idx = int(query.data.replace("est_", ""))
        estimates = load_json(ESTIMATES_FILE)
        est = estimates[idx]
        text = f"📄 <b>Смета {est['date']}</b>\n\n"
        text += f"📍 {est['address']}\n\n"
        for srv, data in est['services'].items():
            text += f"{srv}: {data['total']:.0f}₽\n"
        text += f"\n<b>Итого: {est['total']:.0f}₽</b>"
        keyboard = [[InlineKeyboardButton("📥 PDF", callback_data=f"pdf_{idx}")], [InlineKeyboardButton("◀️ Назад", callback_data="view_history")]]
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
    elif query.data.startswith("pdf_"):
        idx = int(query.data.replace("pdf_", ""))
        await generate_pdf(update, context, idx)
    elif query.data == "back_menu":
        await query.edit_message_text("🏠 <b>Меню</b>", parse_mode="HTML", reply_markup=get_menu_buttons())

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    profile = load_json(PROFILE_FILE)
    if context.user_data.get('setup_step') == 'name':
        profile['name'] = text
        save_json(PROFILE_FILE, profile)
        context.user_data['setup_step'] = 'phone'
        await update.message.reply_text("📝 <b>Шаг 2 из 5</b>\n\nТелефон (8ххххххххх):", parse_mode="HTML", reply_markup=get_menu_buttons())
    elif context.user_data.get('setup_step') == 'phone':
        phone = format_phone(text)
        profile['phone'] = phone
        save_json(PROFILE_FILE, profile)
        context.user_data['setup_step'] = 'vk'
        await update.message.reply_text("📝 <b>Шаг 3 из 5</b>\n\nВК (или 'пропустить'):", parse_mode="HTML", reply_markup=get_menu_buttons())
    elif context.user_data.get('setup_step') == 'vk':
        vk = '' if text.lower() == 'пропустить' else text
        profile['vk'] = vk
        save_json(PROFILE_FILE, profile)
        context.user_data['setup_step'] = 'telegram'
        await update.message.reply_text("📝 <b>Шаг 4 из 5</b>\n\nTelegram (или 'пропустить'):", parse_mode="HTML", reply_markup=get_menu_buttons())
    elif context.user_data.get('setup_step') == 'telegram':
        telegram = '' if text.lower() == 'пропустить' else text
        profile['telegram'] = telegram
        save_json(PROFILE_FILE, profile)
        context.user_data['setup_step'] = None
        msg = "✅ <b>Профиль готов!</b>\n\n"
        msg += f"Название: <b>{profile['name']}</b>\n"
        msg += f"Телефон: <b>{profile['phone']}</b>\n"
        msg += f"ВК: {profile.get('vk', '—')}\n"
        msg += f"Telegram: {profile.get('telegram', '—')}"
        await update.message.reply_text(msg, parse_mode="HTML", reply_markup=get_menu_buttons())
    elif context.user_data.get('edit_field'):
        field = context.user_data['edit_field']
        value = text
        if field == 'phone':
            value = format_phone(value)
        elif field in ['vk', 'telegram'] and text.lower() == 'пропустить':
            value = ''
        profile[field] = value
        save_json(PROFILE_FILE, profile)
        context.user_data['edit_field'] = None
        await update.message.reply_text(f"✅ {field} обновлен!", reply_markup=get_menu_buttons())
    elif context.user_data.get('estimate_step') == 'size':
        try:
            parts = text.split()
            if len(parts) != 3:
                await update.message.reply_text("❌ Ошибка! Формат: 5 4 3", reply_markup=get_menu_buttons())
                return
            d, sh, v = map(float, parts)
            area = ((d + sh) * 2) * v
            context.user_data['size'] = (d, sh, v)
            context.user_data['area'] = area
            context.user_data['estimate_step'] = 'address'
            msg = f"✅ Размеры: {d}×{sh}×{v}м\n📐 Площадь: {area:.2f}м²\n\n📍 Адрес объекта:"
            await update.message.reply_text(msg, reply_markup=get_menu_buttons())
        except:
            await update.message.reply_text("❌ Ошибка! Введите числа", reply_markup=get_menu_buttons())
    elif context.user_data.get('estimate_step') == 'address':
        context.user_data['address'] = text
        await generate_estimate_pdf(update, context)

async def generate_estimate_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    profile = load_json(PROFILE_FILE)
    prices = load_json(PRICES_FILE)
    selected = context.user_data['selected']
    area = context.user_data['area']
    address = context.user_data['address']
    estimate_data = {"date": datetime.now().strftime("%d.%m.%Y %H:%M"), "address": address, "services": {}, "total": 0}
    for service in selected:
        price = prices[service]
        cost = price * area
        estimate_data['services'][service] = {"price_per_m2": price, "area": area, "total": cost}
        estimate_data['total'] += cost
    estimates = load_json(ESTIMATES_FILE)
    estimates.append(estimate_data)
    save_json(ESTIMATES_FILE, estimates)
    pdf_buffer = BytesIO()
    doc = SimpleDocTemplate(pdf_buffer, pagesize=A4, rightMargin=0.8*cm, leftMargin=0.8*cm, topMargin=0.8*cm, bottomMargin=0.8*cm)
    story = []
    styles = getSampleStyleSheet()
    title = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=18, textColor=colors.HexColor('#1E90FF'), alignment=1, spaceAfter=15, fontName='DejaVu')
    story.append(Paragraph("СМЕТА НА РЕМОНТНЫЕ РАБОТЫ", title))
    info = ParagraphStyle('Info', parent=styles['Normal'], fontSize=11, spaceAfter=6, fontName='DejaVu')
    story.append(Paragraph(f"<b>Мастер:</b> {profile.get('name', '—')}", info))
    story.append(Paragraph(f"<b>Телефон:</b> {profile.get('phone', '—')}", info))
    if profile.get('vk'):
        story.append(Paragraph(f"<b>ВК:</b> {profile['vk']}", info))
    if profile.get('telegram'):
        story.append(Paragraph(f"<b>Telegram:</b> {profile['telegram']}", info))
    story.append(Spacer(1, 0.3*cm))
    story.append(Paragraph(f"<b>Адрес:</b> {address}", info))
    story.append(Paragraph(f"<b>Дата:</b> {estimate_data['date']}", info))
    story.append(Spacer(1, 0.4*cm))
    table_data = [['Услуга', 'Цена/м²', 'Площадь', 'Сумма']]
    for service, data in estimate_data['services'].items():
        table_data.append([service, f"{data['price_per_m2']}₽", f"{data['area']:.2f}м²", f"{data['total']:.0f}₽"])
    table_data.append(['', '', '<b>ИТОГО</b>', f"<b>{estimate_data['total']:.0f}₽</b>"])
    table = Table(table_data, colWidths=[5.5*cm, 1.8*cm, 1.8*cm, 1.8*cm])
    table.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1E90FF')), ('TEXTCOLOR', (0, 0), (-1, 0), colors.white), ('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('FONTNAME', (0, 0), (-1, 0), 'DejaVu'), ('FONTNAME', (0, 1), (-1, -1), 'DejaVu'), ('FONTSIZE', (0, 0), (-1, -1), 11), ('GRID', (0, 0), (-1, -1), 1, colors.black), ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#DDDDDD'))]))
    story.append(table)
    doc.build(story)
    pdf_buffer.seek(0)
    filename = f"smeta_{datetime.now().strftime('%d_%m_%Y_%H_%M')}.pdf"
    await context.bot.send_document(chat_id=update.effective_chat.id, document=pdf_buffer, filename=filename, caption=f"✅ Смета готова!\n💰 Итого: {estimate_data['total']:.0f}₽")
    context.user_data['estimate_step'] = None
    await update.message.reply_text("🎉 Отправлено!", reply_markup=get_menu_buttons())

async def generate_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE, idx: int):
    profile = load_json(PROFILE_FILE)
    estimates = load_json(ESTIMATES_FILE)
    est = estimates[idx]
    pdf_buffer = BytesIO()
    doc = SimpleDocTemplate(pdf_buffer, pagesize=A4, rightMargin=0.8*cm, leftMargin=0.8*cm, topMargin=0.8*cm, bottomMargin=0.8*cm)
    story = []
    styles = getSampleStyleSheet()
    title = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=18, textColor=colors.HexColor('#1E90FF'), alignment=1, spaceAfter=15, fontName='DejaVu')
    story.append(Paragraph("СМЕТА НА РЕМОНТНЫЕ РАБОТЫ", title))
    info = ParagraphStyle('Info', parent=styles['Normal'], fontSize=11, spaceAfter=6, fontName='DejaVu')
    story.append(Paragraph(f"<b>Мастер:</b> {profile.get('name', '—')}", info))
    story.append(Paragraph(f"<b>Телефон:</b> {profile.get('phone', '—')}", info))
    if profile.get('vk'):
        story.append(Paragraph(f"<b>ВК:</b> {profile['vk']}", info))
    if profile.get('telegram'):
        story.append(Paragraph(f"<b>Telegram:</b> {profile['telegram']}", info))
    story.append(Spacer(1, 0.3*cm))
    story.append(Paragraph(f"<b>Адрес:</b> {est['address']}", info))
    story.append(Paragraph(f"<b>Дата:</b> {est['date']}", info))
    story.append(Spacer(1, 0.4*cm))
    table_data = [['Услуга', 'Цена/м²', 'Площадь', 'Сумма']]
    for service, data in est['services'].items():
        table_data.append([service, f"{data['price_per_m2']}₽", f"{data['area']:.2f}м²", f"{data['total']:.0f}₽"])
    table_data.append(['', '', '<b>ИТОГО</b>', f"<b>{est['total']:.0f}₽</b>"])
    table = Table(table_data, colWidths=[5.5*cm, 1.8*cm, 1.8*cm, 1.8*cm])
    table.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1E90FF')), ('TEXTCOLOR', (0, 0), (-1, 0), colors.white), ('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('FONTNAME', (0, 0), (-1, 0), 'DejaVu'), ('FONTNAME', (0, 1), (-1, -1), 'DejaVu'), ('FONTSIZE', (0, 0), (-1, -1), 11), ('GRID', (0, 0), (-1, -1), 1, colors.black), ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#DDDDDD'))]))
    story.append(table)
    doc.build(story)
    pdf_buffer.seek(0)
    filename = f"smeta_{est['date'].replace('.', '_').replace(' ', '_').replace(':', '_')}.pdf"
    await context.bot.send_document(chat_id=update.effective_chat.id, document=pdf_buffer, filename=filename, caption=f"📄 Смета от {est['date']}\n💰 {est['total']:.0f}₽")

def main():
    init_files()
    token = os.getenv('TELEGRAM_TOKEN')
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CallbackQueryHandler(handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    logger.info("Бот запущен!")
    app.run_polling()

if __name__ == '__main__':
    main()
