'''Utils for Optiteam mentor bot'''
from time import sleep
#from datetime import date
import configparser
import requests
import pandas as pd
#import httpx

config = configparser.ConfigParser()
config.read('config.ini')

TOKEN = config.get('tgbot', 'TOKEN')
OT_CHAT_ID = config.get('tgbot', 'OT_CHAT_ID')

WS_NAME = config.get('OM', 'WS_NAME')
OM_TOKEN = config.get('OM', 'OM_TOKEN')
SERVICE_NAME = config.get('OM', 'SERVICE_NAME')

WS_URL = WS_NAME + 'service/'+ SERVICE_NAME
WS_URL_FULL = WS_URL + '?token=' + OM_TOKEN


def get_chat_member(user_id):
    '''Get information about user from OT chat'''
    method_url = f'getChatMember?chat_id={OT_CHAT_ID}&user_id={user_id}'
    url = f'https://api.telegram.org/bot{TOKEN}/' + method_url
    return requests.get(url, timeout=5).json()


def req_om_list(list_name):
    '''Get competentions matrix from HR model 'Competentions'''
    req_url = WS_URL + f'?token={OM_TOKEN}'
    ws_list_url = req_url + f'&type=list&name={list_name}&outputType=dictionary'
    return requests.get(ws_list_url, timeout=5).json()


def req_om_mc(mc_name, view=None, formula='TRUE'):
    '''Request OM multicube'''
    body = {
        "SRC": {
            "TYPE": 'OM_MULTICUBE',
            "PARAMS": {
                "NAME": mc_name,
                "VIEW": view,
                'FORMULA_FILTER': formula,
                'CHARSET': 'UTF-8'
            }
        },
        "DEST": {
            "TYPE": 'OM_WEB_SERVICE_PASSIVE',
            "PARAMS": {
                "OUTPUT_TYPE": "DICTIONARY",
            }
        }
    }
    headers = {"Authorization": "Bearer " + OM_TOKEN}
    return requests.post(WS_URL, json = body, headers=headers, timeout=5).json()


def get_om_response(req_answer):
    '''Get response from OM'''
    #try if wrong token
    if req_answer['type'] == 'ERROR':
        print('OM API response type: ERROR, message: ', req_answer['params']['message'])
        return {}
    response_id = req_answer['params']['id']
    response_token = req_answer['params']['responseToken']
    ws_resp_url = WS_URL + f'/response/{response_id}?responseToken={response_token}'
    headers = {"Authorization": "Bearer " + OM_TOKEN}
    bool_flag = True
    while bool_flag:
        sleep(1)
        r = requests.get(ws_resp_url, headers=headers, timeout=5)
        if r.json()['type'] == 'ERROR':
            print('ERROR')
            break
        bool_flag =  r.json()['params']['status'] == 'IN_PROGRESS'
    return r.json()['params']['data']['requestedData']


def get_om_list(list_name, result='df'):
    '''Get OM list'''
    req_answer = req_om_list(list_name)
    resp = get_om_response(req_answer)
    if result == 'df':
        resp = pd.json_normalize(resp)
    return resp


def get_om_mc(mc_name, view=None, formula='TRUE', result='df'):
    '''Get OM multicube'''
    req_answer = req_om_mc(mc_name, view, formula)
    print(req_answer)
    resp = get_om_response(req_answer)
    if result == 'df':
        resp = pd.json_normalize(resp)
    return resp


def get_om_mc_json(mc_name, view=None, formula='TRUE'):
    '''Get OM multicube'''
    req_answer = req_om_mc(mc_name, view, formula)
    resp = get_om_response(req_answer)
    return resp


def make_buttons(df, parent='Все области'):
    '''Make keyboard for domain quiz'''
    #comp_matrix = get_om_list('Области экспертизы для бота', result='json')
    #items_l = [l for l in comp_matrix if l['Parent'] == parent]
    #print(items_l)
    
    items = df[df.Parent == parent].Entity.values.tolist()
    keyboard = [[{'text': i, 'callback_data': 'comp_' + df[df.Entity == i].Code.item()}] for i in items]
    
    #keyboard_l = [[{'text': l['Entity'], 'callback_data': 'comp_' + l['Code']}] for l in items_l if l['Parent'] == parent]
    #print(keyboard_l)
    if parent != 'Все области':
        keyboard.append([{'text': 'Вернуться назад', 'callback_data': 'comp_back'}])
    return keyboard


def write_om_list(url, list_name, std_map, post_data):
    '''Write OM list'''
    post_body = {
    "SRC": {
        "TYPE": 'OM_WEB_SERVICE_PASSIVE',
        "PARAMS": {
        }
    },
    "DEST": {
        "TYPE": 'LIST',
        "PARAMS": {
            "NAME": list_name,
            "TRANSFORM": {
                "CHARSET": "UTF-8",
                "SRC_TO_DEST_COLUMN_MAP": std_map,
            },
        }
    },
    "DATA": post_data
}
    return requests.post(url, json = post_body, timeout=5).json()


def reg_user_in_om(om_user, tg_id, tg_login):
    '''Add information about user in HR model'''
    mc_name = 'ML Users'
    std_map = {
        "tg_id": "Telegram_id",
        "tg_login": "Telegram_login",
    }
    dimentions = {
                  'dim1': {
                      'NAME': "Users",
                      #'SRC_COLUMN_NAME': 'User',
                      'ON_VALUE': {
                            'TYPE': "STATIC_VALUE",
                            'PARAMS': {
                                'VALUE': om_user
                            }
                      }
                  },
    }
    post_data = [
        {
            "tg_id": tg_id,
            "tg_login": tg_login
        }
    ]
    return write_om_mc(mc_name, std_map, dimentions, post_data)


def write_om_mc(mc_name, std_map, dimensions, post_data):
    '''Write data to OM multicube'''
    post_body = {
    "SRC": {
        "TYPE": 'OM_WEB_SERVICE_PASSIVE',
        "PARAMS": {
        }
    },
    "DEST": {
        'TYPE': "OM_MULTICUBE",
      'PARAMS': {
          'NAME': mc_name,
          'TRANSFORM': {
              'CHARSET': "WINDOWS-1251", #"UTF-8"
              'SRC_TO_DEST_COLUMN_MAP': std_map,
              'DIMENSIONS': dimensions,
          },
      }
    },
    "DATA": post_data
}
    return requests.post(WS_URL_FULL, json = post_body, timeout=5).json()


def write_selection(om_user, selected_mentor, domain, day):
    '''Write selected mentor to HR model'''
    mc_name = "Удовлетворенность ментором"
    std_map = {
        "Selection":"Выбранный ментор текст",
        "Domain":"Выбранная тема текст"
    }
    #day = date.today().strftime("%d.%m.%Y")
    dimensions = {
                  'dim1': {
                      'NAME': "Users",
                      'SRC_COLUMN_NAME': 'User',
                      'ON_VALUE': "AS_IS"
                  },
                  'dim2': {
                      'NAME': "Days",
                      'SRC_COLUMN_NAME': "Day",
                      'ON_VALUE': {
                        'TYPE': "BASE_DATE",
                        'PARAMS': {
                                'TIME_SCALE': "DAY"
                            }
                  },
            }
    }
    post_data = [
        {
            "User": om_user,
            "Selection": selected_mentor,
            "Domain": domain,
            "Day": day
        }
    ]
    return write_om_mc(mc_name, std_map, dimensions, post_data)


def make_mentor_message(mentor):
    '''Make massage wirh choosen mentors'''
    mentor_name = mentor['name']
    mentor_grade = mentor['mentor_grade']
    key_skills = mentor['other_skills'].split(", ")
    domains = mentor['skills'].split(", ")
    msg_start = f'''🙂 {mentor_name}
Должность: 	{mentor_grade}
📌 Ключевые навыки:'''
    for skill in key_skills:
        msg_start = msg_start + '\n - ' + skill
    msg_start += '\n📌 Ключевые отрасли:'
    for dom in domains:
        msg_start = msg_start + '\n - ' + dom
    return msg_start + '\n'


def make_mentor_cards(om_user, mentors, code, dom):
    '''Make massage and keyboard with choosen mentors'''
    keyboard = []
    message = f'Я нашел для тебя следующие варианты по теме "{dom}":\n'
    i = 0
    for m in mentors:
        if m['user'] != om_user and i < 5:
            message += '_______\n'
            message += make_mentor_message(m)
            keyboard.append([{'text': m['name'], 'callback_data': 'men_' + m['discord'] + '_' +  code}])
            i += 1
    keyboard.append([{'text': 'Свой вариант', 'callback_data': 'men_' + 'own' + '_' +  code}])
    message += '''_______
❔Если кто-то из менторов тебе подходит, нажми на кнопку с именем ниже, а я подскажу тебе следующие шаги. 
❔Если хочешь начать поиск заново, нажми /start'''
    #keyboard = [[{'text': m['name'], 'callback_data': 'men_' + m['discord'] + '_' +  code}] for m in mentors]
    return message, keyboard


def write_assessment(om_user, day, assessment, time):
    '''Write mentor's assessment to HR model'''
    mc_name = "Удовлетворенность ментором"
    std_map = {
        "Selection":"Оценка (от 1 до 5)",
        "Time":"Оценка времени"
    }
    #day = date.today().strftime("%d.%m.%Y")
    dimentions = {
                  'dim1': {
                      'NAME': "Users",
                      'SRC_COLUMN_NAME': 'User',
                      'ON_VALUE': "AS_IS"
                  },
                  'dim2': {
                      'NAME': "Days",
                      'SRC_COLUMN_NAME': "Day",
                      'ON_VALUE': "AS_IS"
            }
    }
    post_data = [
        {
            "User": om_user,
            "Selection": assessment,
            "Time": time,
            "Day": day
        }
    ]
    return write_om_mc(mc_name, std_map, dimentions, post_data)


def main():
    '''main'''
    data = get_om_mc('ML Users', result='json')
    #payload = {user['Telegram_id']: user for user in data if user['Telegram_id']}
    print(WS_URL_FULL)
    print(data)

    #sleep(3)


if __name__ == "__main__":
    main()
