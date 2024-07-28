#!/usr/bin/env python
# pylint: disable=unused-argument
# This program is dedicated to the public domain under the CC0 license.

"""
Basic example for a bot that uses inline keyboards. For an in-depth explanation, check out
 https://github.com/python-telegram-bot/python-telegram-bot/wiki/InlineKeyboard-Example.
"""
from datetime import date #, time

import logging
import configparser
import json

from telegram import InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
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
comp_matrix = get_om_list('Области экспертизы для бота')
users_df = get_om_mc('ML Users')

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.DEBUG,
    filename='basic.log'
)
# set higher logging level for httpx to avoid all GET and POST requests being logged
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.INFO)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.INFO)


logger = logging.getLogger(__name__)


def get_user_df(df, user_id):
    '''get_user_df'''
    try:
        df = df[df.Telegram_id == str(user_id)]
    except AttributeError:
        df = get_om_mc('ML Users')
        df = df[df.Telegram_id == str(user_id)]
    return df


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a message with three inline buttons attached."""
    user = '@' + update.effective_user.username
    user_id = update.effective_user.id
    req = get_chat_member(user_id)
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
        #logger.debug("get_om_mc('ML Users')")
        users_df = get_om_mc('ML Users')
        user_df = users_df[users_df.Telegram_id == str(update.effective_user.id)]
        #user_df = get_user_df(users_df, user_id)
        om_user = user_df['Почта']
        #check if user had already connected before
        if not om_user.empty:
            #check if user had mentors today
            #sends a competention quiz
            if user_df['Нет оценки'].item() == "1":
                await update.message.reply_text(
                f"{user}, прежде, чем подобрать нового эксперта, необходимо оценить работу ментора по предыдущему обращению 🧐")
                await assess_mentor(update, context)
            else:
                day = date.today().strftime("%d %b %y")
                om_filter = f"ITEM(Users) = Users.{om_user.item()} AND ITEM(Days) = Days.{day}"
                #global assessment_df
                logger.debug("get_om_mc('Удовлетворенность ментором'), filter: %s", om_filter)
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


async def edit_query_message(query, msg):
    '''edit_query_message'''
    await query.edit_message_text(text=msg)


async def compententions_quiz(query, answer_list, tg_username, om_grade):
    '''compententions_quiz'''
    code = answer_list[1]
    if code == 'back':
        keyboard = make_buttons(comp_matrix)
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_reply_markup(reply_markup=reply_markup)
    else:
        answer = comp_matrix[comp_matrix['Code'] == code]['Entity'].item()
        logger.debug('Comp answer is %s, code is %s', answer, code)
        if not comp_matrix[comp_matrix.Parent == answer].empty:
            keyboard = make_buttons(comp_matrix, answer)
            reply_markup = InlineKeyboardMarkup(keyboard)
            #logger.debug('message_reply_markup \n%s', str(reply_markup))
            await query.edit_message_reply_markup(reply_markup=reply_markup)
        #if user choosed final point of quiz
        else:
            await query.edit_message_text(text=
                f'Подожди чуть-чуть, @{tg_username}, подбираю варианты по теме "{answer}"🔍')
            om_formula = f'NAME(ITEM(\'Grades\')) = "{om_grade}" AND NAME(ITEM(\'Области экспертизы для бота\')) = "{answer}"'
            logger.debug("get_om_mc('Данные для бота по ментору', formula=%s)", om_formula)
            df = get_om_mc('Данные для бота по ментору в разрезе грейдов', formula=om_formula)
            mentors = df['Данные'].item()
            mentors = json.loads(mentors.replace('\'', '"'))
            msg, kb = make_mentor_cards(mentors, code, answer)
            logger.debug("make_mentor_cards, %s", kb)
            reply_markup = InlineKeyboardMarkup(kb)
            await query.edit_message_text(text=
                msg)
            await query.edit_message_reply_markup(reply_markup=reply_markup)


async def mentors_quiz(query, answer_list, om_user):
    '''mentors_quiz'''
    dis_name = answer_list[1]
    domain = comp_matrix[comp_matrix['Code'] == answer_list[2]]['Entity'].item()
    name = users_df[users_df['discord'] == dis_name]['name'].item()
    msg = f'''Ментор по теме "{domain}" выбран - {name}!
📩 Связаться с ментором можно в Discord - {dis_name}

1. Опиши свой кейс.
2. Договорись с ментором об удобном времени для созвона 1-1. 
Вам выделяется 4 часа на решение запроса, их можно распределить как удобно.  
ФА/ТА/Этап для встречи: OT_Прочие HR активности 2024, Прочие HR активности, Наставничество.
3. После решения вопроса нужно будет оценить работу с ментором по 5-бальной шкале, где 5 - наивысшая оценка (вопрос решен полностью, взаимодйствие было комфортным). 
👉 Для оценки ментора используй команду /mentor'''
    await query.edit_message_text(text=msg)
    write_selection(om_user, name, domain)


async def assess(query, om_user, answer_list):
    '''assess'''
    assessment = answer_list[1]
    day = answer_list[2]
    await query.edit_message_text(text='❤️Спасибо за оценку!')
    keyboard = [[{'text': 'Спасибо!', 'callback_data': 'finish'}],
                [{'text': 'Найти нового ментора.', 'callback_data': 'repeat'}]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_reply_markup(reply_markup=reply_markup)
    write_assessment(om_user, day, assessment)


async def button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Parses the CallbackQuery and updates the message text."""
    query = update.callback_query
    answer = query.data
    logger.debug('Answer is %s', answer)
    # CallbackQueries need to be answered, even if no notification to the user is needed
    # Some clients may have trouble otherwise. See https://core.telegram.org/bots/api#callbackquery
    await query.answer()
    tg_username = str(update.effective_user.username)
    user_df = get_user_df(users_df, update.effective_user.id)
    om_user = user_df['Почта'].item()
    om_grade = user_df['Грейд'].item()
    answer_list = answer.split('_')
    answer_type = answer_list[0]
    #if user push final button
    if answer_type == 'finish':
        msg = '''Ciao! Взвращайся, если понадобится моя помощь.
Чтобы запустить процесс подбора ментора вновь, нажми /start'''
        await edit_query_message(query, msg)
    #if user asked to repead quiz
    elif answer_type == 'repeat':
        await edit_query_message(query, '👉Нажми /start')
    #if user choosed mentor
    elif answer_type == 'men':
        await mentors_quiz(query, answer_list, om_user)
    #if user choosed assessment for mentor
    elif answer_type == 'assess':
        await assess(query, om_user, answer_list)
    #if user choosing quiz buttons
    elif answer_type == 'comp':
        await compententions_quiz(query, answer_list, tg_username, om_grade)


async def login(update, context) -> None:
    """Check login in OM model"""
    om_user = update.message.text
    tg_id = str(update.effective_user.id)
    tg_username = str(update.effective_user.username)
    user_df = users_df[users_df['Почта'] == om_user]
    if user_df.empty:
        msg = '''Хм, в модели нет такого пользователя! 🧐
Напиши, пожалуйста, корректный адрес рабочей почты.'''
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
    '''comp_quiz'''
    message = '👉 Укажи основную область, в которой тебе потребуется помощь ментора'
    keyboard = make_buttons(comp_matrix)
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(message, reply_markup=reply_markup)


async def assess_mentor(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """assess_mentor"""
    user_df = get_user_df(users_df, update.effective_user.id)
    om_user = user_df['Почта'].item()
    om_formula = f"NAME(ITEM('Users')) = \"{om_user}\" AND 'Нет оценки' AND NOT IS_PARENT()"
    logger.debug("get_om_mc('Удовлетворенность ментором', formula=%s)", om_formula)
    assessment_df = get_om_mc(
        'Удовлетворенность ментором',
        view='4BOT',
        formula=om_formula)
    if assessment_df.empty:
        await update.message.reply_text("У вас нет неоцененных менторов")
    else:
        mentor = assessment_df['Выбранный ментор текст'].item()
        day = assessment_df['Days'].item()
        dom = assessment_df['Выбранная тема текст'].item()
        #dom = comp_matrix[comp_matrix['Code'] == code]['Entity'].item()
        message = f'''👉Оцени работу ментора {mentor} по теме {dom} по 5-бальной шкале,
где 5 - наивысшая оценка (вопрос решен полностью, взаимодйствие было комфортным), 
а 1 - вопрос не решен совсем.'''
        keyboard = [[{'text': i, 'callback_data': f"assess_{str(i)}_{day}" }] for i in range(1, 6)]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(message, reply_markup=reply_markup)


async def post_daily_message(context: ContextTypes.DEFAULT_TYPE) -> None:
    """post_daily_message"""
    om_filter = "'Нет оценки' AND NOT IS_PARENT()"
    df = get_om_mc(
        'Удовлетворенность ментором',
        view='4BOT',
        formula=om_filter)
    print(df)
    user_chat_id = 74096627
    await context.bot.send_message(
        user_chat_id,
        "Good morning, I'm on duty!",
        parse_mode=ParseMode.HTML,
    )


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
    #from pytz import timezone
    #    dt = time.dtime(hour=10, tzinfo=timezone('Europe/Moscow'))
    #dt = time.dtime(hour=10)
    #application.job_queue.run_daily(post_daily_message, dt, name='user_alert')
    # Run the bot until the user presses Ctrl-C
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
