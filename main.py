import os
import telebot
from telebot import types
from dotenv import load_dotenv
from datetime import datetime, timedelta
import threading
import time
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

load_dotenv()

bot_token = os.getenv("token")
bot = telebot.TeleBot(bot_token)
bot_info = bot.get_me()
bot_username = bot_info.username.lower()  # Always compare lowercase

# Store reminders as {chat_id: {user_id: [reminder, ...]}}
user_reminders = {}

# Temporary state to track users who need to enter a task
waiting_for_task = {}


@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    bot.reply_to(
        message,
        "Hello, this is a reminder bot that makes things unforgettable for you. You can add reminders by using the command /reminder.",
        reply_to_message_id=message.message_id
    )


@bot.message_handler(commands=['reminder'])
def handle_reminder(message):
    parts = message.text.split(' ', 1)
    # If user typed only /reminder or /reminder @botusername
    if len(parts) == 1 or (
        parts[1].strip().lower() == f"@{bot_username}"
    ):
        waiting_for_task[message.from_user.id] = message
        bot.send_message(
            message.chat.id,
            "What task do you want to be reminded of?",
            reply_to_message_id=message.message_id
        )
        bot.register_next_step_handler(message, receive_task)
        return

    # ...existing code for normal /reminder flow...
    reminder_text = parts[1].strip()
    if reminder_text.lower().startswith(f"@{bot_username}"):
        reminder_text = reminder_text[len(bot_username)+2:].strip()
    user_reminders[message.chat.id] = user_reminders.get(message.chat.id, {})

    # Tag logic: never tag the bot, always tag the real user
    if (
        not message.from_user.is_bot and
        message.from_user.username and
        message.from_user.username.lower() != bot_username
    ):
        user_tag = f"@{message.from_user.username}"
    elif not message.from_user.is_bot:
        user_tag = message.from_user.first_name
    else:
        user_tag = ""  # Don't tag if it's a bot or the bot itself

    user_reminders[message.chat.id][message.from_user.id] = user_reminders[message.chat.id].get(
        message.from_user.id, [])
    user_reminders[message.chat.id][message.from_user.id].append({
        'text': reminder_text,
        'date': None,
        'time': None,
        'sent': False,
        'message_id': message.message_id,
        'user_tag': user_tag,
        'user_id': message.from_user.id  # Add this line
    })

    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("Today", callback_data="date_today"))
    markup.add(InlineKeyboardButton("Tomorrow", callback_data="date_tomorrow"))
    markup.add(InlineKeyboardButton("Pick a date", callback_data="date_pick"))
    bot.send_message(
        message.chat.id,
        "Please select a date for your reminder:",
        reply_markup=markup,
        reply_to_message_id=message.message_id
    )


def receive_task(message):
    # Only proceed if we were waiting for this user's task
    if message.from_user.id not in waiting_for_task:
        return
    original_message = waiting_for_task.pop(message.from_user.id)
    reminder_text = message.text.strip()
    chat_id = message.chat.id

    user_reminders[chat_id] = user_reminders.get(chat_id, {})
    user_reminders[chat_id][message.from_user.id] = user_reminders[chat_id].get(
        message.from_user.id, [])

    # Tag logic: never tag the bot, always tag the real user
    if (
        not message.from_user.is_bot and
        message.from_user.username and
        message.from_user.username.lower() != bot_username
    ):
        user_tag = f"@{message.from_user.username}"
    elif not message.from_user.is_bot:
        user_tag = message.from_user.first_name
    else:
        user_tag = ""  # Don't tag if it's a bot or the bot itself

    user_reminders[chat_id][message.from_user.id].append({
        'text': reminder_text,
        'date': None,
        'time': None,
        'sent': False,
        'message_id': original_message.message_id,
        'user_tag': user_tag,
        'user_id': message.from_user.id
    })

    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("Today", callback_data="date_today"))
    markup.add(InlineKeyboardButton("Tomorrow", callback_data="date_tomorrow"))
    markup.add(InlineKeyboardButton("Pick a date", callback_data="date_pick"))
    bot.send_message(
        chat_id,
        "Please select a date for your reminder:",
        reply_markup=markup,
        reply_to_message_id=original_message.message_id
    )


def process_date_selection(message):
    reminders = user_reminders.get(
        message.chat.id, {}).get(message.from_user.id, [])
    if not reminders:
        bot.send_message(
            message.chat.id,
            "No reminder found. Please use /reminder command again.",
            reply_to_message_id=message.message_id
        )
        return
    reminder = reminders[-1]
    # Only allow the original user to continue the flow
    if message.from_user.id != reminder.get('user_id'):
        bot.send_message(
            message.chat.id,
            "Only the user who started the reminder can continue this flow.",
            reply_to_message_id=message.message_id
        )
        return

    selected_date = message.text

    if selected_date == "Today":
        date_str = datetime.now().strftime("%Y-%m-%d")
    elif selected_date == "Tomorrow":
        date_str = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    elif selected_date == "Pick a date":
        msg = bot.send_message(
            message.chat.id,
            "Please enter the date in YYYY-MM-DD format:",
            reply_to_message_id=message.message_id
        )
        bot.register_next_step_handler(
            msg, lambda m: process_custom_date(m, reminder))
        return
    else:
        date_str = selected_date  # fallback

    reminder['date'] = date_str
    ask_for_time(message, reminder)


def process_custom_date(message, reminder):
    date_str = message.text
    # Optionally, validate the date format here
    reminder['date'] = date_str
    ask_for_time(message, reminder)


def ask_for_time(message, reminder):
    msg = bot.send_message(
        message.chat.id,
        "Please enter the time for your reminder in HH:MM (24-hour) format:",
        reply_to_message_id=message.message_id
    )
    bot.register_next_step_handler(msg, lambda m: process_time(m, reminder))


def process_time(message, reminder):
    time_str = message.text
    # Optionally, validate the time format here
    reminder['time'] = time_str
    bot.send_message(
        message.chat.id,
        f"Command set for date: {reminder['date']} at {reminder['time']}\nReminder: {reminder['text']}",
        reply_markup=types.ReplyKeyboardRemove(),
        reply_to_message_id=message.message_id
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("date_"))
def handle_date_callback(call):
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    reminders = user_reminders.get(chat_id, {}).get(user_id, [])
    if not reminders:
        bot.answer_callback_query(call.id, "No reminder found.")
        return
    reminder = reminders[-1]
    # Only allow the original user to continue the flow
    if call.from_user.id != reminder.get('user_id'):
        bot.answer_callback_query(
            call.id, "Only the user who started the reminder can continue this flow.")
        return

    if call.data == "date_today":
        date_str = datetime.now().strftime("%Y-%m-%d")
    elif call.data == "date_tomorrow":
        date_str = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    elif call.data == "date_pick":
        msg = bot.send_message(
            call.message.chat.id,
            "Please enter the date in YYYY-MM-DD format:",
            reply_to_message_id=call.message.message_id
        )
        bot.register_next_step_handler(
            msg, lambda m: process_custom_date(m, reminder))
        bot.answer_callback_query(call.id)
        return
    else:
        date_str = ""

    reminder['date'] = date_str
    bot.answer_callback_query(call.id)
    ask_for_time(call.message, reminder)


def reminder_checker():
    while True:
        now = datetime.now()
        for chat_id, user_dict in list(user_reminders.items()):
            for user_id, reminders in user_dict.items():
                for reminder in reminders:
                    if reminder['sent']:
                        continue
                    if reminder['date'] and reminder['time']:
                        try:
                            reminder_dt = datetime.strptime(
                                f"{reminder['date']} {reminder['time']}", "%Y-%m-%d %H:%M")
                            if now >= reminder_dt:
                                user_tag = reminder.get('user_tag', '')
                                bot.send_message(
                                    chat_id,
                                    f"⏰ Reminder: {reminder['text']} {user_tag}",
                                    reply_to_message_id=reminder.get(
                                        'message_id')
                                )
                                reminder['sent'] = True
                        except Exception:
                            continue
        time.sleep(30)  # Check every 30 seconds


# Start the reminder checker in a background thread
threading.Thread(target=reminder_checker, daemon=True).start()

bot.infinity_polling()
