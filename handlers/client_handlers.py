"""Обработчики для клиентов"""
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from datetime import datetime, date, timedelta
from typing import List

from services.user_service import UserService
from services.service_service import ServiceService
from services.schedule_service import ScheduleService
from services.appointment_service import AppointmentService
from services.info_service import InfoService
from services.bot_settings_service import BotSettingsService
from utils.timezone import format_datetime, format_date, get_current_datetime_in_master_tz
from database import db

router = Router()

class BookingStates(StatesGroup):
    """Состояния для процесса записи"""
    selecting_service = State()
    selecting_date = State()
    selecting_time = State()
    selecting_additional_services = State()
    editing_appointment = State()
    editing_appointment_date = State()
    editing_appointment_service = State()
    waiting_for_confirmation = State()

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    """Обработчик команды /start"""
    # Получаем или создаем пользователя
    user = await UserService.get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name
    )
    
    # Проверяем черный список
    if await UserService.is_blacklisted(message.from_user.id):
        await message.answer("❌ Доступ ограничен")
        return
    
    # Сбрасываем состояние
    await state.clear()
    
    # Получаем приветственное сообщение (можно кастомизировать через настройки)
    welcome_text = await BotSettingsService.get_setting(
        'welcome_message',
        '👋 Добро пожаловать! Я помогу вам записаться на услугу.'
    )
    
    # Главное меню
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 Записаться", callback_data="book_service")],
        [InlineKeyboardButton(text="📋 Мои записи", callback_data="my_appointments")],
        [InlineKeyboardButton(text="ℹ️ Информация", callback_data="info")],
        [InlineKeyboardButton(text="❓ Частые вопросы", callback_data="faq")],
        [InlineKeyboardButton(text="📞 Связаться с мастером", callback_data="contact_master")]
    ])
    
    await message.answer(welcome_text, reply_markup=keyboard)

@router.callback_query(F.data == "book_service")
async def show_services(callback: CallbackQuery, state: FSMContext):
    """Показать список услуг"""
    services = await ServiceService.get_all_services(only_active=True, only_main=True)
    
    if not services:
        await callback.answer("На данный момент услуги не доступны", show_alert=True)
        return
    
    keyboard_buttons = []
    for service in services:
        keyboard_buttons.append([
            InlineKeyboardButton(
                text=f"{service.name} - {service.price:.0f} ₽ ({service.duration_minutes} мин)",
                callback_data=f"select_service_{service.id}"
            )
        ])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    
    await callback.message.edit_text("Выберите услугу:", reply_markup=keyboard)
    await state.set_state(BookingStates.selecting_service)

@router.callback_query(F.data.startswith("select_service_"))
async def select_service(callback: CallbackQuery, state: FSMContext):
    """Выбрать услугу и показать выбор дополнительных услуг"""
    service_id = int(callback.data.split("_")[-1])
    service = await ServiceService.get_service(service_id)
    
    if not service:
        await callback.answer("Услуга не найдена", show_alert=True)
        return
    
    # Сохраняем выбранную услугу в состояние
    await state.update_data(service_id=service_id, selected_additional_services=[])
    
    # Получаем доступные дополнительные услуги для этой основной услуги
    additional_services = await db.fetch("""
        SELECT s.* 
        FROM services s
        LEFT JOIN services_additional_links sal ON s.id = sal.additional_service_id
        WHERE s.is_active = TRUE 
        AND s.is_additional = TRUE
        AND (sal.main_service_id = $1 OR sal.main_service_id IS NULL)
    """, service_id)
    
    # Формируем информацию об услуге
    service_info = (
        f"<b>{service.name}</b>\n\n"
        f"💵 Цена: {service.price:.0f} ₽\n"
        f"⏱ Длительность: {service.duration_minutes} минут\n"
    )
    
    if service.description:
        service_info += f"\n{service.description}\n"
    
    if additional_services:
        service_info += "\n\nВыберите дополнительные услуги (необязательно):"
        
        keyboard_buttons = []
        for add_service in additional_services:
            keyboard_buttons.append([
                InlineKeyboardButton(
                    text=f"➕ {add_service['name']} (+{add_service['price']:.0f} ₽)",
                    callback_data=f"add_additional_service_{add_service['id']}"
                )
            ])
        
        keyboard_buttons.append([
            InlineKeyboardButton(text="✅ Перейти к выбору даты", callback_data="continue_to_date")
        ])
        keyboard_buttons.append([
            InlineKeyboardButton(text="🔙 Назад", callback_data="book_service")
        ])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        await callback.message.edit_text(service_info, reply_markup=keyboard, parse_mode='HTML')
        await state.set_state(BookingStates.selecting_additional_services)
    else:
        # Нет дополнительных услуг - переходим сразу к календарю
        service_info += "\nВыберите дату:"
        
        # Показываем календарь на текущий месяц
        current_date = get_current_datetime_in_master_tz()
        keyboard = await _generate_calendar(current_date.year, current_date.month)
        
        await callback.message.edit_text(service_info, reply_markup=keyboard, parse_mode='HTML')
        await state.set_state(BookingStates.selecting_date)

async def _generate_calendar(year: int, month: int, admin_mode: bool = False) -> InlineKeyboardMarkup:
    """Генерация календаря для выбора даты"""
    import calendar
    
    keyboard_buttons = []
    
    # Заголовок с месяцем и годом
    month_names = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
                   'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь']
    header = f"{month_names[month-1]} {year}"
    
    if admin_mode:
        prev_callback = f"admin_calendar_prev_{year}_{month}"
        next_callback = f"admin_calendar_next_{year}_{month}"
    else:
        prev_callback = f"calendar_prev_{year}_{month}"
        next_callback = f"calendar_next_{year}_{month}"
    
    keyboard_buttons.append([
        InlineKeyboardButton(text="◀️", callback_data=prev_callback),
        InlineKeyboardButton(text=header, callback_data="calendar_header"),
        InlineKeyboardButton(text="▶️", callback_data=next_callback)
    ])
    
    # Дни недели
    weekdays = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
    keyboard_buttons.append([
        InlineKeyboardButton(text=day, callback_data="calendar_weekday")
        for day in weekdays
    ])
    
    # Календарь
    cal = calendar.monthcalendar(year, month)
    today = get_current_datetime_in_master_tz().date()
    
    for week in cal:
        week_buttons = []
        for day in week:
            if day == 0:
                week_buttons.append(InlineKeyboardButton(text=" ", callback_data="calendar_empty"))
            else:
                day_date = date(year, month, day)
                if admin_mode:
                    # В режиме админа скрываем прошедшие даты
                    if day_date < today:
                        week_buttons.append(InlineKeyboardButton(text=" ", callback_data="calendar_empty"))
                    else:
                        # В режиме админа проверяем, можно ли настроить дату
                        schedule = await ScheduleService.get_schedule_for_date(day_date)
                        is_fully_booked = await ScheduleService.is_date_fully_booked(day_date)
                        
                        # Скрываем полностью занятые дни и выходные
                        if schedule and schedule.is_day_off:
                            week_buttons.append(InlineKeyboardButton(text=" ", callback_data="calendar_empty"))
                        elif is_fully_booked and schedule and not schedule.is_day_off:
                            week_buttons.append(InlineKeyboardButton(text=" ", callback_data="calendar_empty"))
                        else:
                            # Показываем дату как доступную для настройки
                            week_buttons.append(InlineKeyboardButton(
                                text=str(day),
                                callback_data=f"admin_schedule_date_{year}-{month:02d}-{day:02d}"
                            ))
                else:
                    # Для клиентов скрываем прошедшие даты
                    if day_date < today:
                        week_buttons.append(InlineKeyboardButton(text=" ", callback_data="calendar_past"))
                    else:
                        # Проверяем, есть ли расписание на этот день
                        schedule = await ScheduleService.get_schedule_for_date(day_date)
                        if schedule:
                            if schedule.is_day_off:
                                # Скрываем выходные дни
                                week_buttons.append(InlineKeyboardButton(text=" ", callback_data="calendar_empty"))
                            elif schedule.start_time:
                                # Проверяем, есть ли доступные слоты на этот день
                                slots = await ScheduleService.get_available_slots(day_date, 30, [])
                                if slots:
                                    week_buttons.append(InlineKeyboardButton(
                                        text=str(day),
                                        callback_data=f"calendar_date_{year}_{month}_{day}"
                                    ))
                                else:
                                    # Нет доступных слотов - скрываем
                                    week_buttons.append(InlineKeyboardButton(text=" ", callback_data="calendar_empty"))
                            else:
                                # Нет рабочих часов - скрываем
                                week_buttons.append(InlineKeyboardButton(text=" ", callback_data="calendar_empty"))
                        else:
                            # Если расписания нет - скрываем дату
                            week_buttons.append(InlineKeyboardButton(text=" ", callback_data="calendar_empty"))
        keyboard_buttons.append(week_buttons)
    
    if admin_mode:
        keyboard_buttons.append([
            InlineKeyboardButton(text="🔙 Назад", callback_data="admin_schedule")
        ])
    else:
        keyboard_buttons.append([
            InlineKeyboardButton(text="🔙 Назад", callback_data="book_service")
        ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

async def _generate_calendar_admin(year: int, month: int) -> InlineKeyboardMarkup:
    """Генерация календаря для админа"""
    return await _generate_calendar(year, month, admin_mode=True)

@router.callback_query(F.data.startswith("calendar_"))
async def handle_calendar(callback: CallbackQuery, state: FSMContext):
    """Обработка действий с календарем"""
    data = callback.data
    
    if data.startswith("calendar_date_"):
        # Выбрана дата
        _, _, year, month, day = data.split("_")
        selected_date = date(int(year), int(month), int(day))
        
        data = await state.get_data()
        service_id = data.get('service_id')
        
        if not service_id:
            await callback.answer("Ошибка: услуга не выбрана", show_alert=True)
            return
        
        service = await ServiceService.get_service(service_id)
        if not service:
            await callback.answer("Услуга не найдена", show_alert=True)
            return
        
        # Получаем доступные слоты времени
        existing_appointments = await db.fetch("""
            SELECT appointment_date FROM appointments
            WHERE DATE(appointment_date) = $1
            AND status IN ('pending', 'confirmed')
        """, selected_date)
        
        existing_times = [row['appointment_date'] for row in existing_appointments]
        slots = await ScheduleService.get_available_slots(
            selected_date,
            service.duration_minutes,
            existing_times
        )
        
        if not slots:
            await callback.answer("На эту дату нет свободного времени", show_alert=True)
            return
        
        # Показываем доступные временные слоты
        keyboard_buttons = []
        for slot in slots[:20]:  # Ограничиваем до 20 слотов
            keyboard_buttons.append([
                InlineKeyboardButton(
                    text=format_datetime(slot, "%H:%M"),
                    callback_data=f"select_time_{slot.strftime('%Y-%m-%d %H:%M')}"
                )
            ])
        
        keyboard_buttons.append([
            InlineKeyboardButton(text="🔙 Назад", callback_data="book_service")
        ])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        
        await callback.message.edit_text(
            f"Выберите время на {format_date(datetime.combine(selected_date, datetime.min.time()))}:",
            reply_markup=keyboard
        )
        await state.set_state(BookingStates.selecting_time)
        
    elif data.startswith("calendar_prev_"):
        # Предыдущий месяц
        _, _, year, month = data.split("_")
        year, month = int(year), int(month)
        if month == 1:
            month = 12
            year -= 1
        else:
            month -= 1
        keyboard = await _generate_calendar(year, month)
        await callback.message.edit_reply_markup(reply_markup=keyboard)
        
    elif data.startswith("calendar_next_"):
        # Следующий месяц
        _, _, year, month = data.split("_")
        year, month = int(year), int(month)
        if month == 12:
            month = 1
            year += 1
        else:
            month += 1
        keyboard = await _generate_calendar(year, month)
        await callback.message.edit_reply_markup(reply_markup=keyboard)
        
    else:
        await callback.answer()

@router.callback_query(F.data.startswith("select_time_"), StateFilter(BookingStates.selecting_time))
async def confirm_booking(callback: CallbackQuery, state: FSMContext):
    """Подтверждение записи"""
    time_str = callback.data.replace("select_time_", "")
    appointment_datetime = datetime.strptime(time_str, "%Y-%m-%d %H:%M")
    
    data = await state.get_data()
    service_id = data.get('service_id')
    
    if not service_id:
        await callback.answer("Ошибка: услуга не выбрана", show_alert=True)
        return
    
    service = await ServiceService.get_service(service_id)
    if not service:
        await callback.answer("Услуга не найдена", show_alert=True)
        return
    
    # Проверяем доступность времени
    if not await ScheduleService.is_date_available(appointment_datetime, service.duration_minutes):
        await callback.answer("Это время уже занято", show_alert=True)
        return
    
    # Сохраняем выбранное время
    await state.update_data(appointment_datetime=time_str)
    
    # Формируем информацию о записи с учетом дополнительных услуг
    data = await state.get_data()
    selected_additional = data.get('selected_additional_services', [])
    
    total_price = service.price
    total_duration = service.duration_minutes
    
    booking_info = (
        f"📋 <b>Подтверждение записи</b>\n\n"
        f"<b>Основная услуга:</b> {service.name}\n"
    )
    
    if selected_additional:
        booking_info += "\n<b>Дополнительные услуги:</b>\n"
        for add_id in selected_additional:
            add_service = await ServiceService.get_service(add_id)
            if add_service:
                booking_info += f"  ➕ {add_service.name} - {add_service.price:.0f} ₽\n"
                total_price += add_service.price
                total_duration += add_service.duration_minutes
    
    booking_info += (
        f"\nДата: {format_date(appointment_datetime)}\n"
        f"Время: {format_datetime(appointment_datetime, '%H:%M')}\n"
        f"Длительность: {total_duration} минут\n"
        f"<b>Стоимость: {total_price:.0f} ₽</b>\n\n"
        f"Подтвердите запись:"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить", callback_data="confirm_booking_final")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="book_service")]
    ])
    
    await callback.message.edit_text(booking_info, reply_markup=keyboard, parse_mode='HTML')
    await state.set_state(BookingStates.waiting_for_confirmation)

@router.callback_query(F.data.startswith("add_additional_service_"), StateFilter(BookingStates.selecting_additional_services))
async def add_additional_service(callback: CallbackQuery, state: FSMContext):
    """Добавление дополнительной услуги"""
    additional_service_id = int(callback.data.split("_")[-1])
    data = await state.get_data()
    
    selected_additional = data.get('selected_additional_services', [])
    if additional_service_id not in selected_additional:
        selected_additional.append(additional_service_id)
        await state.update_data(selected_additional_services=selected_additional)
        await callback.answer(f"✅ Услуга добавлена!")
    else:
        # Удаляем если уже добавлена
        selected_additional.remove(additional_service_id)
        await state.update_data(selected_additional_services=selected_additional)
        await callback.answer(f"❌ Услуга удалена!")
    
    # Обновляем интерфейс
    service_id = data.get('service_id')
    service = await ServiceService.get_service(service_id)
    
    additional_services = await db.fetch("""
        SELECT s.* 
        FROM services s
        LEFT JOIN services_additional_links sal ON s.id = sal.additional_service_id
        WHERE s.is_active = TRUE 
        AND s.is_additional = TRUE
        AND (sal.main_service_id = $1 OR sal.main_service_id IS NULL)
    """, service_id)
    
    total_price = service.price
    text = (
        f"<b>{service.name}</b>\n\n"
        f"💵 Цена: {service.price:.0f} ₽\n"
        f"⏱ Длительность: {service.duration_minutes} минут\n"
    )
    
    if service.description:
        text += f"\n{service.description}\n"
    
    text += "\n\nВыберите дополнительные услуги (необязательно):"
    
    if selected_additional:
        text += "\n\n<b>Выбрано:</b>\n"
        for add_id in selected_additional:
            add_service = await ServiceService.get_service(add_id)
            if add_service:
                text += f"  ✅ {add_service.name} - {add_service.price:.0f} ₽\n"
                total_price += add_service.price
        text += f"\n<b>Итого: {total_price:.0f} ₽</b>"
    
    keyboard_buttons = []
    for add_service in additional_services:
        is_selected = "✅" if add_service['id'] in selected_additional else "➕"
        keyboard_buttons.append([
            InlineKeyboardButton(
                text=f"{is_selected} {add_service['name']} (+{add_service['price']:.0f} ₽)",
                callback_data=f"add_additional_service_{add_service['id']}"
            )
        ])
    
    keyboard_buttons.append([
        InlineKeyboardButton(text="✅ Перейти к выбору даты", callback_data="continue_to_date")
    ])
    keyboard_buttons.append([
        InlineKeyboardButton(text="🔙 Назад", callback_data="book_service")
    ])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode='HTML')


@router.callback_query(F.data == "continue_to_date", StateFilter(BookingStates.selecting_additional_services))
async def continue_to_date(callback: CallbackQuery, state: FSMContext):
    """Перейти к выбору даты после выбора дополнительных услуг"""
    data = await state.get_data()
    service_id = data.get('service_id')
    service = await ServiceService.get_service(service_id)
    
    # Формируем информацию об услуге
    service_info = (
        f"<b>{service.name}</b>\n\n"
        f"💵 Цена: {service.price:.0f} ₽\n"
        f"⏱ Длительность: {service.duration_minutes} минут\n"
    )
    
    if service.description:
        service_info += f"\n{service.description}\n"
    
    # Показываем выбранные дополнительные услуги
    selected_additional = data.get('selected_additional_services', [])
    if selected_additional:
        service_info += "\n<b>Дополнительные услуги:</b>\n"
        total_price = service.price
        for add_id in selected_additional:
            add_service = await ServiceService.get_service(add_id)
            if add_service:
                service_info += f"  ➕ {add_service.name} - {add_service.price:.0f} ₽\n"
                total_price += add_service.price
        service_info += f"\n<b>Итого: {total_price:.0f} ₽</b>\n"
    
    service_info += "\nВыберите дату:"
    
    # Показываем календарь на текущий месяц
    current_date = get_current_datetime_in_master_tz()
    keyboard = await _generate_calendar(current_date.year, current_date.month)
    
    await callback.message.edit_text(service_info, reply_markup=keyboard, parse_mode='HTML')
    await state.set_state(BookingStates.selecting_date)

@router.callback_query(F.data == "confirm_booking_final", StateFilter(BookingStates.waiting_for_confirmation))
async def create_booking(callback: CallbackQuery, state: FSMContext):
    """Создание записи"""
    data = await state.get_data()
    service_id = data.get('service_id')
    time_str = data.get('appointment_datetime')
    
    if not service_id or not time_str:
        await callback.answer("Ошибка при создании записи", show_alert=True)
        return
    
    appointment_datetime = datetime.strptime(time_str, "%Y-%m-%d %H:%M")
    
    # Получаем пользователя
    user = await UserService.get_or_create_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.username,
        full_name=callback.from_user.full_name
    )
    
    # Получаем ID клиента из таблицы clients
    client_row = await db.fetchrow("SELECT id FROM clients WHERE user_id = $1", user.id)
    if not client_row:
        # Создаем запись в clients
        client_id = await db.fetchval(
            "INSERT INTO clients (user_id) VALUES ($1) RETURNING id",
            user.id
        )
    else:
        client_id = client_row['id']
    
    # Получаем выбранные дополнительные услуги
    selected_additional = data.get('selected_additional_services', [])
    
    # Создаем запись
    try:
        appointment = await AppointmentService.create_appointment(
            client_id=user.id,  # Используем user.id, так как в appointments ссылка на users
            service_id=service_id,
            appointment_date=appointment_datetime,
            additional_service_ids=selected_additional
        )
        
        # Получаем настройки подтверждения
        settings = await BotSettingsService.get_appointment_settings()
        if settings['require_confirmation']:
            await AppointmentService.update_appointment(appointment.id, status='pending')
            status_text = "⏳ Ожидает подтверждения мастера"
        else:
            await AppointmentService.update_appointment(appointment.id, status='confirmed')
            status_text = "✅ Запись подтверждена"
        
        # Создаем напоминания
        from services.reminder_service import ReminderService
        await ReminderService.schedule_reminders_for_appointment(appointment.id, appointment_datetime)
        
        # Формируем отчет для клиента
        service = await ServiceService.get_service(service_id)
        info_sections = await InfoService.get_all_info_sections()
        address_info = next((s for s in info_sections if s['key'] == 'address'), None)
        contacts_info = next((s for s in info_sections if s['key'] == 'contacts'), None)
        
        # Получаем дополнительные услуги из записи
        additional_services = await db.fetch("""
            SELECT s.name, s.price
            FROM appointment_additional_services aas
            JOIN services s ON aas.service_id = s.id
            WHERE aas.appointment_id = $1
        """, appointment.id)
        
        report = (
            f"✅ <b>Запись успешно создана!</b>\n\n"
            f"Услуга: {service.name}\n"
        )
        
        if additional_services:
            report += "\n<b>Дополнительные услуги:</b>\n"
            for add_service in additional_services:
                report += f"  ➕ {add_service['name']} - {add_service['price']:.0f} ₽\n"
        
        report += (
            f"\nДата: {format_date(appointment_datetime)}\n"
            f"Время: {format_datetime(appointment_datetime, '%H:%M')}\n"
            f"Длительность: {appointment.total_duration} минут\n"
            f"Стоимость: {appointment.total_price:.0f} ₽\n"
            f"Статус: {status_text}\n\n"
        )
        
        if address_info and address_info.get('content'):
            report += f"📍 Адрес: {address_info['content']}\n"
        
        if contacts_info and contacts_info.get('content'):
            report += f"📞 Контакты: {contacts_info['content']}\n"
        
        await callback.message.edit_text(report, parse_mode='HTML')
        
        # Уведомляем мастера
        from services.notification_service import notify_master_new_booking
        await notify_master_new_booking(appointment, callback.bot)
        
        await state.clear()
        await callback.answer("Запись создана!")
        
    except Exception as e:
        await callback.answer(f"Ошибка: {str(e)}", show_alert=True)
        import logging
        logging.exception(f"Ошибка при создании записи: {e}")

@router.callback_query(F.data == "my_appointments")
async def show_my_appointments(callback: CallbackQuery):
    """Показать записи клиента"""
    user = await UserService.get_or_create_user(
        telegram_id=callback.from_user.id
    )
    
    appointments = await AppointmentService.get_client_appointments(user.id, only_active=True)
    
    if not appointments:
        await callback.message.edit_text("У вас нет активных записей")
        return
    
    text = "📋 <b>Ваши записи:</b>\n\n"
    
    keyboard_buttons = []
    for appointment in appointments:
        info = await AppointmentService.format_appointment_info(appointment)
        text += info + "\n\n"
        
        keyboard_buttons.append([
            InlineKeyboardButton(
                text=f"✏️ Редактировать запись #{appointment.id}",
                callback_data=f"edit_appointment_{appointment.id}"
            )
        ])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons + [
        [InlineKeyboardButton(text="🔙 Главное меню", callback_data="back_to_start")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode='HTML')

@router.callback_query(F.data.regexp(r"^edit_appointment_\d+$"))
async def edit_appointment(callback: CallbackQuery, state: FSMContext):
    """Редактирование записи"""
    appointment_id = int(callback.data.split("_")[-1])
    appointment = await AppointmentService.get_appointment(appointment_id)
    
    if not appointment:
        await callback.answer("Запись не найдена", show_alert=True)
        return
    
    # Проверяем, что это запись текущего пользователя
    user = await UserService.get_or_create_user(telegram_id=callback.from_user.id)
    if appointment.client_id != user.id:
        await callback.answer("❌ Это не ваша запись", show_alert=True)
        return
    
    # Сохраняем ID записи
    await state.update_data(appointment_id=appointment_id)
    
    # Показываем текущую информацию о записи
    appointment_info = await AppointmentService.format_appointment_info(appointment)
    
    text = (
        f"✏️ <b>Редактирование записи #{appointment_id}</b>\n\n"
        f"{appointment_info}\n\n"
        f"⚠️ <i>Внимание: мастер проверит изменения и подтвердит их</i>\n\n"
        f"Что хотите изменить?"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 Изменить дату/время", callback_data=f"edit_appointment_time_{appointment_id}")],
        [InlineKeyboardButton(text="🔧 Изменить услугу", callback_data=f"edit_appointment_service_{appointment_id}")],
        [InlineKeyboardButton(text="❌ Отменить запись", callback_data=f"cancel_appointment_{appointment_id}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="my_appointments")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode='HTML')
    await state.set_state(BookingStates.editing_appointment)

@router.callback_query(F.data.startswith("edit_appointment_time_"), StateFilter(BookingStates.editing_appointment))
async def edit_appointment_time(callback: CallbackQuery, state: FSMContext):
    """Редактирование даты и времени записи клиентом"""
    appointment_id = int(callback.data.split("_")[-1])
    appointment = await AppointmentService.get_appointment(appointment_id)
    
    if not appointment:
        await callback.answer("Запись не найдена", show_alert=True)
        return
    
    # Проверяем, что это запись текущего пользователя
    user = await UserService.get_or_create_user(telegram_id=callback.from_user.id)
    if appointment.client_id != user.id:
        await callback.answer("❌ Это не ваша запись", show_alert=True)
        return
    
    await state.update_data(appointment_id=appointment_id)
    
    text = (
        f"📅 <b>Изменение даты и времени записи #{appointment_id}</b>\n\n"
        f"Текущая дата и время: {format_datetime(appointment.appointment_date)}\n\n"
        f"Выберите новую дату:"
    )
    
    # Показываем календарь
    current_date = get_current_datetime_in_master_tz()
    keyboard = await _generate_calendar(current_date.year, current_date.month)
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode='HTML')
    await state.set_state(BookingStates.editing_appointment_date)

@router.callback_query(F.data.startswith("calendar_date_"), StateFilter(BookingStates.editing_appointment_date))
async def edit_appointment_select_date(callback: CallbackQuery, state: FSMContext):
    """Выбор новой даты при редактировании записи"""
    _, _, year, month, day = callback.data.split("_")
    selected_date = date(int(year), int(month), int(day))
    
    data = await state.get_data()
    appointment_id = data.get('appointment_id')
    
    if not appointment_id:
        await callback.answer("Ошибка: запись не найдена", show_alert=True)
        return
    
    appointment = await AppointmentService.get_appointment(appointment_id)
    service = await ServiceService.get_service(appointment.service_id)
    
    # Получаем доступные слоты времени
    existing_appointments = await db.fetch("""
        SELECT appointment_date FROM appointments
        WHERE DATE(appointment_date) = $1
        AND id != $2
        AND status IN ('pending', 'confirmed')
    """, selected_date, appointment_id)
    
    existing_times = [row['appointment_date'] for row in existing_appointments]
    slots = await ScheduleService.get_available_slots(
        selected_date,
        service.duration_minutes,
        existing_times
    )
    
    if not slots:
        await callback.answer("На эту дату нет свободного времени", show_alert=True)
        return
    
    # Показываем доступные временные слоты
    keyboard_buttons = []
    for slot in slots[:20]:
        keyboard_buttons.append([
            InlineKeyboardButton(
                text=format_datetime(slot, "%H:%M"),
                callback_data=f"edit_appointment_select_time_{slot.strftime('%Y-%m-%d %H:%M')}"
            )
        ])
    
    keyboard_buttons.append([
        InlineKeyboardButton(text="🔙 Назад", callback_data=f"edit_appointment_{appointment_id}")
    ])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    
    await callback.message.edit_text(
        f"Выберите новое время на {format_date(datetime.combine(selected_date, datetime.min.time()))}:",
        reply_markup=keyboard
    )

@router.callback_query(F.data.startswith("edit_appointment_select_time_"))
async def edit_appointment_confirm_time(callback: CallbackQuery, state: FSMContext):
    """Подтверждение нового времени записи"""
    time_str = callback.data.replace("edit_appointment_select_time_", "")
    new_datetime = datetime.strptime(time_str, "%Y-%m-%d %H:%M")
    
    data = await state.get_data()
    appointment_id = data.get('appointment_id')
    
    appointment = await AppointmentService.get_appointment(appointment_id)
    if not appointment:
        await callback.answer("Запись не найдена", show_alert=True)
        return
    
    # Обновляем запись
    try:
        await AppointmentService.update_appointment(appointment_id, appointment_date=new_datetime)
        
        # Уведомляем мастера
        from services.notification_service import notify_master_appointment_changed
        await notify_master_appointment_changed(appointment, "date_changed", callback.bot)
        
        await callback.answer("✅ Запись обновлена! Мастер уведомлен.")
        await state.clear()
        
        # Возвращаемся к списку записей
        await show_my_appointments(callback)
    except Exception as e:
        await callback.answer(f"Ошибка: {str(e)}", show_alert=True)

@router.callback_query(F.data.startswith("edit_appointment_service_"), StateFilter(BookingStates.editing_appointment))
async def edit_appointment_service(callback: CallbackQuery, state: FSMContext):
    """Редактирование услуги записи клиентом"""
    appointment_id = int(callback.data.split("_")[-1])
    appointment = await AppointmentService.get_appointment(appointment_id)
    
    if not appointment:
        await callback.answer("Запись не найдена", show_alert=True)
        return
    
    # Проверяем, что это запись текущего пользователя
    user = await UserService.get_or_create_user(telegram_id=callback.from_user.id)
    if appointment.client_id != user.id:
        await callback.answer("❌ Это не ваша запись", show_alert=True)
        return
    
    services = await ServiceService.get_all_services(only_active=True, only_main=True)
    
    keyboard_buttons = []
    for service in services:
        keyboard_buttons.append([
            InlineKeyboardButton(
                text=f"{service.name} - {service.price:.0f} ₽",
                callback_data=f"edit_appointment_set_service_{appointment_id}_{service.id}"
            )
        ])
    
    keyboard_buttons.append([
        InlineKeyboardButton(text="🔙 Назад", callback_data=f"edit_appointment_{appointment_id}")
    ])
    
    text = (
        f"🔧 <b>Изменение услуги записи #{appointment_id}</b>\n\n"
        f"Выберите новую услугу:"
    )
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_buttons), parse_mode='HTML')
    await state.set_state(BookingStates.editing_appointment_service)

@router.callback_query(F.data.startswith("edit_appointment_set_service_"))
async def edit_appointment_confirm_service(callback: CallbackQuery, state: FSMContext):
    """Подтверждение новой услуги записи"""
    parts = callback.data.split("_")
    appointment_id = int(parts[-2])
    service_id = int(parts[-1])
    
    appointment = await AppointmentService.get_appointment(appointment_id)
    if not appointment:
        await callback.answer("Запись не найдена", show_alert=True)
        return
    
    # Проверяем, что это запись текущего пользователя
    user = await UserService.get_or_create_user(telegram_id=callback.from_user.id)
    if appointment.client_id != user.id:
        await callback.answer("❌ Это не ваша запись", show_alert=True)
        return
    
    try:
        await AppointmentService.update_appointment(appointment_id, service_id=service_id)
        
        # Уведомляем мастера
        from services.notification_service import notify_master_appointment_changed
        await notify_master_appointment_changed(appointment, "service_changed", callback.bot)
        
        await callback.answer("✅ Услуга обновлена! Мастер уведомлен.")
        await state.clear()
        
        # Возвращаемся к списку записей
        await show_my_appointments(callback)
    except Exception as e:
        await callback.answer(f"Ошибка: {str(e)}", show_alert=True)

@router.callback_query(F.data.startswith("cancel_appointment_"))
async def cancel_appointment(callback: CallbackQuery):
    """Отмена записи клиентом"""
    appointment_id = int(callback.data.split("_")[-1])
    appointment = await AppointmentService.get_appointment(appointment_id)
    
    if not appointment:
        await callback.answer("Запись не найдена", show_alert=True)
        return
    
    # Проверяем, что это запись текущего пользователя
    user = await UserService.get_or_create_user(telegram_id=callback.from_user.id)
    if appointment.client_id != user.id:
        await callback.answer("❌ Это не ваша запись", show_alert=True)
        return
    
    try:
        await AppointmentService.update_appointment(appointment_id, status='cancelled')
        
        # Уведомляем мастера
        from services.notification_service import notify_master_appointment_changed
        await notify_master_appointment_changed(appointment, "cancelled", callback.bot)
        
        await callback.answer("✅ Запись отменена. Мастер уведомлен.")
        
        # Возвращаемся к списку записей
        await show_my_appointments(callback)
    except Exception as e:
        await callback.answer(f"Ошибка: {str(e)}", show_alert=True)

@router.callback_query(F.data == "info")
async def show_info(callback: CallbackQuery):
    """Показать информационные разделы"""
    sections = await InfoService.get_all_info_sections()
    
    if not sections:
        await callback.answer("Информация пока не добавлена", show_alert=True)
        return
    
    keyboard_buttons = []
    for section in sections:
        if section.get('content'):
            keyboard_buttons.append([
                InlineKeyboardButton(
                    text=section['title'],
                    callback_data=f"info_{section['key']}"
                )
            ])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons + [
        [InlineKeyboardButton(text="🔙 Главное меню", callback_data="back_to_start")]
    ])
    
    await callback.message.edit_text("ℹ️ <b>Информация</b>", reply_markup=keyboard, parse_mode='HTML')

@router.callback_query(F.data.startswith("info_"))
async def show_info_section(callback: CallbackQuery):
    """Показать конкретный информационный раздел"""
    section_key = callback.data.replace("info_", "")
    section = await InfoService.get_info_section(section_key)
    
    if not section or not section.get('content'):
        await callback.answer("Информация не найдена", show_alert=True)
        return
    
    text = f"<b>{section['title']}</b>\n\n{section['content']}"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="info")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode='HTML')

@router.callback_query(F.data == "faq")
async def show_faq(callback: CallbackQuery):
    """Показать FAQ"""
    faq_list = await InfoService.get_faq()
    
    if not faq_list:
        await callback.answer("FAQ пока не добавлены", show_alert=True)
        return
    
    text = "❓ <b>Частые вопросы:</b>\n\n"
    
    for item in faq_list:
        text += f"<b>Q: {item['question']}</b>\n"
        text += f"A: {item['answer']}\n\n"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Главное меню", callback_data="back_to_start")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode='HTML')

@router.callback_query(F.data == "contact_master")
async def contact_master(callback: CallbackQuery):
    """Связаться с мастером"""
    from config import ADMIN_ID
    
    text = (
        "📞 <b>Связаться с мастером</b>\n\n"
        "Вы можете написать мастеру в личные сообщения или использовать кнопку ниже:"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Написать мастеру", url=f"tg://user?id={ADMIN_ID}")],
        [InlineKeyboardButton(text="🔙 Главное меню", callback_data="back_to_start")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode='HTML')

@router.callback_query(F.data == "back_to_start")
async def back_to_start(callback: CallbackQuery, state: FSMContext):
    """Вернуться в главное меню"""
    await state.clear()
    
    # Получаем приветственное сообщение
    welcome_text = await BotSettingsService.get_setting(
        'welcome_message',
        '👋 Добро пожаловать! Я помогу вам записаться на услугу.'
    )
    
    # Главное меню
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 Записаться", callback_data="book_service")],
        [InlineKeyboardButton(text="📋 Мои записи", callback_data="my_appointments")],
        [InlineKeyboardButton(text="ℹ️ Информация", callback_data="info")],
        [InlineKeyboardButton(text="❓ Частые вопросы", callback_data="faq")],
        [InlineKeyboardButton(text="📞 Связаться с мастером", callback_data="contact_master")]
    ])
    
    await callback.message.edit_text(welcome_text, reply_markup=keyboard)

@router.callback_query(F.data.startswith("confirm_attendance_"))
async def confirm_attendance(callback: CallbackQuery):
    """Подтверждение клиентом, что он придет"""
    appointment_id = int(callback.data.split("_")[-1])
    appointment = await AppointmentService.get_appointment(appointment_id)
    
    if not appointment:
        await callback.answer("Запись не найдена", show_alert=True)
        return
    
    # Уведомляем мастера
    from config import ADMIN_ID
    client_user = await db.fetchrow("SELECT full_name FROM users WHERE id = $1", appointment.client_id)
    client_name = client_user['full_name'] if client_user else "Клиент"
    
    try:
        await callback.bot.send_message(
            ADMIN_ID,
            f"✅ Клиент {client_name} подтвердил, что придет на запись {format_datetime(appointment.appointment_date)}"
        )
    except:
        pass
    
    await callback.answer("Спасибо! Мастер уведомлен.")
    await callback.message.edit_text(
        callback.message.text + "\n\n✅ Подтверждено! Мастер уведомлен."
    )
