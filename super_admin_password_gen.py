import mysql.connector
import getpass
import bcrypt

mysql_arg_names = ['user', 'host', 'password', 'database']
mysql_args = [
    'local-web-server-user',
    '::1',
    'eadd5a759647ac9139e0564abf97496b6e2f12238d43a5185a8c321f16434a94',
    '010_TRAIN_TICKETING'
]
with open('config.ini', 'r', encoding='UTF-8') as file:
    for line in file:
        args = line.split()
        if args[0] == 'mysql':
            mysql_args = args[1:]
            break
conn = mysql.connector.connect(**dict(zip(mysql_arg_names, mysql_args)))

password = getpass.getpass("请输入超级管理员密码: ")
hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

with conn.cursor() as cur:
    cur.execute("DELETE FROM SUPER_ADMIN_PASSWORD")
    cur.execute("INSERT INTO SUPER_ADMIN_PASSWORD VALUES (%s)", (hashed_password,))
conn.commit()

print("超级管理员密码已成功设置！")

conn.close()
