"""Обработчики для администратора"""
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from datetime import datetime, date, time
from typing import List

from services.user_service import UserService
from services.service_service import ServiceService
from services.schedule_service import ScheduleService
from services.appointment_service import AppointmentService
from services.info_service import InfoService
from services.bot_settings_service import BotSettingsService
from utils.timezone import format_datetime, format_date, get_current_datetime_in_master_tz
from database import db
from models import Appointment

router = Router()

class AdminStates(StatesGroup):
    """Состояния для админ-панели"""
    adding_service = State()
    editing_service = State()
    setting_schedule = State()
    editing_info = State()
    broadcast_message = State()
    adding_note = State()
    adding_tag = State()
    editing_appointment = State()
    editing_appointment_date = State()
    editing_appointment_time = State()
    editing_appointment_service = State()
    editing_appointment_status = State()
    editing_appointment_comment = State()
    selecting_broadcast_clients = State()
    setting_reminder_interval = State()
    adding_faq_question = State()
    adding_faq_answer = State()


@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext):
    """Админ-панель"""
    if not await UserService.is_admin(message.from_user.id):
        await message.answer("❌ У вас нет доступа к админ-панели")
        return
    
    await state.clear()
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Управление услугами", callback_data="admin_services")],
        [InlineKeyboardButton(text="📅 Управление расписанием", callback_data="admin_schedule")],
        [InlineKeyboardButton(text="👥 Управление клиентами", callback_data="admin_clients")],
        [InlineKeyboardButton(text="📊 История записей", callback_data="admin_history")],
        [InlineKeyboardButton(text="⚙️ Настройки бота", callback_data="admin_settings")],
        [InlineKeyboardButton(text="ℹ️ Управление информацией", callback_data="admin_info")],
        [InlineKeyboardButton(text="📢 Рассылка клиентам", callback_data="admin_broadcast")]
    ])
    
    await message.answer("⚙️ <b>Админ-панель</b>", reply_markup=keyboard, parse_mode='HTML')

@router.callback_query(F.data == "admin_services")
async def admin_services(callback: CallbackQuery):
    """Управление услугами"""
    services = await ServiceService.get_all_services(only_active=False)
    
    text = "📋 <b>Управление услугами</b>\n\n"
    
    keyboard_buttons = []
    for service in services:
        status = "✅" if service.is_active else "❌"
        additional_marker = "➕" if service.is_additional else "📋"
        keyboard_buttons.append([
            InlineKeyboardButton(
                text=f"{status} {additional_marker} {service.name} - {service.price:.0f} ₽",
                callback_data=f"admin_service_{service.id}"
            )
        ])
    
    keyboard_buttons.append([
        InlineKeyboardButton(text="➕ Добавить услугу", callback_data="admin_add_service")
    ])
    keyboard_buttons.append([
        InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")
    ])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode='HTML')

@router.callback_query(F.data == "admin_add_service")
async def admin_add_service_start(callback: CallbackQuery, state: FSMContext):
    """Начало добавления услуги"""
    await callback.message.edit_text(
        "➕ <b>Добавление новой услуги</b>\n\n"
        "Введите название услуги:",
        parse_mode='HTML'
    )
    await state.set_state(AdminStates.adding_service)
    await state.update_data(step='name')

@router.message(StateFilter(AdminStates.adding_service))
async def admin_add_service_process(message: Message, state: FSMContext):
    """Процесс добавления услуги"""
    data = await state.get_data()
    step = data.get('step')
    
    if step == 'name':
        await state.update_data(name=message.text)
        await message.answer("Введите описание услуги (или отправьте '-' для пропуска):")
        await state.update_data(step='description')
    
    elif step == 'description':
        description = message.text if message.text != '-' else None
        await state.update_data(description=description)
        await message.answer("Введите цену услуги (только число, например: 1500):")
        await state.update_data(step='price')
    
    elif step == 'price':
        try:
            price = float(message.text)
            await state.update_data(price=price)
            await message.answer("Введите длительность услуги в минутах (например: 60):")
            await state.update_data(step='duration')
        except ValueError:
            await message.answer("❌ Некорректная цена. Введите число:")
    
    elif step == 'duration':
        try:
            duration = int(message.text)
            service_data = await state.get_data()
            
            # Создаем услугу
            service = await ServiceService.create_service(
                name=service_data['name'],
                description=service_data.get('description'),
                price=service_data['price'],
                duration_minutes=duration
            )
            
            await message.answer(f"✅ Услуга '{service.name}' успешно добавлена!")
            await state.clear()
            
            # Возвращаемся к списку услуг
            await admin_services_callback(message, state)
        except ValueError:
            await message.answer("❌ Некорректная длительность. Введите число минут:")

async def admin_services_callback(message: Message, state: FSMContext):
    """Callback для возврата к списку услуг (для использования после создания)"""
    from handlers.admin_handlers import admin_services
    # Это будет обработано через callback, поэтому создадим отдельный handler

@router.callback_query(F.data.startswith("admin_service_"))
async def admin_service_detail(callback: CallbackQuery):
    """Детали услуги"""
    service_id = int(callback.data.split("_")[-1])
    service = await ServiceService.get_service(service_id)
    
    if not service:
        await callback.answer("Услуга не найдена", show_alert=True)
        return
    
    text = (
        f"📋 <b>Услуга: {service.name}</b>\n\n"
        f"Описание: {service.description or 'Не указано'}\n"
        f"Цена: {service.price:.0f} ₽\n"
        f"Длительность: {service.duration_minutes} минут\n"
        f"Тип: {'➕ Дополнительная' if service.is_additional else '📋 Основная'}\n"
        f"Статус: {'✅ Активна' if service.is_active else '❌ Неактивна'}\n"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="✅ Активировать" if not service.is_active else "❌ Деактивировать",
                callback_data=f"admin_toggle_service_{service_id}"
            )
        ],
        [
            InlineKeyboardButton(
                text="🔄 Сделать основной" if service.is_additional else "➕ Сделать дополнительной",
                callback_data=f"admin_toggle_additional_menu_{service_id}"
            )
        ],
        [InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"admin_edit_service_{service_id}")],
        [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"admin_delete_service_{service_id}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_services")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode='HTML')

@router.callback_query(F.data.startswith("admin_toggle_service_"))
async def admin_toggle_service(callback: CallbackQuery):
    """Активировать/деактивировать услугу"""
    service_id = int(callback.data.split("_")[-1])
    service = await ServiceService.get_service(service_id)
    
    if service:
        await ServiceService.update_service(service_id, is_active=not service.is_active)
        await callback.answer("Статус услуги изменен")
        await admin_service_detail(callback)
    else:
        await callback.answer("Услуга не найдена", show_alert=True)

@router.callback_query(F.data == "admin_schedule")
async def admin_schedule(callback: CallbackQuery):
    """Управление расписанием"""
    current_date = get_current_datetime_in_master_tz()
    
    text = (
        "📅 <b>Управление расписанием</b>\n\n"
        f"Текущая дата: {format_date(current_date)}\n\n"
        "Выберите действие:"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📆 Выбрать дату", callback_data="admin_schedule_select_date")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode='HTML')

@router.callback_query(F.data == "admin_schedule_select_date")
async def admin_schedule_select_date(callback: CallbackQuery):
    """Выбор даты для настройки расписания"""
    from handlers.client_handlers import _generate_calendar
    
    current_date = get_current_datetime_in_master_tz()
    keyboard = await _generate_calendar(current_date.year, current_date.month, admin_mode=True)
    
    await callback.message.edit_text(
        "📅 Выберите дату для настройки расписания:",
        reply_markup=keyboard
    )

@router.callback_query(F.data.startswith("admin_calendar_"))
async def admin_handle_calendar_navigation(callback: CallbackQuery):
    """Обработка навигации по календарю в админ-панели"""
    from handlers.client_handlers import _generate_calendar
    
    data = callback.data
    
    if data.startswith("admin_calendar_prev_"):
        _, _, _, year, month = data.split("_")
        year, month = int(year), int(month)
        if month == 1:
            month = 12
            year -= 1
        else:
            month -= 1
        keyboard = await _generate_calendar(year, month, admin_mode=True)
        await callback.message.edit_reply_markup(reply_markup=keyboard)
        
    elif data.startswith("admin_calendar_next_"):
        _, _, _, year, month = data.split("_")
        year, month = int(year), int(month)
        if month == 12:
            month = 1
            year += 1
        else:
            month += 1
        keyboard = await _generate_calendar(year, month, admin_mode=True)
        await callback.message.edit_reply_markup(reply_markup=keyboard)
    else:
        await callback.answer()

@router.callback_query(F.data.startswith("admin_schedule_date_"))
async def admin_schedule_set_date(callback: CallbackQuery, state: FSMContext):
    """Настройка расписания на дату"""
    # Парсим дату из callback_data
    date_str = callback.data.replace("admin_schedule_date_", "")
    schedule_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    
    # Проверяем текущее расписание
    schedule = await ScheduleService.get_schedule_for_date(schedule_date)
    
    if schedule and schedule.is_day_off:
        text = f"📅 <b>Дата: {format_date(datetime.combine(schedule_date, time.min))}</b>\n\nЭтот день помечен как выходной."
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Сделать рабочим", callback_data=f"admin_schedule_work_{date_str}")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_schedule")]
        ])
    else:
        start_time = schedule.start_time.strftime("%H:%M") if schedule and schedule.start_time else "09:00"
        end_time = schedule.end_time.strftime("%H:%M") if schedule and schedule.end_time else "18:00"
        
        text = (
            f"📅 <b>Настройка расписания на {format_date(datetime.combine(schedule_date, time.min))}</b>\n\n"
            f"Текущее время: {start_time} - {end_time}\n\n"
            "Введите рабочие часы в формате ЧЧ:ММ-ЧЧ:ММ (например, 09:00-18:00)\n"
            "или нажмите кнопку, чтобы сделать день выходным:"
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🚫 Сделать выходным", callback_data=f"admin_schedule_off_{date_str}")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_schedule")]
        ])
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode='HTML')
    await state.set_state(AdminStates.setting_schedule)
    await state.update_data(schedule_date=date_str)

@router.message(StateFilter(AdminStates.setting_schedule))
async def admin_schedule_process(message: Message, state: FSMContext):
    """Обработка ввода расписания"""
    data = await state.get_data()
    date_str = data.get('schedule_date')
    
    if not date_str:
        await message.answer("Ошибка: дата не выбрана")
        return
    
    schedule_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    
    # Парсим время в формате ЧЧ:ММ-ЧЧ:ММ
    try:
        time_str = message.text.strip()
        start_str, end_str = time_str.split('-')
        start_time_obj = datetime.strptime(start_str.strip(), "%H:%M").time()
        end_time_obj = datetime.strptime(end_str.strip(), "%H:%M").time()
        
        await ScheduleService.set_working_hours(schedule_date, start_time_obj, end_time_obj)
        await message.answer(f"✅ Расписание на {format_date(datetime.combine(schedule_date, time.min))} установлено: {time_str}")
        await state.clear()
    except ValueError:
        await message.answer("❌ Некорректный формат. Введите время в формате ЧЧ:ММ-ЧЧ:ММ (например, 09:00-18:00):")

@router.callback_query(F.data.startswith("admin_schedule_off_"))
async def admin_schedule_set_off(callback: CallbackQuery):
    """Установить день как выходной"""
    date_str = callback.data.replace("admin_schedule_off_", "")
    schedule_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    
    await ScheduleService.set_day_off(schedule_date)
    await callback.answer("День помечен как выходной")
    
    text = f"✅ Дата {format_date(datetime.combine(schedule_date, time.min))} помечена как выходной"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_schedule")]
    ])
    await callback.message.edit_text(text, reply_markup=keyboard)

@router.callback_query(F.data.startswith("admin_schedule_work_"))
async def admin_schedule_set_work(callback: CallbackQuery, state: FSMContext):
    """Сделать день рабочим"""
    date_str = callback.data.replace("admin_schedule_work_", "")
    schedule_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    
    await state.update_data(schedule_date=date_str)
    await callback.message.edit_text(
        f"Введите рабочие часы для {format_date(datetime.combine(schedule_date, time.min))} в формате ЧЧ:ММ-ЧЧ:ММ (например, 09:00-18:00):"
    )
    await state.set_state(AdminStates.setting_schedule)

@router.callback_query(F.data.startswith("admin_confirm_"))
async def admin_confirm_appointment(callback: CallbackQuery):
    """Подтвердить запись от мастера"""
    appointment_id = int(callback.data.split("_")[-1])
    
    await AppointmentService.update_appointment(appointment_id, status='confirmed')
    
    appointment = await AppointmentService.get_appointment(appointment_id)
    if appointment:
        client_user = await db.fetchrow("SELECT telegram_id FROM users WHERE id = $1", appointment.client_id)
        if client_user:
            try:
                await callback.bot.send_message(
                    client_user['telegram_id'],
                    f"✅ Ваша запись на {format_datetime(appointment.appointment_date)} подтверждена мастером!"
                )
            except:
                pass
    
    await callback.answer("Запись подтверждена")
    await callback.message.edit_text(callback.message.text + "\n\n✅ Запись подтверждена")

@router.callback_query(F.data.startswith("admin_reject_"))
async def admin_reject_appointment(callback: CallbackQuery):
    """Отклонить запись от мастера"""
    appointment_id = int(callback.data.split("_")[-1])
    
    await AppointmentService.cancel_appointment(appointment_id, reason="Отклонено мастером")
    
    appointment = await AppointmentService.get_appointment(appointment_id)
    if appointment:
        client_user = await db.fetchrow("SELECT telegram_id FROM users WHERE id = $1", appointment.client_id)
        if client_user:
            try:
                await callback.bot.send_message(
                    client_user['telegram_id'],
                    f"❌ Ваша запись на {format_datetime(appointment.appointment_date)} была отклонена мастером. Пожалуйста, выберите другое время."
                )
            except:
                pass
    
    await callback.answer("Запись отклонена")
    await callback.message.edit_text(callback.message.text + "\n\n❌ Запись отклонена")

@router.callback_query(F.data == "admin_settings")
async def admin_settings(callback: CallbackQuery):
    """Настройки бота"""
    settings = await BotSettingsService.get_appointment_settings()
    
    confirmation_text = "✅ Требуется подтверждение" if settings['require_confirmation'] else "❌ Только уведомление"
    
    text = (
        "⚙️ <b>Настройки бота</b>\n\n"
        f"Подтверждение записей: {confirmation_text}\n"
        f"Напоминания за 24ч: {'✅ Включены' if settings['reminder_24h_enabled'] else '❌ Выключены'}\n"
        f"Напоминания за 1-2ч: {'✅ Включены' if settings['reminder_1_2h_enabled'] else '❌ Выключены'}\n"
        f"Интервал повторных напоминаний: {settings['reminder_interval_hours']} часов\n"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🔔 " + ("Выключить подтверждение" if settings['require_confirmation'] else "Включить подтверждение"),
            callback_data="admin_toggle_confirmation"
        )],
        [InlineKeyboardButton(
            text="⏰ " + ("Выключить напоминание за 24ч" if settings['reminder_24h_enabled'] else "Включить напоминание за 24ч"),
            callback_data="admin_toggle_reminder_24h"
        )],
        [InlineKeyboardButton(
            text="⏰ " + ("Выключить напоминание за 1-2ч" if settings['reminder_1_2h_enabled'] else "Включить напоминание за 1-2ч"),
            callback_data="admin_toggle_reminder_1_2h"
        )],
        [InlineKeyboardButton(
            text=f"🔄 Изменить интервал напоминаний ({settings['reminder_interval_hours']} ч)",
            callback_data="admin_set_reminder_interval"
        )],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode='HTML')

@router.callback_query(F.data == "admin_toggle_confirmation")
async def admin_toggle_confirmation(callback: CallbackQuery):
    """Переключить требование подтверждения"""
    settings = await BotSettingsService.get_appointment_settings()
    new_value = not settings['require_confirmation']
    
    await BotSettingsService.update_appointment_settings(require_confirmation=new_value)
    await callback.answer("Настройка изменена")
    await admin_settings(callback)

@router.callback_query(F.data == "admin_toggle_reminder_24h")
async def admin_toggle_reminder_24h(callback: CallbackQuery):
    """Переключить напоминание за 24 часа"""
    settings = await BotSettingsService.get_appointment_settings()
    new_value = not settings['reminder_24h_enabled']
    
    await BotSettingsService.update_appointment_settings(reminder_24h_enabled=new_value)
    await callback.answer("Настройка изменена")
    await admin_settings(callback)

@router.callback_query(F.data == "admin_toggle_reminder_1_2h")
async def admin_toggle_reminder_1_2h(callback: CallbackQuery):
    """Переключить напоминание за 1-2 часа"""
    settings = await BotSettingsService.get_appointment_settings()
    new_value = not settings['reminder_1_2h_enabled']
    
    await BotSettingsService.update_appointment_settings(reminder_1_2h_enabled=new_value)
    await callback.answer("Настройка изменена")
    await admin_settings(callback)

@router.callback_query(F.data == "admin_set_reminder_interval")
async def admin_set_reminder_interval_start(callback: CallbackQuery, state: FSMContext):
    """Начало установки интервала напоминаний"""
    await callback.message.edit_text(
        "🔄 <b>Установка интервала повторных напоминаний</b>\n\n"
        "Введите интервал в часах (например: 2):",
        parse_mode='HTML'
    )
    await state.set_state(AdminStates.setting_reminder_interval)

@router.message(StateFilter(AdminStates.setting_reminder_interval))
async def admin_set_reminder_interval_process(message: Message, state: FSMContext):
    """Обработка установки интервала напоминаний"""
    try:
        interval = int(message.text.strip())
        if interval < 1:
            await message.answer("❌ Интервал должен быть не менее 1 часа. Введите число:")
            return
        
        await BotSettingsService.update_appointment_settings(reminder_interval_hours=interval)
        await message.answer(f"✅ Интервал напоминаний установлен: {interval} часов")
        await state.clear()
    except ValueError:
        await message.answer("❌ Некорректное значение. Введите число (например: 2):")

@router.callback_query(F.data == "admin_back")
async def admin_back(callback: CallbackQuery, state: FSMContext):
    """Вернуться в админ-панель"""
    if not await UserService.is_admin(callback.from_user.id):
        await callback.answer("❌ У вас нет доступа", show_alert=True)
        return
    
    await state.clear()
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Управление услугами", callback_data="admin_services")],
        [InlineKeyboardButton(text="📅 Управление расписанием", callback_data="admin_schedule")],
        [InlineKeyboardButton(text="👥 Управление клиентами", callback_data="admin_clients")],
        [InlineKeyboardButton(text="📊 История записей", callback_data="admin_history")],
        [InlineKeyboardButton(text="⚙️ Настройки бота", callback_data="admin_settings")],
        [InlineKeyboardButton(text="ℹ️ Управление информацией", callback_data="admin_info")],
        [InlineKeyboardButton(text="📢 Рассылка клиентам", callback_data="admin_broadcast")]
    ])
    
    await callback.message.edit_text("⚙️ <b>Админ-панель</b>", reply_markup=keyboard, parse_mode='HTML')

# ========== ДОБАВЛЕННЫЕ ОБРАБОТЧИКИ ==========

@router.callback_query(F.data == "admin_clients")
async def admin_clients(callback: CallbackQuery):
    """Управление клиентами"""
    clients = await db.fetch("""
        SELECT u.id, u.telegram_id, u.full_name, u.username, c.id as client_id
        FROM users u
        LEFT JOIN clients c ON u.id = c.user_id
        WHERE u.is_admin = FALSE
        ORDER BY u.created_at DESC
        LIMIT 50
    """)
    
    if not clients:
        await callback.message.edit_text("👥 Клиентов пока нет", parse_mode='HTML')
        return
    
    text = "👥 <b>Управление клиентами</b>\n\n"
    keyboard_buttons = []
    
    for client in clients:
        name = client['full_name'] or client['username'] or f"ID: {client['telegram_id']}"
        client_id = client['client_id'] or client['id']
        keyboard_buttons.append([
            InlineKeyboardButton(
                text=name[:40],
                callback_data=f"admin_client_{client_id}"
            )
        ])
    
    keyboard_buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode='HTML')

async def _show_history_page(callback: CallbackQuery, page: int = 0, page_size: int = 10):
    """Показать страницу истории записей"""
    offset = page * page_size
    
    appointments = await db.fetch("""
        SELECT a.*, u.full_name, u.username, s.name as service_name
        FROM appointments a
        JOIN users u ON a.client_id = u.id
        JOIN services s ON a.service_id = s.id
        ORDER BY a.appointment_date DESC
        LIMIT $1 OFFSET $2
    """, page_size, offset)
    
    total_count = await db.fetchval("""
        SELECT COUNT(*) FROM appointments
    """)
    
    total_pages = (total_count + page_size - 1) // page_size if total_count > 0 else 1
    
    if not appointments and page == 0:
        await callback.message.edit_text("📊 Записей пока нет", parse_mode='HTML')
        return
    
    text = f"📊 <b>История записей</b> (стр. {page + 1}/{total_pages})\n\n"
    status_emoji = {
        'pending': '⏳', 
        'confirmed': '✅', 
        'cancelled': '❌', 
        'completed': '✓',
        'no_show': '🚫',
        'moved': '🔄'
    }
    
    for apt in appointments:
        client_name = apt['full_name'] or apt['username'] or 'Без имени'
        emoji = status_emoji.get(apt['status'], '❓')
        text += f"{emoji} <b>{client_name}</b> - {apt['service_name']}\n"
        text += f"   {format_datetime(apt['appointment_date'])}\n"
        text += f"   {float(apt['total_price']):.0f} ₽\n"
        text += f"   ID: {apt['id']}\n\n"
    
    keyboard_buttons = []
    
    # Кнопки для редактирования записей (первые 5)
    for apt in appointments[:5]:
        keyboard_buttons.append([
            InlineKeyboardButton(
                text=f"✏️ Редактировать запись #{apt['id']}",
                callback_data=f"admin_edit_appointment_{apt['id']}"
            )
        ])
    
    # Кнопки навигации
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"admin_history_page_{page - 1}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton(text="➡️ Вперед", callback_data=f"admin_history_page_{page + 1}"))
    if nav_buttons:
        keyboard_buttons.append(nav_buttons)
    
    keyboard_buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode='HTML')

@router.callback_query(F.data == "admin_history")
async def admin_history(callback: CallbackQuery, state: FSMContext):
    """История записей"""
    await state.update_data(history_page=0)
    await _show_history_page(callback, 0)

@router.callback_query(F.data.startswith("admin_history_page_"))
async def admin_history_page(callback: CallbackQuery):
    """Переход по страницам истории"""
    page = int(callback.data.split("_")[-1])
    await _show_history_page(callback, page)

@router.callback_query(F.data == "admin_info")
async def admin_info(callback: CallbackQuery):
    """Управление информацией"""
    sections = await InfoService.get_all_info_sections()
    
    text = "ℹ️ <b>Управление информацией</b>\n\n"
    keyboard_buttons = []
    
    for section in sections:
        has_content = "✅" if section.get('content') else "❌"
        keyboard_buttons.append([
            InlineKeyboardButton(
                text=f"{section['title']} {has_content}",
                callback_data=f"admin_edit_info_{section['key']}"
            )
        ])
    
    # Показываем FAQ
    faq_list = await InfoService.get_faq()
    if faq_list:
        text += "\n<b>FAQ:</b>\n"
        for faq in faq_list:
            status = "✅" if faq.get('is_active', True) else "❌"
            text += f"{status} {faq['question'][:30]}...\n"
            keyboard_buttons.append([
                InlineKeyboardButton(
                    text=f"{status} FAQ: {faq['question'][:30]}",
                    callback_data=f"admin_edit_faq_{faq['id']}"
                )
            ])
    
    keyboard_buttons.append([
        InlineKeyboardButton(text="➕ Добавить FAQ", callback_data="admin_add_faq")
    ])
    keyboard_buttons.append([
        InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")
    ])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode='HTML')

@router.callback_query(F.data.startswith("admin_edit_info_"))
async def admin_edit_info(callback: CallbackQuery, state: FSMContext):
    """Редактирование информационного раздела"""
    section_key = callback.data.replace("admin_edit_info_", "")
    section = await InfoService.get_info_section(section_key)
    
    if not section:
        await callback.answer("Раздел не найден", show_alert=True)
        return
    
    text = (
        f"✏️ <b>Редактирование: {section['title']}</b>\n\n"
        f"Текущий текст:\n{section.get('content', 'Пусто')}\n\n"
        f"Введите новый текст (или '-' для очистки):"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_info")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode='HTML')
    await state.set_state(AdminStates.editing_info)
    await state.update_data(section_key=section_key)

@router.message(StateFilter(AdminStates.editing_info))
async def admin_info_process(message: Message, state: FSMContext):
    """Обработка ввода информации"""
    data = await state.get_data()
    section_key = data.get('section_key')
    
    if not section_key:
        await message.answer("Ошибка: раздел не выбран")
        return
    
    content = message.text if message.text != '-' else ''
    await InfoService.update_info_section(section_key, content)
    await message.answer("✅ Информация обновлена!")
    await state.clear()

@router.callback_query(F.data == "admin_add_faq")
async def admin_add_faq_start(callback: CallbackQuery, state: FSMContext):
    """Начало добавления FAQ"""
    await callback.message.edit_text(
        "➕ <b>Добавление FAQ</b>\n\nВведите вопрос:",
        parse_mode='HTML'
    )
    await state.set_state(AdminStates.adding_faq_question)

@router.message(StateFilter(AdminStates.adding_faq_question))
async def admin_add_faq_question(message: Message, state: FSMContext):
    """Обработка вопроса FAQ"""
    question = message.text.strip()
    if not question:
        await message.answer("❌ Вопрос не может быть пустым. Введите вопрос:")
        return
    
    await state.update_data(faq_question=question)
    await message.answer("Теперь введите ответ:")
    await state.set_state(AdminStates.adding_faq_answer)

@router.message(StateFilter(AdminStates.adding_faq_answer))
async def admin_add_faq_answer(message: Message, state: FSMContext):
    """Обработка ответа FAQ"""
    data = await state.get_data()
    question = data.get('faq_question')
    answer = message.text.strip()
    
    if not answer:
        await message.answer("❌ Ответ не может быть пустым. Введите ответ:")
        return
    
    await InfoService.add_faq(question, answer)
    await message.answer("✅ FAQ добавлен!")
    await state.clear()

@router.callback_query(F.data.startswith("admin_edit_faq_"))
async def admin_edit_faq(callback: CallbackQuery):
    """Редактирование FAQ"""
    faq_id = int(callback.data.split("_")[-1])
    faq = await db.fetchrow("SELECT * FROM faq WHERE id = $1", faq_id)
    
    if not faq:
        await callback.answer("FAQ не найден", show_alert=True)
        return
    
    text = (
        f"✏️ <b>FAQ #{faq_id}</b>\n\n"
        f"<b>Вопрос:</b> {faq['question']}\n\n"
        f"<b>Ответ:</b> {faq['answer']}\n\n"
        f"Статус: {'✅ Активен' if faq['is_active'] else '❌ Неактивен'}"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="❌ Деактивировать" if faq['is_active'] else "✅ Активировать",
            callback_data=f"admin_toggle_faq_{faq_id}"
        )],
        [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"admin_delete_faq_{faq_id}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_info")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode='HTML')

@router.callback_query(F.data.startswith("admin_toggle_faq_"))
async def admin_toggle_faq(callback: CallbackQuery):
    """Переключить активность FAQ"""
    faq_id = int(callback.data.split("_")[-1])
    faq = await db.fetchrow("SELECT is_active FROM faq WHERE id = $1", faq_id)
    
    if faq:
        new_status = not faq['is_active']
        await db.execute("UPDATE faq SET is_active = $1 WHERE id = $2", new_status, faq_id)
        await callback.answer("Статус FAQ изменен")
        await admin_edit_faq(callback)

@router.callback_query(F.data.startswith("admin_delete_faq_"))
async def admin_delete_faq(callback: CallbackQuery):
    """Удалить FAQ"""
    faq_id = int(callback.data.split("_")[-1])
    await db.execute("DELETE FROM faq WHERE id = $1", faq_id)
    await callback.answer("FAQ удален")
    await admin_info(callback)

@router.callback_query(F.data == "admin_broadcast")
async def admin_broadcast_start(callback: CallbackQuery, state: FSMContext):
    """Начало рассылки - выбор типа рассылки"""
    text = (
        "📢 <b>Рассылка клиентам</b>\n\n"
        "Выберите тип рассылки:"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌐 Всем клиентам", callback_data="admin_broadcast_all")],
        [InlineKeyboardButton(text="👥 Определенным клиентам", callback_data="admin_broadcast_selected")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")]
    ])
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode='HTML')

@router.callback_query(F.data == "admin_broadcast_all")
async def admin_broadcast_all_start(callback: CallbackQuery, state: FSMContext):
    """Начало рассылки всем клиентам"""
    text = "📢 <b>Рассылка всем клиентам</b>\n\nВведите сообщение для рассылки:"
    await callback.message.edit_text(text, parse_mode='HTML')
    await state.update_data(broadcast_type='all')
    await state.set_state(AdminStates.broadcast_message)

@router.callback_query(F.data == "admin_broadcast_selected")
async def admin_broadcast_selected_start(callback: CallbackQuery, state: FSMContext):
    """Выбор клиентов для рассылки"""
    clients = await db.fetch("""
        SELECT u.id, u.telegram_id, u.full_name, u.username, c.id as client_id
        FROM users u
        LEFT JOIN clients c ON u.id = c.user_id
        WHERE u.is_admin = FALSE
        ORDER BY u.created_at DESC
        LIMIT 100
    """)
    
    if not clients:
        await callback.answer("Клиентов не найдено", show_alert=True)
        return
    
    text = "👥 <b>Выберите клиентов для рассылки</b>\n\nВы можете выбрать несколько клиентов:"
    keyboard_buttons = []
    
    for client in clients:
        name = client['full_name'] or client['username'] or f"ID: {client['telegram_id']}"
        client_id = client['client_id'] or client['id']
        user_id = client['id']
        
        # Формируем ссылку на клиента
        client_link = ""
        if client.get('username'):
            client_link = f"@{client['username']}"
        elif client.get('telegram_id'):
            client_link = f"tg://user?id={client['telegram_id']}"
        
        button_text = name[:30]
        if client_link:
            button_text += f" [{client_link}]"
        
        keyboard_buttons.append([
            InlineKeyboardButton(
                text=button_text[:60],
                callback_data=f"admin_broadcast_select_client_{user_id}"
            )
        ])
    
    keyboard_buttons.append([
        InlineKeyboardButton(text="✅ Завершить выбор", callback_data="admin_broadcast_finish_selection")
    ])
    keyboard_buttons.append([
        InlineKeyboardButton(text="🔙 Назад", callback_data="admin_broadcast")
    ])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode='HTML')
    await state.update_data(broadcast_type='selected', selected_clients=[])
    await state.set_state(AdminStates.selecting_broadcast_clients)

@router.callback_query(F.data.startswith("admin_broadcast_select_client_"), StateFilter(AdminStates.selecting_broadcast_clients))
async def admin_broadcast_select_client(callback: CallbackQuery, state: FSMContext):
    """Добавление/удаление клиента из списка рассылки"""
    user_id = int(callback.data.split("_")[-1])
    data = await state.get_data()
    selected_clients = data.get('selected_clients', [])
    
    if user_id in selected_clients:
        selected_clients.remove(user_id)
        await callback.answer("❌ Клиент удален из списка")
    else:
        selected_clients.append(user_id)
        await callback.answer("✅ Клиент добавлен в список")
    
    await state.update_data(selected_clients=selected_clients)
    
    # Обновляем интерфейс
    clients = await db.fetch("""
        SELECT u.id, u.telegram_id, u.full_name, u.username, c.id as client_id
        FROM users u
        LEFT JOIN clients c ON u.id = c.user_id
        WHERE u.is_admin = FALSE
        ORDER BY u.created_at DESC
        LIMIT 100
    """)
    
    text = f"👥 <b>Выберите клиентов для рассылки</b>\n\nВыбрано: {len(selected_clients)} клиент(ов)\n\nВы можете выбрать несколько клиентов:"
    keyboard_buttons = []
    
    for client in clients:
        name = client['full_name'] or client['username'] or f"ID: {client['telegram_id']}"
        client_id = client['client_id'] or client['id']
        user_id_check = client['id']
        
        # Формируем ссылку на клиента
        client_link = ""
        if client.get('username'):
            client_link = f"@{client['username']}"
        elif client.get('telegram_id'):
            client_link = f"tg://user?id={client['telegram_id']}"
        
        is_selected = "✅ " if user_id_check in selected_clients else ""
        button_text = f"{is_selected}{name[:25]}"
        if client_link:
            button_text += f" [{client_link}]"
        
        keyboard_buttons.append([
            InlineKeyboardButton(
                text=button_text[:60],
                callback_data=f"admin_broadcast_select_client_{user_id_check}"
            )
        ])
    
    keyboard_buttons.append([
        InlineKeyboardButton(text="✅ Завершить выбор", callback_data="admin_broadcast_finish_selection")
    ])
    keyboard_buttons.append([
        InlineKeyboardButton(text="🔙 Назад", callback_data="admin_broadcast")
    ])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode='HTML')

@router.callback_query(F.data == "admin_broadcast_finish_selection", StateFilter(AdminStates.selecting_broadcast_clients))
async def admin_broadcast_finish_selection(callback: CallbackQuery, state: FSMContext):
    """Завершение выбора клиентов и переход к вводу сообщения"""
    data = await state.get_data()
    selected_clients = data.get('selected_clients', [])
    
    if not selected_clients:
        await callback.answer("❌ Выберите хотя бы одного клиента", show_alert=True)
        return
    
    text = f"📢 <b>Рассылка {len(selected_clients)} клиентам</b>\n\nВведите сообщение для рассылки:"
    await callback.message.edit_text(text, parse_mode='HTML')
    await state.set_state(AdminStates.broadcast_message)

@router.message(StateFilter(AdminStates.broadcast_message))
async def admin_broadcast_send(message: Message, state: FSMContext, bot: Bot):
    """Отправка рассылки"""
    data = await state.get_data()
    broadcast_type = data.get('broadcast_type', 'all')
    
    if broadcast_type == 'all':
        users = await db.fetch("""
            SELECT telegram_id FROM users
            WHERE is_admin = FALSE AND telegram_id IS NOT NULL
        """)
        user_ids = [user['telegram_id'] for user in users]
    else:
        # Рассылка выбранным клиентам
        selected_clients = data.get('selected_clients', [])
        if not selected_clients:
            await message.answer("❌ Не выбраны клиенты для рассылки")
            await state.clear()
            return
        
        users = await db.fetch("""
            SELECT telegram_id FROM users
            WHERE id = ANY($1::int[]) AND telegram_id IS NOT NULL
        """, selected_clients)
        user_ids = [user['telegram_id'] for user in users]
    
    sent = 0
    failed = 0
    await message.answer(f"📤 Начинаю рассылку {len(user_ids)} клиентам...")
    
    for telegram_id in user_ids:
        try:
            await bot.send_message(telegram_id, message.text)
            sent += 1
        except:
            failed += 1
    
    await message.answer(f"✅ Рассылка завершена!\nОтправлено: {sent}\nОшибок: {failed}")
    await state.clear()

async def _show_client_detail(client_id: int, message_or_edit):
    """Вспомогательная функция для отображения деталей клиента"""
    client = await db.fetchrow("""
        SELECT c.*, u.telegram_id, u.full_name, u.username, u.id as user_id
        FROM clients c
        JOIN users u ON c.user_id = u.id
        WHERE c.id = $1
    """, client_id)
    
    user_id = None
    telegram_id = None
    
    if not client:
        # Попробуем найти по user_id (если передан user_id вместо client_id)
        client = await db.fetchrow("""
            SELECT u.*, u.id as user_id, NULL as phone, NULL as notes, u.telegram_id, u.full_name, u.username
            FROM users u
            WHERE u.id = $1 AND u.is_admin = FALSE
        """, client_id)
        if not client:
            if hasattr(message_or_edit, 'answer'):
                await message_or_edit.answer("Клиент не найден")
            return
        user_id = client['id']
        telegram_id = client['telegram_id']
        # Создаем запись в clients если её нет
        existing_client = await db.fetchrow("SELECT id FROM clients WHERE user_id = $1", user_id)
        if not existing_client:
            new_client_id = await db.fetchval("""
                INSERT INTO clients (user_id) VALUES ($1) RETURNING id
            """, user_id)
            client_id = new_client_id
        else:
            client_id = existing_client['id']
    else:
        user_id = client.get('user_id') or client['id']
        telegram_id = client.get('telegram_id')
    
    # Проверяем черный список
    is_blacklisted = await UserService.is_blacklisted(telegram_id) if telegram_id else False
    
    appointments = await db.fetch("""
        SELECT * FROM appointments WHERE client_id = $1 ORDER BY appointment_date DESC LIMIT 10
    """, user_id)
    
    # Генерируем ссылки на клиента
    client_links = []
    if client.get('username'):
        client_links.append(f"@{client['username']}")
    if telegram_id:
        client_links.append(f"tg://user?id={telegram_id}")
    
    name = client.get('full_name') or client.get('username') or 'Без имени'
    text = f"👤 <b>Клиент: {name}</b>\n\n"
    if client_links:
        text += f"Ссылки: {', '.join(client_links)}\n"
    else:
        text += "Ссылка: Нет ссылки\n"
    text += f"Telegram ID: {telegram_id}\n"
    text += f"Телефон: {client.get('phone') or 'Не указан'}\n"
    text += f"Записей: {len(appointments)}\n"
    text += f"Черный список: {'✅ Да' if is_blacklisted else '❌ Нет'}\n\n"
    
    # Получаем все заметки клиента
    notes = await db.fetch("""
        SELECT note, created_at FROM client_notes WHERE client_id = $1 ORDER BY created_at DESC LIMIT 5
    """, client_id)
    
    if notes:
        text += "Последние заметки:\n"
        for note in notes:
            text += f"  • {note['note']}\n"
        text += "\n"
    elif client.get('notes'):
        text += f"Заметки: {client['notes']}\n\n"
    
    keyboard_buttons = []
    if is_blacklisted:
        keyboard_buttons.append([
            InlineKeyboardButton(text="✅ Убрать из черного списка", callback_data=f"admin_unblacklist_{user_id}")
        ])
    else:
        keyboard_buttons.append([
            InlineKeyboardButton(text="📝 Добавить заметку", callback_data=f"admin_add_note_{client_id}"),
        ])
        keyboard_buttons.append([
            InlineKeyboardButton(text="🚫 В черный список", callback_data=f"admin_blacklist_{client_id}")
        ])
    keyboard_buttons.append([
        InlineKeyboardButton(text="📋 История визитов", callback_data=f"admin_client_history_{client_id}_0")
    ])
    keyboard_buttons.append([
        InlineKeyboardButton(text="🗑 Удалить клиента", callback_data=f"admin_delete_client_{client_id}")
    ])
    keyboard_buttons.append([
        InlineKeyboardButton(text="🔙 Назад", callback_data="admin_clients")
    ])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    await message_or_edit.edit_text(text, reply_markup=keyboard, parse_mode='HTML')

@router.callback_query(F.data.startswith("admin_client_"))
async def admin_client_detail(callback: CallbackQuery):
    """Детали клиента"""
    client_id = int(callback.data.split("_")[-1])
    await _show_client_detail(client_id, callback.message)

@router.callback_query(F.data.startswith("admin_toggle_additional_menu_"))
async def admin_toggle_additional_menu(callback: CallbackQuery):
    """Меню выбора типа дополнительной услуги"""
    service_id = int(callback.data.split("_")[-1])
    service = await ServiceService.get_service(service_id)
    
    if not service:
        await callback.answer("Услуга не найдена", show_alert=True)
        return
    
    text = (
        f"➕ <b>Настройка дополнительной услуги</b>\n\n"
        f"Услуга: {service.name}\n\n"
        f"Выберите, для каких услуг эта услуга будет доступна как дополнительная:"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌐 Для всех основных услуг", callback_data=f"admin_set_additional_all_{service_id}")],
        [InlineKeyboardButton(text="🎯 Для конкретной услуги", callback_data=f"admin_set_additional_specific_{service_id}")],
        [InlineKeyboardButton(text="📋 Сделать основной услугой", callback_data=f"admin_set_main_service_{service_id}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data=f"admin_service_{service_id}")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode='HTML')

@router.callback_query(F.data.startswith("admin_set_additional_all_"))
async def admin_set_additional_all(callback: CallbackQuery):
    """Сделать услугу дополнительной для всех основных услуг"""
    service_id = int(callback.data.split("_")[-1])
    
    # Делаем услугу дополнительной
    await ServiceService.update_service(service_id, is_additional=True)
    
    # Удаляем все существующие связи
    await db.execute("DELETE FROM services_additional_links WHERE additional_service_id = $1", service_id)
    
    # Создаем связь для всех (main_service_id = NULL)
    await db.execute("""
        INSERT INTO services_additional_links (additional_service_id, main_service_id)
        VALUES ($1, NULL)
        ON CONFLICT DO NOTHING
    """, service_id)
    
    await callback.answer("✅ Услуга доступна как дополнительная для всех основных услуг")
    await admin_service_detail(callback)

@router.callback_query(F.data.startswith("admin_set_additional_specific_"))
async def admin_set_additional_specific(callback: CallbackQuery, state: FSMContext):
    """Начало настройки дополнительной услуги для конкретной услуги"""
    service_id = int(callback.data.split("_")[-1])
    
    # Делаем услугу дополнительной
    await ServiceService.update_service(service_id, is_additional=True)
    
    # Получаем все основные услуги
    main_services = await ServiceService.get_all_services(only_active=False, only_main=True)
    
    text = "🎯 <b>Выберите основную услугу</b>\n\nДля какой основной услуги будет доступна эта дополнительная:"
    
    keyboard_buttons = []
    for main_service in main_services:
        keyboard_buttons.append([
            InlineKeyboardButton(
                text=f"{main_service.name}",
                callback_data=f"admin_link_additional_{service_id}_{main_service.id}"
            )
        ])
    
    keyboard_buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data=f"admin_service_{service_id}")])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode='HTML')

@router.callback_query(F.data.startswith("admin_link_additional_"))
async def admin_link_additional(callback: CallbackQuery):
    """Связать дополнительную услугу с основной"""
    parts = callback.data.split("_")
    additional_service_id = int(parts[-2])
    main_service_id = int(parts[-1])
    
    # Создаем связь
    await db.execute("""
        INSERT INTO services_additional_links (additional_service_id, main_service_id)
        VALUES ($1, $2)
        ON CONFLICT (additional_service_id, main_service_id) DO NOTHING
    """, additional_service_id, main_service_id)
    
    await callback.answer("✅ Связь создана")
    await admin_service_detail(callback)

@router.callback_query(F.data.startswith("admin_set_main_service_"))
async def admin_set_main_service(callback: CallbackQuery):
    """Сделать услугу основной"""
    service_id = int(callback.data.split("_")[-1])
    
    # Делаем услугу основной
    await ServiceService.update_service(service_id, is_additional=False)
    
    # Удаляем все связи
    await db.execute("DELETE FROM services_additional_links WHERE additional_service_id = $1", service_id)
    
    await callback.answer("✅ Услуга сделана основной")
    await admin_service_detail(callback)

@router.callback_query(F.data.startswith("admin_toggle_additional_"))
async def admin_toggle_additional(callback: CallbackQuery):
    """Переключить тип услуги (основная/дополнительная)"""
    service_id = int(callback.data.split("_")[-1])
    service = await ServiceService.get_service(service_id)
    
    if service:
        await ServiceService.update_service(service_id, is_additional=not service.is_additional)
        await callback.answer("Тип услуги изменен")
        
        # Обновляем информацию об услуге
        service = await ServiceService.get_service(service_id)
        text = (
            f"📋 <b>Услуга: {service.name}</b>\n\n"
            f"Описание: {service.description or 'Не указано'}\n"
            f"Цена: {service.price:.0f} ₽\n"
            f"Длительность: {service.duration_minutes} минут\n"
            f"Тип: {'➕ Дополнительная' if service.is_additional else '📋 Основная'}\n"
            f"Статус: {'✅ Активна' if service.is_active else '❌ Неактивна'}\n"
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Активировать" if not service.is_active else "❌ Деактивировать",
                    callback_data=f"admin_toggle_service_{service_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔄 Сделать основной" if service.is_additional else "➕ Сделать дополнительной",
                    callback_data=f"admin_toggle_additional_{service_id}"
                )
            ],
            [InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"admin_edit_service_{service_id}")],
            [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"admin_delete_service_{service_id}")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_services")]
        ])
        
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode='HTML')
    else:
        await callback.answer("Услуга не найдена", show_alert=True)

@router.callback_query(F.data.startswith("admin_edit_service_"))
async def admin_edit_service_start(callback: CallbackQuery, state: FSMContext):
    """Начало редактирования услуги"""
    service_id = int(callback.data.split("_")[-1])
    service = await ServiceService.get_service(service_id)
    
    if not service:
        await callback.answer("Услуга не найдена", show_alert=True)
        return
    
    await state.update_data(service_id=service_id, edit_step='name')
    await callback.message.edit_text(
        f"✏️ <b>Редактирование услуги: {service.name}</b>\n\n"
        f"Введите новое название (или отправьте '-' чтобы оставить текущее '{service.name}'):",
        parse_mode='HTML'
    )
    await state.set_state(AdminStates.editing_service)

@router.message(StateFilter(AdminStates.editing_service))
async def admin_edit_service_process(message: Message, state: FSMContext):
    """Процесс редактирования услуги"""
    data = await state.get_data()
    service_id = data.get('service_id')
    edit_step = data.get('edit_step')
    
    if not service_id:
        await message.answer("Ошибка: услуга не выбрана")
        await state.clear()
        return
    
    service = await ServiceService.get_service(service_id)
    if not service:
        await message.answer("Услуга не найдена")
        await state.clear()
        return
    
    if edit_step == 'name':
        new_name = message.text if message.text != '-' else service.name
        await state.update_data(name=new_name, edit_step='price')
        await message.answer(f"Введите новую цену (или '-' чтобы оставить {service.price:.0f} ₽):")
    
    elif edit_step == 'price':
        if message.text != '-':
            try:
                new_price = float(message.text)
                await state.update_data(price=new_price)
            except ValueError:
                await message.answer("❌ Некорректная цена. Введите число или '-' для пропуска:")
                return
        await state.update_data(edit_step='duration')
        await message.answer(f"Введите новую длительность в минутах (или '-' чтобы оставить {service.duration_minutes}):")
    
    elif edit_step == 'duration':
        updates = {}
        name = data.get('name')
        price = data.get('price')
        
        if name:
            updates['name'] = name
        if price is not None:
            updates['price'] = price
        if message.text != '-':
            try:
                updates['duration_minutes'] = int(message.text)
            except ValueError:
                await message.answer("❌ Некорректная длительность. Введите число или '-' для пропуска:")
                return
        
        if updates:
            await ServiceService.update_service(service_id, **updates)
            await message.answer("✅ Услуга обновлена!")
        else:
            await message.answer("Ничего не изменено.")
        
        await state.clear()

@router.callback_query(F.data.startswith("admin_delete_service_"))
async def admin_delete_service(callback: CallbackQuery):
    """Удалить услугу"""
    service_id = int(callback.data.split("_")[-1])
    await ServiceService.delete_service(service_id)
    await callback.answer("Услуга удалена")
    await admin_services(callback)

@router.callback_query(F.data.startswith("admin_add_note_"))
async def admin_add_note_start(callback: CallbackQuery, state: FSMContext):
    """Начало добавления заметки"""
    client_id = int(callback.data.split("_")[-1])
    
    await state.update_data(client_id=client_id)
    await callback.message.edit_text(
        "📝 <b>Добавление заметки</b>\n\nВведите текст заметки:",
        parse_mode='HTML'
    )
    await state.set_state(AdminStates.adding_note)

@router.message(StateFilter(AdminStates.adding_note))
async def admin_add_note_process(message: Message, state: FSMContext):
    """Обработка добавления заметки"""
    data = await state.get_data()
    client_id = data.get('client_id')
    
    if not client_id:
        await message.answer("Ошибка: клиент не выбран")
        await state.clear()
        return
    
    note_text = message.text.strip()
    
    if not note_text:
        await message.answer("❌ Заметка не может быть пустой. Введите текст:")
        return
    
    # Сохраняем заметку
    await db.execute("""
        INSERT INTO client_notes (client_id, note)
        VALUES ($1, $2)
    """, client_id, note_text)
    
    await message.answer("✅ Заметка добавлена!")
    await state.clear()
    
    # Возвращаемся к деталям клиента через callback
    # Используем CallbackQuery для этого, но так как у нас Message, создадим callback вручную
    from aiogram.types import CallbackQuery
    # Проще отправить новое сообщение со списком клиентов
    await admin_clients_callback_helper(message)

async def admin_clients_callback_helper(message: Message):
    """Helper для возврата к списку клиентов"""
    clients = await db.fetch("""
        SELECT u.id, u.telegram_id, u.full_name, u.username, c.id as client_id
        FROM users u
        LEFT JOIN clients c ON u.id = c.user_id
        WHERE u.is_admin = FALSE
        ORDER BY u.created_at DESC
        LIMIT 50
    """)
    
    if not clients:
        await message.answer("👥 Клиентов пока нет", parse_mode='HTML')
        return
    
    text = "👥 <b>Управление клиентами</b>\n\nВыберите клиента для просмотра деталей:"
    keyboard_buttons = []
    
    for client in clients:
        name = client['full_name'] or client['username'] or f"ID: {client['telegram_id']}"
        client_id = client['client_id'] or client['id']
        keyboard_buttons.append([
            InlineKeyboardButton(
                text=name[:40],
                callback_data=f"admin_client_{client_id}"
            )
        ])
    
    keyboard_buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    await message.answer(text, reply_markup=keyboard, parse_mode='HTML')

@router.callback_query(F.data.startswith("admin_blacklist_"))
async def admin_blacklist_add(callback: CallbackQuery):
    """Добавить клиента в черный список"""
    client_id = int(callback.data.split("_")[-1])
    
    # Получаем user_id из clients или используем client_id как user_id
    client = await db.fetchrow("SELECT user_id FROM clients WHERE id = $1", client_id)
    
    if not client:
        # Если не найден в clients, возможно это user_id
        user = await db.fetchrow("SELECT id FROM users WHERE id = $1 AND is_admin = FALSE", client_id)
        if not user:
            await callback.answer("Клиент не найден", show_alert=True)
            return
        user_id = client_id
    else:
        user_id = client['user_id']
    
    # Проверяем, не в черном списке ли уже
    existing = await db.fetchrow("SELECT id FROM blacklist WHERE user_id = $1", user_id)
    if existing:
        await callback.answer("Клиент уже в черном списке", show_alert=True)
        return
    
    # Добавляем в черный список
    await db.execute("""
        INSERT INTO blacklist (user_id, reason)
        VALUES ($1, $2)
    """, user_id, "Добавлен администратором")
    
    await callback.answer("Клиент добавлен в черный список")
    
    # Находим client_id для отображения деталей
    client = await db.fetchrow("SELECT id FROM clients WHERE user_id = $1", user_id)
    client_id = client['id'] if client else None
    
    if not client_id:
        # Создаем запись в clients если её нет
        existing = await db.fetchrow("SELECT id FROM clients WHERE user_id = $1", user_id)
        if existing:
            client_id = existing['id']
        else:
            client_id = await db.fetchval("""
                INSERT INTO clients (user_id) VALUES ($1) RETURNING id
            """, user_id)
    
    if client_id:
        await _show_client_detail(client_id, callback.message)

# ========== ОБРАБОТЧИКИ ДЛЯ РЕДАКТИРОВАНИЯ ЗАПИСЕЙ ==========

@router.callback_query(F.data.startswith("admin_edit_appointment_"))
async def admin_edit_appointment_start(callback: CallbackQuery, state: FSMContext):
    """Начало редактирования записи администратором"""
    appointment_id = int(callback.data.split("_")[-1])
    appointment = await AppointmentService.get_appointment(appointment_id)
    
    if not appointment:
        await callback.answer("Запись не найдена", show_alert=True)
        return
    
    service = await ServiceService.get_service(appointment.service_id)
    client = await db.fetchrow("SELECT * FROM users WHERE id = $1", appointment.client_id)
    
    status_texts = {
        'pending': '⏳ Ожидает подтверждения',
        'confirmed': '✅ Подтверждена',
        'cancelled': '❌ Отменена',
        'completed': '✓ Завершена',
        'no_show': '🚫 Не пришёл',
        'moved': '🔄 Перенесена'
    }
    
    text = (
        f"✏️ <b>Редактирование записи #{appointment_id}</b>\n\n"
        f"Клиент: {client['full_name'] or client['username'] or 'Без имени'}\n"
        f"Услуга: {service.name if service else 'Неизвестно'}\n"
        f"Дата: {format_datetime(appointment.appointment_date)}\n"
        f"Статус: {status_texts.get(appointment.status, appointment.status)}\n"
        f"Стоимость: {appointment.total_price:.0f} ₽\n"
    )
    
    if appointment.admin_comment:
        text += f"Комментарий: {appointment.admin_comment}\n"
    
    text += "\nЧто хотите изменить?"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 Дата и время", callback_data=f"admin_appointment_edit_date_{appointment_id}")],
        [InlineKeyboardButton(text="📋 Услуга", callback_data=f"admin_appointment_edit_service_{appointment_id}")],
        [InlineKeyboardButton(text="📊 Статус", callback_data=f"admin_appointment_edit_status_{appointment_id}")],
        [InlineKeyboardButton(text="💬 Комментарий", callback_data=f"admin_appointment_edit_comment_{appointment_id}")],
        [InlineKeyboardButton(text="📧 Уведомить клиента", callback_data=f"admin_notify_appointment_change_{appointment_id}")],
        [InlineKeyboardButton(text="📜 История изменений", callback_data=f"admin_appointment_history_{appointment_id}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_history")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode='HTML')
    await state.update_data(appointment_id=appointment_id)

@router.callback_query(F.data.startswith("admin_appointment_edit_date_"))
async def admin_edit_appointment_date(callback: CallbackQuery, state: FSMContext):
    """Редактирование даты и времени записи"""
    appointment_id = int(callback.data.split("_")[-1])
    await state.update_data(appointment_id=appointment_id, edit_field='date')
    
    await callback.message.edit_text(
        "📅 <b>Изменение даты и времени</b>\n\n"
        "Введите новую дату и время в формате: ДД.ММ.ГГГГ ЧЧ:ММ\n"
        "Например: 25.12.2024 14:30",
        parse_mode='HTML'
    )
    await state.set_state(AdminStates.editing_appointment_date)

@router.message(StateFilter(AdminStates.editing_appointment_date))
async def admin_edit_appointment_date_process(message: Message, state: FSMContext, bot: Bot):
    """Обработка изменения даты и времени"""
    data = await state.get_data()
    appointment_id = data.get('appointment_id')
    
    try:
        appointment_datetime = datetime.strptime(message.text.strip(), "%d.%m.%Y %H:%M")
        
        appointment = await AppointmentService.get_appointment(appointment_id)
        if not appointment:
            await message.answer("Запись не найдена")
            await state.clear()
            return
        
        old_date = appointment.appointment_date
        
        admin_user = await db.fetchrow("SELECT id FROM users WHERE telegram_id = $1", message.from_user.id)
        admin_user_id = admin_user['id'] if admin_user else None
        
        await AppointmentService.update_appointment(appointment_id, appointment_date=appointment_datetime, changed_by=admin_user_id)
        
        await message.answer("✅ Дата и время записи обновлены!")
        await state.clear()
    except ValueError:
        await message.answer("❌ Неверный формат. Используйте: ДД.ММ.ГГГГ ЧЧ:ММ (например: 25.12.2024 14:30)")

@router.callback_query(F.data.startswith("admin_appointment_edit_service_"))
async def admin_edit_appointment_service(callback: CallbackQuery, state: FSMContext):
    """Редактирование услуги записи"""
    appointment_id = int(callback.data.split("_")[-1])
    
    services = await ServiceService.get_all_services(only_active=True)
    
    keyboard_buttons = []
    for service in services:
        keyboard_buttons.append([
            InlineKeyboardButton(
                text=f"{service.name} - {service.price:.0f} ₽",
                callback_data=f"admin_appointment_set_service_{appointment_id}_{service.id}"
            )
        ])
    
    keyboard_buttons.append([InlineKeyboardButton(text="🔙 Отмена", callback_data=f"admin_edit_appointment_{appointment_id}")])
    
    await callback.message.edit_text(
        "📋 <b>Выбор услуги</b>\n\nВыберите новую услугу:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_buttons),
        parse_mode='HTML'
    )

@router.callback_query(F.data.startswith("admin_appointment_set_service_"))
async def admin_set_appointment_service(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Установка новой услуги для записи"""
    parts = callback.data.split("_")
    appointment_id = int(parts[-2])  # предпоследний элемент
    service_id = int(parts[-1])      # последний элемент
    
    appointment = await AppointmentService.get_appointment(appointment_id)
    if not appointment:
        await callback.answer("Запись не найдена", show_alert=True)
        return
    
    old_service = await ServiceService.get_service(appointment.service_id)
    new_service = await ServiceService.get_service(service_id)
    
    if not new_service:
        await callback.answer("Услуга не найдена", show_alert=True)
        return
    
    admin_user = await db.fetchrow("SELECT id FROM users WHERE telegram_id = $1", callback.from_user.id)
    admin_user_id = admin_user['id'] if admin_user else None
    
    await AppointmentService.update_appointment(appointment_id, service_id=service_id, changed_by=admin_user_id)
    
    await callback.answer("✅ Услуга обновлена!")
    # Обновляем запись и показываем меню редактирования
    appointment = await AppointmentService.get_appointment(appointment_id)
    if appointment:
        await admin_edit_appointment_start(callback, state)

@router.callback_query(F.data.startswith("admin_appointment_edit_status_"))
async def admin_edit_appointment_status(callback: CallbackQuery, state: FSMContext):
    """Редактирование статуса записи"""
    appointment_id = int(callback.data.split("_")[-1])
    
    appointment = await AppointmentService.get_appointment(appointment_id)
    if not appointment:
        await callback.answer("Запись не найдена", show_alert=True)
        return
    
    statuses = [
        ('pending', '⏳ Ожидает подтверждения'),
        ('confirmed', '✅ Подтверждена'),
        ('completed', '✓ Завершена'),
        ('cancelled', '❌ Отменена'),
        ('no_show', '🚫 Не пришёл'),
        ('moved', '🔄 Перенесена')
    ]
    
    keyboard_buttons = []
    for status_key, status_text in statuses:
        # Используем специальный разделитель для статусов с подчеркиваниями
        keyboard_buttons.append([
            InlineKeyboardButton(
                text=status_text,
                callback_data=f"admin_appointment_set_status|{appointment_id}|{status_key}"
            )
        ])
    
    keyboard_buttons.append([InlineKeyboardButton(text="🔙 Отмена", callback_data=f"admin_edit_appointment_{appointment_id}")])
    
    await state.update_data(appointment_id=appointment_id)
    await callback.message.edit_text(
        "📊 <b>Выбор статуса</b>\n\nВыберите новый статус записи:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_buttons),
        parse_mode='HTML'
    )

@router.callback_query(F.data.startswith("admin_appointment_set_status|"))
async def admin_set_appointment_status(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Установка нового статуса записи"""
    # Используем | как разделитель для корректной обработки статусов с подчеркиваниями
    parts = callback.data.split("|")
    appointment_id = int(parts[1])
    new_status = parts[2]
    
    appointment = await AppointmentService.get_appointment(appointment_id)
    if not appointment:
        await callback.answer("Запись не найдена", show_alert=True)
        return
    
    old_status = appointment.status
    status_texts = {
        'pending': '⏳ Ожидает подтверждения',
        'confirmed': '✅ Подтверждена',
        'cancelled': '❌ Отменена',
        'completed': '✓ Завершена',
        'no_show': '🚫 Не пришёл',
        'moved': '🔄 Перенесена'
    }
    
    # Сохраняем изменение в историю
    admin_user = await db.fetchrow("SELECT id FROM users WHERE telegram_id = $1", callback.from_user.id)
    admin_user_id = admin_user['id'] if admin_user else None
    
    await AppointmentService.update_appointment(appointment_id, status=new_status, changed_by=admin_user_id)
    
    # Показываем меню с кнопкой уведомления
    status_text = status_texts.get(new_status, new_status)
    
    text = (
        f"✅ <b>Статус обновлен</b>\n\n"
        f"Старый статус: {status_texts.get(old_status, old_status)}\n"
        f"Новый статус: {status_text}\n\n"
        f"Хотите уведомить клиента об изменении?"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📧 Уведомить клиента", callback_data=f"admin_notify_status_change|{appointment_id}|{new_status}")],
        [InlineKeyboardButton(text="🔙 Вернуться к редактированию", callback_data=f"admin_edit_appointment_{appointment_id}")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode='HTML')
    await callback.answer("✅ Статус обновлен!")

@router.callback_query(F.data.startswith("admin_notify_appointment_change_"))
async def admin_notify_appointment_change(callback: CallbackQuery, bot: Bot):
    """Уведомление клиента об изменении записи"""
    appointment_id = int(callback.data.split("_")[-1])
    
    appointment = await AppointmentService.get_appointment(appointment_id)
    if not appointment:
        await callback.answer("Запись не найдена", show_alert=True)
        return
    
    client = await db.fetchrow("SELECT telegram_id FROM users WHERE id = $1", appointment.client_id)
    if not client or not client['telegram_id']:
        await callback.answer("❌ Клиент не найден", show_alert=True)
        return
    
    service = await ServiceService.get_service(appointment.service_id)
    
    # Получаем дополнительные услуги
    additional_services = await db.fetch("""
        SELECT s.name, s.price
        FROM appointment_additional_services aas
        JOIN services s ON aas.service_id = s.id
        WHERE aas.appointment_id = $1
    """, appointment_id)
    
    status_texts = {
        'pending': '⏳ Ожидает подтверждения',
        'confirmed': '✅ Подтверждена',
        'cancelled': '❌ Отменена',
        'completed': '✓ Завершена',
        'no_show': '🚫 Не пришёл',
        'moved': '🔄 Перенесена'
    }
    
    message_text = (
        f"📋 <b>Изменение записи</b>\n\n"
        f"Ваша запись была изменена.\n\n"
        f"Услуга: {service.name if service else 'Неизвестно'}\n"
    )
    
    if additional_services:
        message_text += "\n<b>Дополнительные услуги:</b>\n"
        for add_service in additional_services:
            message_text += f"  ➕ {add_service['name']} - {add_service['price']:.0f} ₽\n"
    
    message_text += (
        f"\nДата: {format_datetime(appointment.appointment_date)}\n"
        f"Стоимость: {appointment.total_price:.0f} ₽\n"
        f"Статус: {status_texts.get(appointment.status, appointment.status)}\n\n"
        f"Если у вас есть вопросы, свяжитесь с мастером."
    )
    
    try:
        await bot.send_message(
            client['telegram_id'],
            message_text,
            parse_mode='HTML'
        )
        await callback.answer("✅ Клиент уведомлен!")
    except Exception as e:
        await callback.answer(f"❌ Ошибка отправки уведомления: {str(e)}", show_alert=True)

@router.callback_query(F.data.startswith("admin_notify_status_change|"))
async def admin_notify_status_change(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Уведомление клиента об изменении статуса"""
    parts = callback.data.split("|")
    appointment_id = int(parts[1])
    new_status = parts[2]
    
    appointment = await AppointmentService.get_appointment(appointment_id)
    if not appointment:
        await callback.answer("Запись не найдена", show_alert=True)
        return
    
    status_texts = {
        'pending': '⏳ Ожидает подтверждения',
        'confirmed': '✅ Подтверждена',
        'cancelled': '❌ Отменена',
        'completed': '✓ Завершена',
        'no_show': '🚫 Не пришёл',
        'moved': '🔄 Перенесена'
    }
    
    # Отправляем уведомление клиенту
    client = await db.fetchrow("SELECT telegram_id FROM users WHERE id = $1", appointment.client_id)
    if client and client['telegram_id']:
        try:
            service = await ServiceService.get_service(appointment.service_id)
            await bot.send_message(
                client['telegram_id'],
                f"📊 <b>Изменение статуса записи</b>\n\n"
                f"Статус вашей записи изменен.\n\n"
                f"Услуга: {service.name if service else 'Неизвестно'}\n"
                f"Дата: {format_datetime(appointment.appointment_date)}\n"
                f"Новый статус: {status_texts.get(new_status, new_status)}\n\n"
                f"Если у вас есть вопросы, свяжитесь с мастером.",
                parse_mode='HTML'
            )
            await callback.answer("✅ Клиент уведомлен!")
        except Exception as e:
            await callback.answer(f"❌ Ошибка отправки уведомления: {str(e)}", show_alert=True)
            return
    else:
        await callback.answer("❌ Клиент не найден", show_alert=True)
        return
    
    # Возвращаемся к редактированию записи
    appointment = await AppointmentService.get_appointment(appointment_id)
    if appointment:
        # Создаем временный state для вызова функции
        temp_state = FSMContext(
            storage=state.storage,
            key=state.key
        )
        await admin_edit_appointment_start(callback, temp_state)

@router.callback_query(F.data.startswith("admin_appointment_history_"))
async def admin_appointment_history(callback: CallbackQuery):
    """Просмотр истории изменений записи"""
    appointment_id = int(callback.data.split("_")[-1])
    
    appointment = await AppointmentService.get_appointment(appointment_id)
    if not appointment:
        await callback.answer("Запись не найдена", show_alert=True)
        return
    
    # Получаем историю изменений
    history = await db.fetch("""
        SELECT h.*, u.full_name, u.username
        FROM appointments_history h
        LEFT JOIN users u ON h.changed_by = u.id
        WHERE h.appointment_id = $1
        ORDER BY h.created_at DESC
        LIMIT 50
    """, appointment_id)
    
    service = await ServiceService.get_service(appointment.service_id)
    client = await db.fetchrow("SELECT * FROM users WHERE id = $1", appointment.client_id)
    
    text = (
        f"📜 <b>История изменений записи #{appointment_id}</b>\n\n"
        f"Клиент: {client['full_name'] or client['username'] or 'Без имени'}\n"
        f"Услуга: {service.name if service else 'Неизвестно'}\n"
        f"Дата записи: {format_datetime(appointment.appointment_date)}\n\n"
        f"<b>История изменений:</b>\n\n"
    )
    
    status_texts = {
        'pending': '⏳ Ожидает подтверждения',
        'confirmed': '✅ Подтверждена',
        'cancelled': '❌ Отменена',
        'completed': '✓ Завершена',
        'no_show': '🚫 Не пришёл',
        'moved': '🔄 Перенесена'
    }
    
    if not history:
        text += "История изменений пуста"
    else:
        for record in history:
            changed_by_name = record['full_name'] or record['username'] or 'Система'
            change_time = format_datetime(record['created_at'])
            
            text += f"🕐 {change_time}\n"
            text += f"   Изменил: {changed_by_name}\n"
            
            if record['old_status'] or record['new_status']:
                old_status_text = status_texts.get(record['old_status'], record['old_status']) if record['old_status'] else '—'
                new_status_text = status_texts.get(record['new_status'], record['new_status']) if record['new_status'] else '—'
                text += f"   Статус: {old_status_text} → {new_status_text}\n"
            
            if record['change_reason']:
                text += f"   Причина: {record['change_reason']}\n"
            
            text += "\n"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Вернуться к редактированию", callback_data=f"admin_edit_appointment_{appointment_id}")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode='HTML')

@router.callback_query(F.data.startswith("admin_appointment_edit_comment_"))
async def admin_edit_appointment_comment(callback: CallbackQuery, state: FSMContext):
    """Редактирование комментария к записи"""
    appointment_id = int(callback.data.split("_")[-1])
    
    appointment = await AppointmentService.get_appointment(appointment_id)
    if not appointment:
        await callback.answer("Запись не найдена", show_alert=True)
        return
    
    await state.update_data(appointment_id=appointment_id)
    
    text = "💬 <b>Добавление/изменение комментария</b>\n\n"
    if appointment.admin_comment:
        text += f"Текущий комментарий: {appointment.admin_comment}\n\n"
    text += "Введите новый комментарий (или '-' для удаления):"
    
    await callback.message.edit_text(text, parse_mode='HTML')
    await state.set_state(AdminStates.editing_appointment_comment)

@router.message(StateFilter(AdminStates.editing_appointment_comment))
async def admin_edit_appointment_comment_process(message: Message, state: FSMContext):
    """Обработка изменения комментария"""
    data = await state.get_data()
    appointment_id = data.get('appointment_id')
    
    comment = message.text.strip() if message.text.strip() != '-' else None
    
    admin_user = await db.fetchrow("SELECT id FROM users WHERE telegram_id = $1", message.from_user.id)
    admin_user_id = admin_user['id'] if admin_user else None
    
    await AppointmentService.update_appointment(appointment_id, admin_comment=comment, changed_by=admin_user_id)
    
    await message.answer("✅ Комментарий обновлен!")
    await state.clear()

# ========== ИСТОРИЯ ВИЗИТОВ КЛИЕНТА ==========

async def _show_client_history_page(client_id: int, page: int, message_or_edit, page_size: int = 5):
    """Показать страницу истории визитов клиента"""
    from utils.timezone import format_datetime
    
    # Получаем user_id
    client_row = await db.fetchrow("SELECT user_id FROM clients WHERE id = $1", client_id)
    if not client_row:
        await message_or_edit.edit_text("Клиент не найден")
        return
    
    user_id = client_row['user_id']
    
    offset = page * page_size
    
    appointments = await db.fetch("""
        SELECT a.*, s.name as service_name
        FROM appointments a
        JOIN services s ON a.service_id = s.id
        WHERE a.client_id = $1
        ORDER BY a.appointment_date DESC
        LIMIT $2 OFFSET $3
    """, user_id, page_size, offset)
    
    total_count = await db.fetchval("""
        SELECT COUNT(*) FROM appointments WHERE client_id = $1
    """, user_id)
    
    client_info = await db.fetchrow("""
        SELECT u.full_name, u.username, u.telegram_id
        FROM users u
        WHERE u.id = $1
    """, user_id)
    
    total_pages = (total_count + page_size - 1) // page_size if total_count > 0 else 1
    
    name = client_info['full_name'] or client_info['username'] or 'Без имени'
    client_links = []
    if client_info.get('username'):
        client_links.append(f"@{client_info['username']}")
    if client_info.get('telegram_id'):
        client_links.append(f"tg://user?id={client_info['telegram_id']}")
    
    text = f"📋 <b>История визитов: {name}</b>\n"
    if client_links:
        text += f"Ссылки: {', '.join(client_links)}\n"
    text += f"Страница {page + 1}/{total_pages}\n\n"
    
    status_emoji = {
        'pending': '⏳',
        'confirmed': '✅',
        'cancelled': '❌',
        'completed': '✓',
        'no_show': '🚫',
        'moved': '🔄'
    }
    
    if not appointments:
        text += "Записей пока нет"
    else:
        for apt in appointments:
            emoji = status_emoji.get(apt['status'], '❓')
            text += f"{emoji} {format_datetime(apt['appointment_date'])}\n"
            text += f"   {apt['service_name']}\n"
            text += f"   {float(apt['total_price']):.0f} ₽\n"
            if apt.get('admin_comment'):
                text += f"   💬 {apt['admin_comment']}\n"
            text += f"   ID: {apt['id']}\n\n"
    
    keyboard_buttons = []
    
    # Кнопки для редактирования записей
    for apt in appointments:
        keyboard_buttons.append([
            InlineKeyboardButton(
                text=f"✏️ Запись #{apt['id']} - {format_datetime(apt['appointment_date'], '%d.%m %H:%M')}",
                callback_data=f"admin_edit_appointment_{apt['id']}"
            )
        ])
    
    # Кнопки навигации
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️", callback_data=f"admin_client_history_{client_id}_{page - 1}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton(text="➡️", callback_data=f"admin_client_history_{client_id}_{page + 1}"))
    if nav_buttons:
        keyboard_buttons.append(nav_buttons)
    
    keyboard_buttons.append([InlineKeyboardButton(text="🔙 Назад к клиенту", callback_data=f"admin_client_{client_id}")])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    await message_or_edit.edit_text(text, reply_markup=keyboard, parse_mode='HTML')

@router.callback_query(F.data.startswith("admin_client_history_"))
async def admin_client_history(callback: CallbackQuery):
    """Просмотр истории визитов клиента"""
    parts = callback.data.split("_")
    client_id = int(parts[-2])
    page = int(parts[-1])
    await _show_client_history_page(client_id, page, callback.message)

@router.callback_query(F.data.startswith("admin_unblacklist_"))
async def admin_unblacklist_remove(callback: CallbackQuery):
    """Убрать клиента из черного списка"""
    user_id = int(callback.data.split("_")[-1])
    
    # Удаляем из черного списка
    await db.execute("DELETE FROM blacklist WHERE user_id = $1", user_id)
    
    await callback.answer("Клиент убран из черного списка")
    
    # Находим client_id для возврата к деталям
    client = await db.fetchrow("SELECT id FROM clients WHERE user_id = $1", user_id)
    client_id = client['id'] if client else None
    
    if not client_id:
        # Создаем запись в clients если её нет
        existing = await db.fetchrow("SELECT id FROM clients WHERE user_id = $1", user_id)
        if existing:
            client_id = existing['id']
        else:
            client_id = await db.fetchval("""
                INSERT INTO clients (user_id) VALUES ($1) RETURNING id
            """, user_id)
    
    if client_id:
        # Обновляем детали клиента через вспомогательную функцию
        await _show_client_detail(client_id, callback.message)
    else:
        await callback.message.edit_text("✅ Клиент убран из черного списка")

@router.callback_query(F.data.startswith("admin_delete_client_"))
async def admin_delete_client(callback: CallbackQuery):
    """Удалить клиента"""
    client_id = int(callback.data.split("_")[-1])
    
    # Получаем информацию о клиенте
    client = await db.fetchrow("""
        SELECT c.*, u.telegram_id, u.id as user_id, u.full_name, u.username
        FROM clients c
        JOIN users u ON c.user_id = u.id
        WHERE c.id = $1
    """, client_id)
    
    if not client:
        await callback.answer("Клиент не найден", show_alert=True)
        return
    
    user_id = client['user_id']
    
    # Проверяем наличие активных записей
    active_appointments = await db.fetchval("""
        SELECT COUNT(*) FROM appointments
        WHERE client_id = $1 AND status IN ('pending', 'confirmed')
    """, user_id)
    
    if active_appointments > 0:
        await callback.answer(
            f"❌ Нельзя удалить клиента с активными записями ({active_appointments}). Сначала отмените записи.",
            show_alert=True
        )
        return
    
    # Удаляем все записи о напоминаниях для этого клиента
    await db.execute("""
        DELETE FROM reminders 
        WHERE appointment_id IN (SELECT id FROM appointments WHERE client_id = $1)
    """, user_id)
    
    # Отменяем все неактивные записи (на всякий случай)
    await db.execute("""
        UPDATE appointments 
        SET status = 'cancelled' 
        WHERE client_id = $1 AND status NOT IN ('cancelled', 'completed')
    """, user_id)
    
    # Удаляем все записи клиента
    await db.execute("DELETE FROM appointments WHERE client_id = $1", user_id)
    
    # Удаляем из черного списка если был там
    await db.execute("DELETE FROM blacklist WHERE user_id = $1", user_id)
    
    # Удаляем клиента (CASCADE удалит notes и tags)
    await db.execute("DELETE FROM clients WHERE id = $1", client_id)
    
    # Удаляем пользователя из users
    await db.execute("DELETE FROM users WHERE id = $1", user_id)
    
    await callback.answer("✅ Клиент удален")
    
    # Возвращаемся к списку клиентов
    await admin_clients(callback)

