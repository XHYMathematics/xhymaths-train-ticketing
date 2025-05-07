from flask import Flask, render_template, redirect, request, session, abort
import mysql.connector
import secrets
import bcrypt
import logging
import os
from bitarray import bitarray
from datetime import datetime, timedelta
from math import *
import threading
import bisect

app = Flask(__name__)
# app.secret_key = secrets.token_hex()
app.secret_key = 'temp'
password = 'dad24c7ed22f45c141d342c669a3a286bbf9c954916dc25de166ceeb1955764b'

cur_dir = os.path.dirname(__file__)
config_path = os.path.join(cur_dir, 'config.ini')
app_path = os.path.join(cur_dir, 'train_ticketing.py')
log_path = os.path.join(cur_dir, 'app.log')

file_handler = logging.FileHandler(log_path)
file_handler.setLevel(logging.DEBUG)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s [%(filename)s %(lineno)d] %(levelname)s：%(message)s')
file_handler.setFormatter(formatter)
console_handler.setFormatter(formatter)
werkzeug_logger = logging.getLogger('werkzeug')
werkzeug_formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
werkzeug_logger.addHandler(file_handler)
app.logger.setLevel(logging.INFO)
app.logger.addHandler(file_handler)

host = '::'
port = 8080
app.debug = True
rule = {
    'unit_price': 0.155,
    'train_prices': {
        i: 0.5 for i in '5678'} | {
        i: 1 for i in '1234KTZ'} | {
        'D': 2,
        'G': 3
    },
    'seat_prices': [1, 1.6, 50, 1.13, 65, 1.77],
    'seat_names': {
        i: ['硬座', '软座', '硬卧', '软卧'] for i in '12345678KTZ'} | {
        i: ['二等座', '一等座', '二等卧', '一等卧'] for i in 'DG'
    },
    'timeout': 1
}
mysql_arg_names = ['user', 'host', 'password', 'database']
mysql_args = [
    'local-web-server-user',
    '::1',
    'eadd5a759647ac9139e0564abf97496b6e2f12238d43a5185a8c321f16434a94',
    '010_TRAIN_TICKETING'
]

def load_config():
    try:
        global rule
        with open(config_path, 'r', encoding='UTF-8') as file:
            for line in file:
                args = line.split()
                if len(args) < 2:
                    continue
                if args[0] in ['host', 'port', 'unit_price']:
                    globals()[args[0]] = args[1]
                elif args[0] == 'debug':
                    app.debug = args[1]
                elif args[0] == 'mysql':
                    global mysql_args
                    mysql_args = args[1:]
                elif args[0] == 'unit-price':
                    rule['unit_price'] = float(args[1])
                elif args[0] == 'set-train-prices':
                    rule['train_prices'][args[1]] = float(args[2])
                elif args[0] == 'seat-prices':
                    rule['seat_prices'] = [float(i) for i in args[1:]]
                elif args[0] == 'set-seat-names':
                    rule['seat_names'][args[1]] = args[2]
    except FileNotFoundError:
        pass

load_config()

@app.route('/status')
def status():
    return "XHYMaths' Train Ticketing System"
@app.route('/reload', methods=['GET', 'POST'])
def reload():
    if request.remote_addr == '::1' and request.method == 'POST' and 'password' in request.form and request.form['password'] == password:
        load_config()
        return 'Reloaded successfully.'
    else:
        abort(403)
@app.route('/exit', methods=['GET', 'POST'])
def exit():
    if request.remote_addr == '::1' and request.method == 'POST' and 'password' in request.form and request.form['password'] == password:
        os._exit(123)
    else:
        abort(403)

actype_name = ['普通用户', '管理员']
default_seat_name = ['硬/二等座', '软/一等座', '硬/二等卧', '软/一等卧']
change_type_name = ['充值', '消费', '退款']
order_status_name = ['已支付', '已退款']

def bytes_to_bitarray(by: bytes) -> bitarray:
    ba = bitarray()
    ba.frombytes(by)
    return ba
def price(tnumber0: str, dist: int, seat_type: int) -> float:
    if seat_type in [0, 1]:
        res = rule['train_prices'][tnumber0] * dist * rule['unit_price'] * rule['seat_prices'][int(seat_type)]
    elif seat_type == 2:
        res = rule['train_prices'][tnumber0] * (rule['seat_prices'][2] + dist * rule['unit_price'] * rule['seat_prices'][3])
    elif seat_type == 3:
        res = rule['train_prices'][tnumber0] * (rule['seat_prices'][4] + dist * rule['unit_price'] * rule['seat_prices'][5])
    res = divmod(res, 1)
    res1 = 0 if res[1] < 0.25 else 0.5 if res[1] < 0.75 else 1
    return res[0] + res1
def update_balance():
    with conn.cursor() as cur:
        cur.execute("SELECT BALANCE FROM ACCOUNTS WHERE USERNAME = %s", (session['userinfo']['username'],))
        balance = cur.fetchone()[0]
    session['userinfo']['balance'] = balance
    session.modified = True

@app.route('/', methods=['GET', 'POST'])
def login():
    if 'userinfo' in session:
        return redirect('/main')
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password'].encode('UTF-8')
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM ACCOUNTS WHERE username = %s", (username,))
            user = cur.fetchone()
        if user and bcrypt.checkpw(password, user[1].encode('UTF-8')):
            session['userinfo'] = {
                'username': user[0],
                'actype': user[2],
                'actype_name': actype_name[user[2]],
                'balance': user[3]
            }
            return redirect('/main')
        else:
            return '用户名或密码错误！'
    return render_template('login.html')
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password'].encode('UTF-8')
        confirm_password = request.form['confirm_password'].encode('UTF-8')
        actype = request.form['actype']
        if password != confirm_password:
            return '两次输入的密码不一致！'
        hashed_password = bcrypt.hashpw(password, bcrypt.gensalt())
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM ACCOUNTS WHERE username = %s", (username,))
            if cur.fetchone():
                return '用户名已存在！'
            if actype == '1':
                super_admin_password = request.form['super_admin_password'].encode('UTF-8')
                cur.execute("SELECT * FROM SUPER_ADMIN_PASSWORD")
                if not bcrypt.checkpw(super_admin_password, cur.fetchone()[0].encode('UTF-8')):
                    return '超级管理员密码错误！'
            cur.execute("INSERT INTO ACCOUNTS VALUES (%s, %s, %s, %s)",
                        (username, hashed_password, actype, 0 if actype == '0' else None))
        conn.commit()
        return redirect('/')
    return render_template('register.html')
@app.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return redirect('/')
@app.route('/main', methods=['GET', 'POST'])
def main():
    if 'userinfo' not in session:
        return redirect('/')
    if request.method == 'POST':
        session['search'] = dict(request.form) | {
            'sort': request.form.getlist('sort')
        }
        return redirect('/main')
    update_balance()
    userinfo = session['userinfo']
    search = session.get('search', {})
    if not search:
        search = {
            '1': '',
            'K': '',
            'T': '',
            'Z': '',
            'D': '',
            'G': '',
            'sort': ['0', 'asc']
        }
        trains = []
        train_infos = []
    else:
        sort = search.setdefault('sort', ['0', 'asc'])
        sql = """\
            SELECT
                TNUMBER,
                DEPARTURE_TIME,
                ARRIVAL_TIME,
                DAY_DIFF,
                DURATION,
                TDATE,
                BEGIN_STOPNO,
                END_STOPNO,
                DISTANCE
            FROM VTRAIN_SEGMENTS
            WHERE
                T_DEPARTURE_DATE = %s
                AND BEGIN_STATION_NAME = %s
                AND END_STATION_NAME = %s
        """
        if userinfo['actype'] != 1:
            if search['t_departure_date'] < datetime.now().strftime('%Y-%m-%d'):
                return '查询日期不能早于当前日期！'
            sql += ' AND DATE_ADD(CURRENT_TIMESTAMP, INTERVAL 3 MINUTE) < T_DEPARTURE_DATETIME'
        has_type_checked = False
        if not ({'1', 'K', 'T', 'Z', 'D', 'G'} <= search.keys()):
            if '1' in search:
                sql += f" {'OR' if has_type_checked else 'AND ('} TNUMBER REGEXP '^[0-9]'"
                has_type_checked = True
            for i in ['K', 'T', 'Z', 'D', 'G']:
                if i in search:
                    sql += f" {'OR' if has_type_checked else 'AND ('} TNUMBER LIKE '{i}%'"
                    has_type_checked = True
            if has_type_checked:
                sql += ')'
        else:
            has_type_checked = True
        if not has_type_checked:
            search |= {
                '1': '',
                'K': '',
                'T': '',
                'Z': '',
                'D': '',
                'G': ''
            }
            session['search'] = search
        with conn.cursor() as cur:
            cur.execute(sql, (search['t_departure_date'], search['begin_station'], search['end_station']))
            trains = cur.fetchall()
        train_infos = []
        for i in range(len(trains)):
            trains[i] = list(trains[i])
            train_info = trains[i][5:]
            train_infos.append(train_info)
            trains[i] = trains[i][:5]
            train = trains[i]
            sql = """\
                SELECT SEATS0, SEATS1, SEATS2, SEATS3
                FROM TRAIN_STOPS
                WHERE TDATE = %s AND TNUMBER = %s AND STOPNO BETWEEN %s AND %s
            """
            with conn.cursor() as cur:
                cur.execute(sql, (train_info[0], train[0], train_info[1], train_info[2]))
                seats = cur.fetchall()
            for i in range(len(seats)):
                seats[i] = list(seats[i])
                for j in range(4):
                    if seats[i][j] is not None:
                        seats[i][j] = bytes_to_bitarray(seats[i][j])
            seat_num = [0] * 4
            with conn.cursor() as cur:
                sql = """\
                    SELECT SEAT_TYPE, MAX(SEAT_PREFSUM) FROM TRAIN_SEATS
                    WHERE TDATE = %s AND TNUMBER = %s
                    GROUP BY SEAT_TYPE
                """
                cur.execute(sql, (train_info[0], train[0]))
                res = cur.fetchall()
                for i in res:
                    if i[1] is not None:
                        seat_num[i[0]] = i[1]
            seat_cnt = [bitarray(len(seats[0][i])) for i in range(4)]
            for j in range(4):
                if len(seats[0][j]):
                    for i in range(len(seats)):
                        seat_cnt[j] |= seats[i][j]
                    seat_cnt[j] = seat_num[j] - seat_cnt[j].count()
                else:
                    seat_cnt[j] = None
            train += [seat_cnt[i] if seat_cnt[i] is not None else None for i in range(4)]
            prices = [price(train[0][0], train_info[3], i) if train[i+5] is not None else None for i in range(4)]
            for i in range(4):
                if train[i+5] is not None:
                    train[i+5] = (train[i+5], f'{prices[i]:g}')
            train.extend(train_info[:2])
        trains.sort(key=lambda x: x[int(sort[0])], reverse=sort[1] == 'desc')
    return render_template('main.html', userinfo=userinfo, rule=rule, default_seat_name=default_seat_name, search=search, trains=trains, train_infos=train_infos, cur_date=datetime.now().strftime('%Y-%m-%d'))
@app.route('/train', methods=['GET', 'POST'])
def train():
    if 'userinfo' not in session:
        return redirect('/')
    if request.method == 'POST':
        session['train_search'] = request.form
        return redirect('/train')
    update_balance()
    userinfo = session['userinfo']
    train_search = session.get('train_search', {})
    if not train_search:
        stops = []
        cars = []
    else:
        sql = """\
            SELECT
                STOPNO,
                STATION_NAME,
                ARRIVAL_DAY+1,
                DATE_FORMAT(ARRIVAL_TIME, '%H:%i') ARRIVAL_TIME,
                DATE_FORMAT(DEPARTURE_TIME, '%H:%i') DEPARTURE_TIME,
                TIME_INTERVAL,
                DIST_PREFSUM,
                T_ARRIVAL_DATE
            FROM VTRAIN_STOPS
            WHERE TDATE = %s AND TNUMBER = %s
            ORDER BY STOPNO ASC
        """
        with conn.cursor() as cur:
            cur.execute(sql, (train_search['tdate'], train_search['tnumber']))
            stops = cur.fetchall()
        sql = """\
            SELECT CARNO, SEAT_PREFSUM, SEAT_TYPE
            FROM TRAIN_SEATS
            WHERE TDATE = %s AND TNUMBER = %s
            ORDER BY CARNO ASC
        """
        with conn.cursor() as cur:
            cur.execute(sql, (train_search['tdate'], train_search['tnumber']))
            cars = cur.fetchall()
        seat_sum = [0] * 4
        for i in range(len(cars)):
            cars[i] = list(cars[i])
            cars[i][1] = int(cars[i][1]) - seat_sum[cars[i][2]]
            seat_sum[cars[i][2]] += cars[i][1]
    return render_template('train.html', userinfo=userinfo, rule=rule, train_search=train_search, stops=stops, cars=cars)
@app.route('/train_date', methods=['GET', 'POST'])
def train_date():
    if 'userinfo' not in session:
        return redirect('/')
    if request.method == 'POST':
        session['train_search'] = request.form
        if 'tnumber' not in session['train_search']:
            return redirect('/train')
        return redirect('/train_date')
    update_balance()
    userinfo = session['userinfo']
    train_search = session['train_search']
    sql = """\
        SELECT TDATE FROM TRAINS
        WHERE TNUMBER = %s
        ORDER BY TDATE ASC
    """
    with conn.cursor() as cur:
        cur.execute(sql, (train_search['tnumber'],))
        dates = cur.fetchall()
    return render_template('train_date.html', userinfo=userinfo, train_search=train_search, dates=dates)

@app.route('/train_manage', methods=['GET', 'POST'])
def train_manage():
    if 'userinfo' not in session or session['userinfo']['actype'] != 1:
        return redirect('/')
    userinfo = session['userinfo']
    return render_template('train_manage.html', userinfo=userinfo)

def date_range(begin_date_str: str, end_date_str: str):
    begin_date = datetime.strptime(begin_date_str, '%Y-%m-%d')
    end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
    current_date = begin_date
    while current_date <= end_date:
        yield current_date.strftime('%Y-%m-%d')
        current_date += timedelta(days=1)

@app.route('/add_train', methods=['GET', 'POST'])
def add_train():
    if 'userinfo' not in session or session['userinfo']['actype'] != 1:
        return redirect('/')
    if request.method == 'POST':
        if 'clear' in request.form:
            session.pop('add_train', None)
        elif 'from_existing_train' in request.form:
            add_train = session['add_train'] = {
                'begin_tdate': request.form['tdate'],
                'end_tdate': request.form['tdate'],
                'tnumber': request.form['tnumber'],
                'stops': [],
                'cars': []
            }
            sql = """\
                SELECT
                    STATION_NAME,
                    ARRIVAL_DAY+1,
                    DATE_FORMAT(ARRIVAL_TIME, '%H:%i'),
                    DATE_FORMAT(DEPARTURE_TIME, '%H:%i'),
                    DIST_PREFSUM
                FROM TRAIN_STOPS
                WHERE TDATE = %s AND TNUMBER = %s
                ORDER BY STOPNO ASC
            """
            with conn.cursor() as cur:
                cur.execute(sql, (add_train['begin_tdate'], add_train['tnumber']))
                stops = cur.fetchall()
            for stop in stops:
                for item in stop:
                    session['add_train']['stops'].append(item)
            sql = """\
                SELECT CARNO, SEAT_PREFSUM, SEAT_TYPE
                FROM TRAIN_SEATS
                WHERE TDATE = %s AND TNUMBER = %s
                ORDER BY CARNO ASC
            """
            with conn.cursor() as cur:
                cur.execute(sql, (add_train['begin_tdate'], add_train['tnumber']))
                cars = cur.fetchall()
            seat_sum = [0] * 4
            for i in range(len(cars)):
                cars[i] = list(cars[i])
                cars[i][1] = int(cars[i][1]) - seat_sum[cars[i][2]]
                seat_sum[cars[i][2]] += cars[i][1]
            for i in range(len(cars)):
                for j in range(3):
                    if j % 3 == 2:
                        cars[i][j] = str(cars[i][j])
                    session['add_train']['cars'].append(cars[i][j])
        else:
            add_train = session['add_train'] = {
                'begin_tdate': request.form['begin_tdate'],
                'end_tdate': request.form['end_tdate'],
                'tnumber': request.form['tnumber'],
                'stops': request.form.getlist('stops'),
                'cars': request.form.getlist('cars')
            }
            if 'save' not in request.form:
                begin_tdate = add_train['begin_tdate']
                end_tdate = add_train['end_tdate']
                tnumber = add_train['tnumber']
                stops = add_train['stops']
                cars = add_train['cars']
                if begin_tdate > end_tdate:
                    return '开始日期不能晚于结束日期！'
                sql = """\
                    SELECT 1 FROM TRAINS
                    WHERE TNUMBER = %s AND TDATE BETWEEN %s AND %s
                """
                with conn.cursor() as cur:
                    cur.execute(sql, (tnumber, begin_tdate, end_tdate))
                    if cur.fetchone():
                        return '该日期范围内的某个日期已有该车次！'
                prev_carno = 0
                car_cnt = 0
                for i in range(0, len(cars), 3):
                        car_cnt += 1
                        if int(cars[i]) <= prev_carno:
                            return f'第{car_cnt}个车厢的车厢号有误，上一个车厢号为{prev_carno}，但接下来的车厢号为{cars[i]}！'
                        prev_carno = int(cars[i])
                max_day = 1
                max_dist = 0
                stopno = 0
                for i in range(0, len(stops), 5):
                    stopno += 1
                    if int(stops[i+4]) < max_dist:
                        return f'第{stopno}站{stops[i]}站的累计里程有误！'
                    max_dist = int(stops[i+4])
                    if int(stops[i+1]) > max_day:
                        max_day = int(stops[i+1])
                    elif int(stops[i+1]) < max_day:
                        return f'第{stopno}站{stops[i]}站的天数有误！'
                    if i!=0 and stops[i+2]=='':
                        return f'第{stopno}站{stops[i]}站不是始发站，但进站时间为空！'
                    if i!=len(stops)-5 and stops[i+3]=='':
                        return f'第{stopno}站{stops[i]}站不是终到站，但出站时间为空！'
                    if i!=0 and i!=len(stops)-5 and stops[i+3]<stops[i+2] and int(stops[i+1])+1!=int(stops[i+5+1]):
                        return f'第{stopno}站{stops[i]}站的下一站未跨天，但第{stopno}站{stops[i]}站的出站时间小于进站时间！'
                    if i!=0 and stops[i+2]<stops[i-5+3] and int(stops[i+1])-1!=int(stops[i-5+1]):
                        return f'第{stopno}站{stops[i]}站未跨天，但进站时间小于上一站出站时间！'
                conn.rollback()
                for tdate in date_range(begin_tdate, end_tdate):
                    with conn.cursor() as cur:
                        cur.execute("INSERT INTO TRAINS VALUES (%s, %s)", (tdate, tnumber))
                        seat_sum = [0] * 4
                        for i in range(0, len(cars), 3):
                            seat_sum[int(cars[i+2])] += int(cars[i+1])
                            cur.execute("INSERT INTO TRAIN_SEATS VALUES (%s, %s, %s, %s, %s)",
                                        (tdate, tnumber, cars[i], seat_sum[int(cars[i+2])], cars[i+2]))
                        stopno = 0
                        stops[2] = None
                        stops[len(stops)-5+3] = None
                        for i in range(0, len(stops), 5):
                            stopno += 1
                            cur.execute("INSERT INTO TRAIN_STOPS VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                                        (tdate, tnumber, stopno, stops[i], int(stops[i+1])-1, stops[i+2], stops[i+3], stops[i+4], bytes(ceil(seat_sum[0]/8)), bytes(ceil(seat_sum[1]/8)), bytes(ceil(seat_sum[2]/8)), bytes(ceil(seat_sum[3]/8))))
                conn.commit()
                session['train_search'] = {
                    'tdate': begin_tdate,
                    'tnumber': tnumber
                }
                return redirect('/train')
        return redirect('/add_train')
    userinfo = session['userinfo']
    add_train = session.get('add_train', {})
    return render_template('add_train.html', userinfo=userinfo, rule=rule, add_train=add_train, default_seat_name=default_seat_name)
@app.route('/train_list', methods=['GET', 'POST'])
def train_list():
    if 'userinfo' not in session or session['userinfo']['actype'] != 1:
        return redirect('/')
    if request.method == 'POST':
        if 'clear' in request.form:
            session.pop('train_list_search', None)
        else:
            session['train_list_search'] = request.form
        return redirect('/train_list')
    userinfo = session['userinfo']
    train_list_search = session.get('train_list_search', {})
    sql = "SELECT TDATE, TNUMBER FROM TRAINS"
    params = []
    first_param = True
    for condition in ['tdate', 'tnumber']:
        if train_list_search.get(condition):
            sql += f" {'WHERE' if first_param else 'AND'} {condition.upper()} = %s"
            params.append(train_list_search[condition])
            first_param = False
    with conn.cursor() as cur:
        cur.execute(sql, params)
        trains = cur.fetchall()
    return render_template('train_list.html', userinfo=userinfo, train_list_search=train_list_search, trains=trains)
@app.route('/train_info', methods=['GET', 'POST'])
def train_info():
    if 'userinfo' not in session or session['userinfo']['actype'] != 1:
        return redirect('/')
    if request.method == 'POST':
        session['train_search'] = request.form
        return redirect('/train_info')
    userinfo = session['userinfo']
    train_search = session.get('train_search', {})
    if not train_search:
        stops = []
        cars = []
    else:
        sql = """\
            SELECT CARNO, SEAT_PREFSUM, SEAT_TYPE
            FROM TRAIN_SEATS
            WHERE TDATE = %s AND TNUMBER = %s
            ORDER BY CARNO ASC
        """
        with conn.cursor() as cur:
            cur.execute(sql, (train_search['tdate'], train_search['tnumber']))
            cars = cur.fetchall()
        seat_sum = [0] * 4
        for i in range(len(cars)):
            cars[i] = list(cars[i])
            cars[i][1] = int(cars[i][1]) - seat_sum[cars[i][2]]
            seat_sum[cars[i][2]] += cars[i][1]
        sql = """\
            SELECT
                STOPNO,
                STATION_NAME,
                ARRIVAL_DAY+1,
                DATE_FORMAT(ARRIVAL_TIME, '%H:%i') ARRIVAL_TIME,
                DATE_FORMAT(DEPARTURE_TIME, '%H:%i') DEPARTURE_TIME,
                TIME_INTERVAL,
                DIST_PREFSUM,
                SEATS0,
                SEATS1,
                SEATS2,
                SEATS3
            FROM VTRAIN_STOPS
            WHERE TDATE = %s AND TNUMBER = %s
            ORDER BY STOPNO ASC
        """
        with conn.cursor() as cur:
            cur.execute(sql, (train_search['tdate'], train_search['tnumber']))
            stops = cur.fetchall()
        for i in range(len(stops)):
            stops[i] = list(stops[i])
            seats = stops[i][7:]
            for j in range(len(seats)):
                seats[j] = bytes_to_bitarray(seats[j])
            stops[i] = stops[i][:7]
            stop = stops[i]
            stop.append([])
            ptr = [0] * 4
            for car in cars:
                stop[7].append(seats[car[2]][ ptr[car[2]] : ptr[car[2]]+car[1] ])
                ptr[car[2]] += car[1]
    return render_template('train_info.html', userinfo=userinfo, train_search=train_search, stops=stops, cars=cars)

@app.route('/station', methods=['GET', 'POST'])
def station():
    if 'userinfo' not in session:
        return redirect('/')
    if request.method == 'POST':
        session['station_search'] = request.form
        return redirect('/station')
    update_balance()
    userinfo = session['userinfo']
    station_search = session.get('station_search', {})
    if not station_search:
        trains = []
    else:
        station_search.setdefault('tdate', datetime.now().strftime('%Y-%m-%d'))
        station_search.setdefault('arr_or_dep', '0')
        sql = """\
            SELECT
                TNUMBER,
                DATE_FORMAT(ARRIVAL_TIME, '%H:%i') ARRIVAL_TIME,
                DATE_FORMAT(DEPARTURE_TIME, '%H:%i') DEPARTURE_TIME,
                TDATE
            FROM VTRAIN_STOPS
            WHERE
                STATION_NAME = %s
        """
        if station_search['arr_or_dep'] == '0':
            sql += """\
                AND T_ARRIVAL_DATE = %s
                AND ARRIVAL_TIME IS NOT NULL
                ORDER BY ARRIVAL_TIME ASC
            """
        else:
            sql += """\
                AND T_DEPARTURE_DATE = %s
                AND DEPARTURE_TIME IS NOT NULL
                ORDER BY DEPARTURE_TIME ASC
            """
        with conn.cursor() as cur:
            cur.execute(sql, (station_search['station_name'], station_search['tdate']))
            trains = cur.fetchall()
        for i in range(len(trains)):
            if station_search['arr_or_dep'] != '1':
                trains[i] = (trains[i][0], trains[i][1], trains[i][3])
            else:
                trains[i] = (trains[i][0], trains[i][2], trains[i][3])
    return render_template('station.html', userinfo=userinfo, station_search=station_search, trains=trains)

seat_locks = {}
def select_price(args: dict):
    sql = """\
        SELECT DISTANCE FROM VTRAIN_SEGMENTS
        WHERE TDATE = %s AND TNUMBER = %s AND BEGIN_STOPNO = %s AND END_STOPNO = %s
    """
    with conn.cursor() as cur:
        cur.execute(sql, (args['tdate'], args['tnumber'], args['begin_stopno'], args['end_stopno']))
        dist = cur.fetchone()[0]
    return price(args['tnumber'][0], dist, int(args['seat_type']))
def seatid_to_carno_seatno(args, seatid):
    sql = """\
        SELECT CARNO FROM TRAIN_SEATS
        WHERE TDATE = %s AND TNUMBER = %s AND SEAT_TYPE = %s AND SEAT_PREFSUM > %s
        ORDER BY CARNO ASC
        LIMIT 1
    """
    with conn.cursor() as cur:
        cur.execute(sql, (args['tdate'], args['tnumber'], args['seat_type'], seatid))
        carno = cur.fetchone()[0]
    sql = """\
        SELECT SEAT_PREFSUM FROM TRAIN_SEATS
        WHERE TDATE = %s AND TNUMBER = %s AND SEAT_TYPE = %s AND CARNO < %s
        ORDER BY CARNO DESC
        LIMIT 1
    """
    with conn.cursor() as cur:
        cur.execute(sql, (args['tdate'], args['tnumber'], args['seat_type'], carno))
        seat_prefsum = cur.fetchone()
    if not seat_prefsum:
        seat_prefsum = 0
    else:
        seat_prefsum = seat_prefsum[0]
    seatno = seatid - seat_prefsum + 1
    return carno, seatno
def carno_seatno_to_seatid(args, carno, seatno):
    sql = """\
        SELECT SEAT_PREFSUM FROM TRAIN_SEATS
        WHERE TDATE = %s AND TNUMBER = %s AND SEAT_TYPE = %s AND CARNO < %s
        ORDER BY CARNO ASC
        LIMIT 1
    """
    with conn.cursor() as cur:
        cur.execute(sql, (args['tdate'], args['tnumber'], args['seat_type'], carno))
        seat_prefsum = cur.fetchone()
    if not seat_prefsum:
        seat_prefsum = 0
    else:
        seat_prefsum = seat_prefsum[0]
    seatid = seat_prefsum + seatno - 1
    return seatid

@app.route('/buy_ticket', methods=['GET', 'POST'])
def buy_ticket():
    if 'userinfo' not in session or session['userinfo']['actype'] != 0:
        return redirect('/')
    if request.method == 'POST':
        session['buy_ticket'] = request.form
        if 'password' not in request.form:
            return redirect('/buy_ticket')
        else:
            buy_ticket = session['buy_ticket']
            sql = """\
                SELECT PASSWORD FROM ACCOUNTS
                WHERE USERNAME = %s
            """
            with conn.cursor() as cur:
                cur.execute(sql, (session['userinfo']['username'],))
                hashed_password = cur.fetchone()[0].encode('UTF-8')
            if not bcrypt.checkpw(request.form['password'].encode('UTF-8'), hashed_password):
                return '密码错误！'
            amount = select_price(buy_ticket)
            sql = """\
                SELECT BALANCE FROM ACCOUNTS
                WHERE USERNAME = %s
            """
            with conn.cursor() as cur:
                cur.execute(sql, (session['userinfo']['username'],))
                balance = cur.fetchone()[0]
            if balance < amount:
                return '余额不足！'
            sql = """\
                SELECT 1
                FROM VORDERS
                WHERE USERNAME = %s AND TDATE = %s AND TNUMBER = %s AND BEGIN_STOPNO = %s AND END_STOPNO = %s AND STATUS = 0
            """
            with conn.cursor() as cur:
                cur.execute(sql, (session['userinfo']['username'], buy_ticket['tdate'], buy_ticket['tnumber'], buy_ticket['begin_stopno'], buy_ticket['end_stopno']))
                if cur.fetchone():
                    return '您已购买过该日期、车次的此区间的车票！'
            if buy_ticket['seat_type'] not in ['0', '1', '2', '3']:
                seat_lock.release()
                abort(403)
            conn.rollback()
            seat_lock = seat_locks.setdefault((buy_ticket['tdate'], buy_ticket['tnumber']), threading.Lock())
            seat_lock.acquire()
            sql = f"""\
                SELECT SEATS{buy_ticket['seat_type']}
                FROM TRAIN_STOPS
                WHERE TDATE = %s AND TNUMBER = %s AND STOPNO BETWEEN %s AND %s
                ORDER BY STOPNO ASC
            """
            with conn.cursor() as cur:
                cur.execute(sql, (buy_ticket['tdate'], buy_ticket['tnumber'], buy_ticket['begin_stopno'], buy_ticket['end_stopno']))
                seats = cur.fetchall()
            for i in range(len(seats)):
                seats[i] = bytes_to_bitarray(seats[i][0])
            seat = bitarray(len(seats[0]))
            for i in range(len(seats)):
                seat |= seats[i]
            seatid = seat.find(bitarray('0'))
            if seatid == -1:
                seat_lock.release()
                return '当前车次、座位类型现已无票！'
            sql = f"""\
                UPDATE TRAIN_STOPS
                SET SEATS{buy_ticket['seat_type']} = %s
                WHERE TDATE = %s AND TNUMBER = %s AND STOPNO = %s
            """
            with conn.cursor() as cur:
                for i in range(len(seats)-1):
                    seats[i][seatid] = 1
                    cur.execute(sql, (seats[i].tobytes(), buy_ticket['tdate'], buy_ticket['tnumber'], int(buy_ticket['begin_stopno'])+i))
            carno, seatno = seatid_to_carno_seatno(buy_ticket, seatid)
            sql = """\
                INSERT INTO ORDERS (USERNAME, TDATE, TNUMBER, BEGIN_STOPNO, END_STOPNO, CARNO, SEATNO, SEAT_TYPE, AMOUNT)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            with conn.cursor() as cur:
                cur.execute(sql, (session['userinfo']['username'], buy_ticket['tdate'], buy_ticket['tnumber'], buy_ticket['begin_stopno'], buy_ticket['end_stopno'], carno, seatno, buy_ticket['seat_type'], amount))
                cur.execute("SELECT MAX(ORDERNO) FROM ORDERS")
                orderno = cur.fetchone()[0]
                cur.callproc('CHANGE_BALANCE', (session['userinfo']['username'], amount, 1, orderno))
            conn.commit()
            seat_lock.release()
            update_balance()
            session['order_search'] = {
                'username': session['userinfo']['username'],
                'orderno': orderno
            }
            return redirect('/orders')
    update_balance()
    userinfo = session['userinfo']
    buy_ticket = session.get('buy_ticket', {})
    return render_template('buy_ticket.html', userinfo=userinfo, rule=rule, buy_ticket=buy_ticket, price=select_price(buy_ticket))

@app.route('/orders', methods=['GET', 'POST'])
def orders():
    if 'userinfo' not in session:
        return redirect('/')
    if request.method == 'POST':
        if 'from_train_info' in request.form:
            session['order_search'] = request.form | {
                'tdate': session['train_search']['tdate'],
                'tnumber': session['train_search']['tnumber'],
            }
        elif 'clear' in request.form:
            session.pop('order_search', None)
        else:
            session['order_search'] = request.form
        return redirect('/orders')
    update_balance()
    userinfo = session['userinfo']
    order_search = session.setdefault('order_search', {})
    if userinfo['actype'] != 1:
        order_search['username'] = userinfo['username']
    sql = """\
        SELECT
            ORDERNO,
            USERNAME,
            T_DEPARTURE_DATE,
            TNUMBER,
            BEGIN_STATION_NAME,
            END_STATION_NAME,
            DEPARTURE_TIME,
            ARRIVAL_TIME,
            DAY_DIFF,
            DURATION,
            CARNO,
            SEATNO,
            SEAT_TYPE,
            AMOUNT,
            ORDER_TIME,
            STATUS,
            TDATE,
            HISTORY
        FROM VORDERS
    """
    params = []
    first_param = True
    for condition in ['username', 'tdate', 'tnumber', 'carno', 'seatno', 'orderno']:
        if order_search.get(condition):
            sql += f" {'WHERE' if first_param else 'AND'} {condition.upper()} = %s"
            params.append(order_search[condition])
            first_param = False
    if order_search.get('status', '-1') != '-1':
        sql += f" {'WHERE' if first_param else 'AND'} STATUS = %s"
        params.append(order_search['status'])
        first_param = False
    if order_search.get('pass_stopno'):
        sql += f" {'WHERE' if first_param else 'AND'} BEGIN_STOPNO <= %s AND %s < END_STOPNO"
        params += [order_search['pass_stopno']] * 2
        first_param = False
    with conn.cursor() as cur:
        cur.execute(sql, params)
        orders = cur.fetchall()
    future_orders = []
    history_orders = []
    for order in orders:
        if order:
            if order[-1]:
                history_orders.append(order)
            else:
                future_orders.append(order)
    orders = [(None, True)] + sorted(future_orders, key=lambda x: (x[2], x[6])) + [(None, bool(history_orders))] + sorted(history_orders, key=lambda x: (x[2], x[6]), reverse=True)
    return render_template('orders.html', userinfo=userinfo, rule=rule, order_search=order_search, orders=orders, order_status_name=order_status_name)
@app.route('/refund', methods=['GET', 'POST'])
def refund():
    if 'userinfo' not in session:
        return redirect('/')
    if request.method == 'POST':
        session['refund'] = request.form
        if 'confirmed' not in request.form:
            return redirect('/refund')
        else:
            userinfo = session['userinfo']
            refund = session['refund']
            orderno = refund['orderno']
            sql = """\
                SELECT
                    USERNAME,
                    TDATE,
                    TNUMBER,
                    BEGIN_STOPNO,
                    END_STOPNO,
                    BEGIN_STATION_NAME,
                    END_STATION_NAME,
                    CARNO,
                    SEATNO,
                    SEAT_TYPE,
                    AMOUNT,
                    STATUS,
                    HISTORY
                FROM VORDERS
                WHERE ORDERNO = %s
            """
            with conn.cursor() as cur:
                cur.execute(sql, (orderno,))
                res = cur.fetchone()
            if not res:
                return '订单不存在！'
            username, tdate, tnumber, begin_stopno, end_stopno, begin_station_name, end_station_name, carno, seatno, seat_type, amount, status, history = res
            if status != 0:
                return '订单不是已支付状态！'
            if userinfo['actype'] != 1 and (username != userinfo['username'] or history):
                abort(403)
            args = {
                'tdate': tdate,
                'tnumber': tnumber,
                'seat_type': seat_type
            }
            seatid = carno_seatno_to_seatid(args, carno, seatno)
            conn.rollback()
            seat_lock = seat_locks.setdefault((tdate, tnumber), threading.Lock())
            seat_lock.acquire()
            if seat_type not in [0, 1, 2, 3]:
                seat_lock.release()
                abort(403)
            sql = f"""\
                SELECT SEATS{seat_type}
                FROM TRAIN_STOPS
                WHERE TDATE = %s AND TNUMBER = %s AND STOPNO BETWEEN %s AND %s
                ORDER BY STOPNO ASC
            """
            with conn.cursor() as cur:
                cur.execute(sql, (tdate, tnumber, begin_stopno, end_stopno))
                seats = cur.fetchall()
            for i in range(len(seats)):
                seats[i] = bytes_to_bitarray(seats[i][0])
            seat = bitarray(len(seats[0]))
            sql = f"""\
                UPDATE TRAIN_STOPS
                SET SEATS{seat_type} = %s
                WHERE TDATE = %s AND TNUMBER = %s AND STOPNO = %s
            """
            with conn.cursor() as cur:
                for i in range(len(seats)-1):
                    seats[i][seatid] = 0
                    cur.execute(sql, (seats[i].tobytes(), tdate, tnumber, int(begin_stopno)+i))
            sql = """\
                UPDATE ORDERS SET STATUS = 1
                WHERE ORDERNO = %s
            """
            with conn.cursor() as cur:
                cur.execute(sql, (orderno,))
                cur.callproc('CHANGE_BALANCE', (username, amount, 2, orderno))
            conn.commit()
            seat_lock.release()
            if userinfo['username'] == username:
                update_balance()
            session['order_search'] = {
                'username': username,
                'orderno': orderno
            }
            return redirect('/orders')
    update_balance()
    userinfo = session['userinfo']
    refund = session.get('refund', {})
    sql = """\
        SELECT
            ORDERNO,
            USERNAME,
            T_DEPARTURE_DATE,
            TNUMBER,
            BEGIN_STATION_NAME,
            END_STATION_NAME,
            DEPARTURE_TIME,
            ARRIVAL_TIME,
            DAY_DIFF,
            DURATION,
            CARNO,
            SEATNO,
            SEAT_TYPE,
            AMOUNT,
            ORDER_TIME,
            STATUS,
            HISTORY
        FROM VORDERS
        WHERE ORDERNO = %s
    """
    with conn.cursor() as cur:
        cur.execute(sql, (refund['orderno'],))
        order = cur.fetchone()
    return render_template('refund.html', userinfo=userinfo, rule=rule, order=order, order_status_name=order_status_name)
@app.route('/balance', methods=['GET', 'POST'])
def balance():
    if 'userinfo' not in session:
        return redirect('/')
    if request.method == 'POST':
        if 'clear' in request.form:
            session.pop('change_search', None)
        else:
            session['change_search'] = request.form
        return redirect('/balance')
    update_balance()
    userinfo = session['userinfo']
    change_search = session.setdefault('change_search', {})
    if userinfo['actype'] != 1:
        change_search['username'] = userinfo['username']
    if change_search.get('username'):
        sql = "SELECT BALANCE FROM ACCOUNTS WHERE USERNAME = %s"
        with conn.cursor() as cur:
            cur.execute(sql, (change_search['username'],))
            balance = cur.fetchone()[0]
    else:
        balance = None
    sql = "SELECT * FROM BALANCE_CHANGES"
    params = []
    first_param = True
    if change_search.get('username'):
        sql += f" {'WHERE' if first_param else 'AND'} USERNAME = %s"
        params.append(change_search['username'])
        first_param = False
    if change_search.get('changeno'):
        sql += f" {'WHERE' if first_param else 'AND'} CHANGENO = %s"
        params.append(change_search['changeno'])
        first_param = False
    if change_search.get('earliest_time'):
        sql += f" {'WHERE' if first_param else 'AND'} CHANGE_TIME >= %s"
        params.append(change_search['earliest_time'])
        first_param = False
    if change_search.get('latest_time'):
        sql += f" {'WHERE' if first_param else 'AND'} CHANGE_TIME <= %s"
        params.append(change_search['latest_time'])
        first_param = False
    if change_search.get('change_type', '-1') != '-1':
        sql += f" {'WHERE' if first_param else 'AND'} CHANGE_TYPE = %s"
        params.append(change_search['change_type'])
        first_param = False
    if change_search.get('min_amount'):
        sql += f" {'WHERE' if first_param else 'AND'} AMOUNT >= %s"
        params.append(change_search['min_amount'])
        first_param = False
    if change_search.get('max_amount'):
        sql += f" {'WHERE' if first_param else 'AND'} AMOUNT <= %s"
        params.append(change_search['max_amount'])
        first_param = False
    sql += " ORDER BY CHANGE_TIME DESC"
    with conn.cursor() as cur:
        cur.execute(sql, params)
        changes = cur.fetchall()
    return render_template('balance.html', userinfo=userinfo, change_search=change_search, changes=changes, balance=balance, change_type_name=change_type_name)
@app.route('/recharge', methods=['GET', 'POST'])
def recharge():
    if 'userinfo' not in session or session['userinfo']['actype'] != 1:
        return redirect('/')
    if request.method == 'POST':
        recharge = request.form
        sql = "SELECT ACTYPE FROM ACCOUNTS WHERE USERNAME = %s"
        with conn.cursor() as cur:
            cur.execute(sql, (recharge['username'],))
            actype = cur.fetchone()
        if not actype:
            return '要充值的用户不存在！'
        elif actype[0] == 1:
            return '管理员没有平台内部资金账户，不能充值！'
        with conn.cursor() as cur:
            cur.callproc('CHANGE_BALANCE', (recharge['username'], int(recharge['amount']), 0, None))
        session['change_search'] = {
            'username': recharge['username']
        }
        return redirect('/balance')
    userinfo = session['userinfo']
    return render_template('recharge.html', userinfo=userinfo)

if __name__ == '__main__':
    load_config()
    conn = mysql.connector.connect(**dict(zip(mysql_arg_names, mysql_args)))
    app.run(host=host, port=port)