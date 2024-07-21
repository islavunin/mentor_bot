#!/usr/bin/env python
# pylint: disable=unused-argument
# This program is dedicated to the public domain under the CC0 license.

"""
Basic example for a bot that uses inline keyboards. For an in-depth explanation, check out
 https://github.com/python-telegram-bot/python-telegram-bot/wiki/InlineKeyboard-Example.
"""
from datetime import date
import logging
import configparser
import json
import pandas as pd

from telegram import InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters
)

from bot_utils import (
    get_om_list,
    get_om_mc,
    make_buttons,
    reg_user_in_om,
    get_chat_member,
    write_selection,
    make_mentor_cards,
    write_assessment
)

config = configparser.ConfigParser()
config.read('config.ini')
TBOT_TOKEN = config.get('tgbot', 'TOKEN')

# Global variables
comp_matrix = {}
users_df = {}
mentors = {}
assessment_df = {}

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
# set higher logging level for httpx to avoid all GET and POST requests being logged
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a message with three inline buttons attached."""
    user = '@' + update.effective_user.username
    req = get_chat_member(update.effective_user.id)
    #check if user in OT chat
    if not req['ok']:
        await update.message.reply_text(
            f"Привет, {user}! Этим ботом могут пользоваться только сотрудники ОТ и ОМ, которые состоят в корпоративном чате 😉")
    elif req['result']['status'] == 'kicked':
        await update.message.reply_text(
            f"Привет, {user}! Ты был удален из корпоративного чата ГК Оптимакрос. К сожалению, ты не можешь воспользоваться ботом 😔")
    else:
        await update.message.reply_text(
                f"Привет, {user}, подожди немного 🙏🏼")
        global users_df
        users_df = get_om_mc('ML Users')
        user_df = users_df[users_df.Telegram_id == str(update.effective_user.id)]
        om_user = user_df['Почта']
        #check if user had already connected before
        if not om_user.empty:
            #sends a competention quiz
            assessment = user_df['Нет оценки'].item() == "1"
            if assessment:
                await update.message.reply_text(
                f"{user}, прежде, чем подобрать нового эксперта, необходимо оценить работу ментора по предыдущему обращению 🧐")
                await assess_mentor(update, context)
            else:
                #check if user had mentors today
                day = date.today().strftime("%d %b %y")
                om_filter = f"ITEM(Users) = Users.{om_user.item()} AND ITEM(Days) = Days.{day}"
                global assessment_df
                assessment_df = get_om_mc(
                    'Удовлетворенность ментором',
                    view='4BOT',
                    formula=om_filter)
                if assessment_df['Выбранный ментор текст'].item() != "":
                    await update.message.reply_text(
                    f"{user}, в день не больше одного ментора!")
                else:
                    await comp_quiz(update, context)
        else:
            #sends a message to register
            await register(update, context)


async def register(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a message to register."""
    # if user not in OT - All cons then "Вы не состоите в чате"
    message = '''Добро пожаловать в бота по поиску и подбору экспертов 
среди сотрудников ОптиТим и Оптимакрос.
Чтобы продолжить работу, нужно пройти короткую регистрацию!

👉Напиши свою рабочую эл. почту

Пример: i.ivanov@optiteam.ru

Также, если ты не против, мы запишем данные твоего телеграм-аккаунта в модель Human capital 
и в следующий раз бот будет узнавать тебя автоматически'''
    await update.message.reply_text(message)


async def button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Parses the CallbackQuery and updates the message text."""
    query = update.callback_query
    answer = query.data
    # CallbackQueries need to be answered, even if no notification to the user is needed
    # Some clients may have trouble otherwise. See https://core.telegram.org/bots/api#callbackquery
    await query.answer()
    global mentors
    #if mentors answer
    tg_username = str(update.effective_user.username)
    user = users_df[users_df.Telegram_id == str(update.effective_user.id)]
    om_user = user['Почта'].item()
    om_grade = user['Грейд'].item()
    #if user push final button
    if answer == 'finish':
        msg = 'Ciao! Взвращайся, если понадобится моя помощь. Чтобы запустить процесс подбора ментора вновь, нажми /start'
        await query.edit_message_text(text=msg)
    #if user asked to repead quiz
    elif answer == 'repeat':
        await query.edit_message_text(text='👉Нажми /start')
        #await comp_quiz(update=update, context=context)
    #if user choosed mentor
    elif answer[:4] == 'men_':
        mentors = pd.json_normalize(mentors)
        mentor = mentors[mentors.discord == answer[4:]]
        dis_name = mentor.discord.item()
        name = mentor.name.item()
        msg = f'''Ментор выбран - {name}!
📩 Связаться с ментором можно в Discord - {dis_name}

1. Опиши свой кейс.
2. Договорись с ментором об удобном времени для созвона 1-1. 
Вам выделяется 4 часа на решение запроса, их можно распределить как удобно.  
ФА/ТА/Этап для встречи: OT_Прочие HR активности 2024, Прочие HR активности, Наставничество.
3. После решения вопроса нужно будет оценить работу с ментором по 5-бальной шкале, где 5 - наивысшая оценка (вопрос решен полностью, взаимодйствие было комфортным). 
👉 Для оценки ментора используй команду /mentor'''
    #    message = f'''Вы выбрали эксперта {name}! Связаться c ним вы можете в дискорде {dis_name}.
    #После решения вопроса просьба оставить обратную связь с оценкой ментора.
    #Для этого используйте команду /mentor.'''
        await query.edit_message_text(text=msg)
        write_selection(om_user, name)
    #if user choosed assessment for mentor
    elif answer[:7] == 'assess_':
        assessment = answer[7:]
        day = assessment_df['Days'].item()
        await query.edit_message_text(text='❤️Спасибо за оценку!')
        keyboard = [[{'text': 'Спасибо!', 'callback_data': 'finish'}],
                    [{'text': 'Найти нового ментора.', 'callback_data': 'repeat'}]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_reply_markup(reply_markup=reply_markup)
        write_assessment(om_user, day, assessment)
    #if user choosing quiz buttons
    elif not comp_matrix[comp_matrix.Parent == answer].empty:
        keyboard = make_buttons(comp_matrix, answer)
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_reply_markup(reply_markup=reply_markup)
    #if user choosed final point of quiz
    else:
        await query.edit_message_text(text=
            f'Подожди чуть-чуть, @{tg_username}, подбираю варианты 🔍')
        #om_grade = 'Middlе старший'
        om_formula = f'NAME(ITEM(\'Grades\')) = "{om_grade}" AND NAME(ITEM(\'Области экспертизы для бота\')) = "{answer}"'
        df = get_om_mc('Данные для бота по ментору в разрезе грейдов', formula=om_formula)
        mentors = df['Данные'].item()
        #mentors = "[{'user': 'i.ivanov@optiteam.ru', 'name': 'Полунин Владислав', 'discord': 'iivanov', 'mentor_grade': 'Middle', 'skills': ['Excel', 'Word', 'Visio']},\n {'user': 'p.ivanov@optiteam.ru', 'name': 'Петр Иванов', 'discord': 'pivanov', 'mentor_grade': 'Middle', 'skills': ['Excel', 'Word', 'Visio']},\n {'user': 'i.petrov@optiteam.ru', 'name': 'Иван Петров', 'discord': 'ipetrov', 'mentor_grade': 'Middle', 'skills': ['Excel', 'Word', 'Visio']}]"
        mentors = json.loads(mentors.replace('\'', '"'))
        msg, kb = make_mentor_cards(mentors)
        reply_markup = InlineKeyboardMarkup(kb)
        await query.edit_message_text(text=
            msg)
        await query.edit_message_reply_markup(reply_markup=reply_markup)



async def login(update, context) -> None:
    """Check login in OM model"""
    om_user = update.message.text
    tg_id = str(update.effective_user.id)
    tg_username = str(update.effective_user.username)
    user_df = users_df[users_df['Почта'] == om_user]
    if user_df.empty:
        msg = 'Хм, в модели нет такого пользователя! 🧐\nНапиши, пожалуйста, корректный адрес рабочей почты.'
        await update.message.reply_text(msg)
    elif user_df.Telegram_id.item() and user_df.Telegram_id.item() != tg_id:
        #msg = f'Данный email уже указал пользователь @{user_df.Telegram_login.item()}!'
        msg = '''Хм, этот e-mail уже использован 🧐 
Напиши, пожалуйста, корректный адрес своей рабочей почты.'''
        await update.message.reply_text(msg)
    else:
        reg_user_in_om(om_user, tg_id, tg_username)
        await update.message.reply_text(
                f"Подожди чуть-чуть, {tg_username}, составляем опросник!")
        await comp_quiz(update, context)


async def comp_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    '''А'''
    message = '👉 Укажи основную область, в которой тебе потребуется помощь ментора'
    global comp_matrix
    comp_matrix = get_om_list('Области экспертизы для бота') #.iloc[:50, :]
    keyboard = make_buttons(comp_matrix, 'Все области')
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(message, reply_markup=reply_markup)


async def assess_mentor(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """assess_mentor"""
    global users_df
    try:
        user_df = users_df[users_df.Telegram_id == str(update.effective_user.id)]
    except AttributeError:
        users_df = get_om_mc('ML Users')
        user_df = users_df[users_df.Telegram_id == str(update.effective_user.id)]
    om_user = user_df['Почта'].item()
    om_filter = f"NAME(ITEM('Users')) = \"{om_user}\" AND 'Нет оценки' AND NOT IS_PARENT()"
    global assessment_df
    assessment_df = get_om_mc(
        'Удовлетворенность ментором',
        view='4BOT',
        formula=om_filter)
    if assessment_df.empty:
        await update.message.reply_text("У вас нет неоцененных менторов")
    else:
        mentor = assessment_df['Выбранный ментор текст'].item()
        message = f'''👉Оцени работу ментора {mentor} по 5-бальной шкале,
где 5 - наивысшая оценка (вопрос решен полностью, взаимодйствие было комфортным), 
а 1 - вопрос не решен совсем.'''
        keyboard = [[{'text': i, 'callback_data': "assess_" + str(i)}] for i in range(1, 6)]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(message, reply_markup=reply_markup)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays info on how to use the bot."""
    await update.message.reply_text("Use /start to test this bot.")


def main() -> None:
    """Run the bot."""
    # Create the Application and pass it your bot's token.
    application = Application.builder().token(TBOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button))
    hashtag_filter = filters.Regex('@optiteam.ru')
    application.add_handler(MessageHandler(hashtag_filter, login))
    application.add_handler(CommandHandler("mentor", assess_mentor))
    #application.add_handler(CommandHandler("help", help_command))
    # Run the bot until the user presses Ctrl-C
    application.run_polling(allowed_updates=Update.ALL_TYPES)
    #users_df


if __name__ == "__main__":
    main()
