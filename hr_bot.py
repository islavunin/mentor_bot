'''Telegram bot for Optiteam mentor activity'''

from datetime import date, time, datetime
import logging
#from logging.handlers import RotatingFileHandler
import configparser
import json
from pytz import timezone


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
    filename='basic.log',
    encoding='utf-8')

# Set rotating logger
#logger = logging.getLogger(__name__)
#logger.setLevel(logging.DEBUG)
#formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

#handler = RotatingFileHandler("basic.log",
#                              mode='a',
#                              maxBytes=1000000,
#                              backupCount=1,
#                              encoding='utf-8',
#                              delay=0)
#handler.setLevel(logging.DEBUG)
#handler.setFormatter(formatter)

#logger.addHandler(handler)

# Set higher logging level for httpx to avoid all GET and POST requests being logged
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
    logger.debug("get_chat_member, %s", req)
    #check if user in OT chat
    if not req['ok']:
        await update.message.reply_text(
            f"Привет, {user}! Этим ботом могут пользоваться только сотрудники ОТ и ОМ, которые состоят в корпоративном чате 😉")
    elif req['result']['status'] == 'kicked' or req['result']['status'] == 'left':
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
                day = date.today().strftime("%d/%m/%y")
                om_filter = f"ITEM(Users) = Users.'{om_user.item()}' AND ITEM(Days) = DAY(DATE(\"{day}\"))"
                #global assessment_df
                logger.debug("get_om_mc('Удовлетворенность ментором'), filter: %s", om_filter)
                assessment_df = get_om_mc(
                    'Удовлетворенность ментором',
                    view='4BOT',
                    formula=om_filter)
                logger.debug(assessment_df)
                if assessment_df['Выбранный ментор текст'].item() != "":
                    await update.message.reply_text(
                    f"{user}, прости, можно подобрать не более одного ментора в день!")
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


async def login(update, context) -> None:
    """Check login in OM model"""
    om_user = update.message.text
    tg_id = str(update.effective_user.id)
    tg_username = str(update.effective_user.username)
    global users_df
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
        users_df = get_om_mc('ML Users')
        await comp_quiz(update, context)


async def comp_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    '''comp_quiz'''
    message = '👉 Укажи основную область, в которой тебе потребуется помощь ментора'
    keyboard = make_buttons(comp_matrix)
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(message, reply_markup=reply_markup)


async def edit_query_message(query, msg):
    '''edit_query_message'''
    await query.edit_message_text(text=msg)


async def compententions_quiz(context, query, answer_list, tg_username, om_user, om_grade):
    '''compententions_quiz'''
    code = answer_list[1]
    if code == 'back':
        keyboard = make_buttons(comp_matrix)
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_reply_markup(reply_markup=reply_markup)
    else:
        answer = comp_matrix[comp_matrix['Code'] == code]['Entity'].item()
        payload = {
            tg_username: {
                "domain": answer,
            }
        }
        context.bot_data.update(payload)
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
            msg, kb = make_mentor_cards(om_user, mentors, code, answer)
            logger.debug("make_mentor_cards, %s", kb)
            reply_markup = InlineKeyboardMarkup(kb)
            await query.edit_message_text(text=
                msg)
            await query.edit_message_reply_markup(reply_markup=reply_markup)


async def mentors_choise(query, answer_list, om_user):
    '''mentors_choise'''
    dis_name = answer_list[1]
    domain = comp_matrix[comp_matrix['Code'] == answer_list[2]]['Entity'].item()
    if dis_name == 'own':
        msg = f'👉Напиши точный дискорд-ник ментора, к которому ты хочешь обратиться (без @) по теме {domain}'
        await query.edit_message_text(text=msg)
    else:
        name = users_df[users_df['discord'] == dis_name]['name'].item()
        msg = f'''Ментор по теме "{domain}" выбран - {name}!
📩 Связаться с ментором можно в Discord - {dis_name}

1. Опиши свой кейс.
2. Договорись с ментором об удобном времени для созвона 1-1. 
Вам выделяется 4 часа на решение запроса, их можно распределить как удобно.  
ФА/ТА/Этап для встречи: OT_Прочие HR активности 2024, Прочие HR активности, Наставничество.
3. После решения вопроса нужно будет оценить работу с ментором по 5-бальной шкале, где 5 - наивысшая оценка (вопрос решен полностью, взаимодйствие было комфортным). 
👉 Для оценки ментора используй команду /mentor
Если разобрался сам или ошибся с выбором ментора, все равно пройди в меню оценки и выбери отмену'''
        await query.edit_message_text(text=msg)
        day = date.today().strftime("%d.%m.%Y")
        write_selection(om_user, name, domain, day)


async def own_mentor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    '''own_mentor'''
    user = '@' + update.effective_user.username
    discord = update.message.text
    bot_data = context.bot_data[user[1:]]
    logging.debug("bot data %s", bot_data)
    domain = bot_data['domain']
    code = comp_matrix[comp_matrix.Entity == domain].Code.item()
    logger.debug('discord name: %s', discord)
    if users_df['discord'].isin([discord]).any():
        mentor_df = users_df[users_df['discord'] == discord]
        logger.debug('is_mentor: %s', mentor_df.is_mentor.item())
        if mentor_df.is_mentor.item() == '1':
            mentor_name = mentor_df['name'].item()
            skills = mentor_df['key_skills'].item().split(', ')
            message = f'''Я нашел ментора:
_______
🙂 {mentor_name}
Должность: {mentor_df['Грейд'].item()}
📌 Ключевые навыки: 
- {skills[0]}
- {skills[1]}
- {skills[2]}
_______
❔Если ментор тебе подходит, нажми на кнопку с именем ниже, а я подскажу тебе следующие шаги. 
❔Если хочешь начать поиск заново, нажми /start'''
            keyboard = [[{'text': mentor_name, 'callback_data': 'men_' + discord + '_' +  code }],
                        [{'text': "Начать с начала", 'callback_data': 'repeat' }]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(message, reply_markup=reply_markup)
        else:
            txt = f'''{user}, прости, этот сотрудник не является ментором. Я не могу зарегистрировать обращение к нему 😔
Если хочешь начать поиск заново, нажми /start'''
            await update.message.reply_text(txt)
    else:
        txt = '''Хм, такого пользователя не существует! 🧐 
Напиши, пожалуйста, корректный дискорд-ник.'''
        await update.message.reply_text(txt)


def get_assessment_df(user_id):
    '''get_assessment_df'''
    user_df = get_user_df(users_df, user_id)
    om_user = user_df['Почта'].item()
    om_formula = f"NAME(ITEM('Users')) = \"{om_user}\" AND 'Нет оценки' AND NOT IS_PARENT()"
    logger.debug("get_om_mc('Удовлетворенность ментором', formula=%s)", om_formula)
    assessment_df = get_om_mc(
        'Удовлетворенность ментором',
        view='4BOT',
        formula=om_formula)
    return [om_user, assessment_df]


async def assess_mentor(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """assess_mentor"""
    assessment_df = get_assessment_df(update.effective_user.id)[1]
    if assessment_df.empty:
        await update.message.reply_text("У тебя нет менторов для оценки")
    else:
        mentor = assessment_df['Выбранный ментор текст'].item()
        day = assessment_df['Days'].item()
        dom = assessment_df['Выбранная тема текст'].item()
        #dom = comp_matrix[comp_matrix['Code'] == code]['Entity'].item()
        message = f'''👉Оцени работу ментора {mentor} по теме {dom} по 5-бальной шкале,
где 5 - наивысшая оценка (вопрос решен полностью, взаимодйствие было комфортным), 
а 1 - вопрос не решен совсем.
Если разобрался сам или ошибся с выбором ментора, то выбери вариант в самом низу'''
        keyboard = [[{'text': i, 'callback_data': f"assess_{str(i)}_{day}" }] for i in range(1, 6)]
        keyboard.append([{'text': 'Разобрался сам', 'callback_data': f"cancel_{day}" }])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(message, reply_markup=reply_markup)


async def cancel_mentor(update) -> None:
    """cancel_mentor"""
    query = update.callback_query
    user_df = get_user_df(users_df, update.effective_user.id)
    om_user = user_df['Почта'].item()
    day = query.data.split("_")[1]
    day = datetime.strptime(day, "%d %b %y").strftime("%d.%m.%y")
    message = 'Выбор ментора отменен. Чтобы запустить процесс подбора ментора вновь, нажми /start'
    await query.edit_message_text(text=message)
    name, domain = '', ''
    write_selection(om_user, name, domain, day)


async def assess_time(query, answer):
    '''assess'''
    q_list = ["до 30 мин", "30 мин - 1 час", "1-2 часа", "2-3 часа", "3-4 часа"]
    answer = 'end' + answer
    message = '👉Какое время потребовалось ментору для помощи?'
    await query.edit_message_text(text=message)
    keyboard = [[{'text': q_list[i], 'callback_data': f"{answer}_{i+1}" }] for i in range(5)]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_reply_markup(reply_markup=reply_markup)


async def end_assess(query, om_user, answer_list):
    '''assess_time'''
    assessment = answer_list[1]
    day = answer_list[2]
    period = answer_list[3]
    await query.edit_message_text(text='❤️Спасибо за оценку!')
    keyboard = [[{'text': 'Спасибо!', 'callback_data': 'finish'}],
                [{'text': 'Найти нового ментора.', 'callback_data': 'repeat'}]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_reply_markup(reply_markup=reply_markup)
    write_assessment(om_user, day, assessment, period)


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
        await mentors_choise(query, answer_list, om_user)
    #if user choosed assessment for mentor
    elif answer_type == 'assess':
        await assess_time(query, answer)
    #if user choosed time assessment
    elif answer_type == 'endassess':
        await end_assess(query, om_user, answer_list)
    #if user choosed cancellation
    elif answer_type == 'cancel':
        await cancel_mentor(update)
    #if user choosing quiz buttons
    elif answer_type == 'comp':
        await compententions_quiz(context, query, answer_list, tg_username, om_user, om_grade)


async def post_daily_message(context: ContextTypes.DEFAULT_TYPE) -> None:
    """post_daily_message"""
    om_filter = "'Нет оценки' AND NOT IS_PARENT()"
    df = get_om_mc(
        'Удовлетворенность ментором',
        view='4BOT',
        formula=om_filter)
    logger.debug('Нет оценки: \n %s', df)
    if not df.empty:
        for index in df.index:
            udf = df.loc[index, :]
            logger.debug('df.row(): \n %s', udf)
            day = udf['Days']
            dtdelta = datetime.today() - datetime.strptime(day, "%d %b %y")
            if dtdelta.days >= 7:
                user_id = udf['Telegram_id']
                user = udf['Telegram_login']
                txt = f'''Привет, {user}! Не забудь оценить работу ментора по команде /mentor,
где 5 - наивысшая оценка (вопрос решен полностью, взаимодйствие было комфортным), а 1 - вопрос не решен совсем.
Если вы все еще в процессе решения кейса, напоминаю, что вам выделяется 4 часа для совместной работы, их можно распределить как удобно.  
ФА/ТА/Этап для встречи: OT_Прочие HR активности 2024, Прочие HR активности, Наставничество.
Если разобрался сам или ошибся с выбором ментора, то все равно пройди в меню оценки и выбери самый нижний вариант'''
                await context.bot.send_message(
                    user_id,
                    txt,
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
    email_filter = filters.Regex('@optiteam.ru')
    application.add_handler(MessageHandler(email_filter, login))
    discord_filter = filters.Regex(r'^[^\/][a-z]{4,20}')
    application.add_handler(MessageHandler(discord_filter, own_mentor))
    application.add_handler(CommandHandler("mentor", assess_mentor))
    #application.add_handler(CommandHandler("help", help_command))
    
    # Run schedule job
    dt = time(hour=10, tzinfo=timezone('Europe/Moscow'))
    application.job_queue.run_daily(post_daily_message, dt, name='user_alert')
    # Run the bot until the user presses Ctrl-C
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
