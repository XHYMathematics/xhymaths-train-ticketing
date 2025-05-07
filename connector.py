import socket
import sys
import os
import textwrap
import threading

client_socket = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
client_socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, False)

if len(sys.argv) == 1:
    try:
        s = input('请输入要连接的服务器主机名或IP地址、端口号，中间用空格隔开: \n').split()
        server_address = s[0], int(s[1])
    except KeyboardInterrupt:
        exit()
elif len(sys.argv) == 3:
    server_address = sys.argv[1], int(sys.argv[2])
else:
    print(textwrap.dedent('''\
        命令格式错误！
        命令格式为：
        python [...] connector.py [<主机名或IP地址> <端口号>]
    '''), end='')
    exit()

def receive() -> None:
    try:
        while True:
            data = client_socket.recv(4096)
            if data:
                print(data.decode('utf-8'), end='', flush=True)
            else:
                break
    except:
        pass
    finally:
        print('与服务器的连接已断开。')
        client_socket.close()
        os._exit(0)

print(f'正在连接服务器{server_address}……')
client_socket.connect(server_address)
print(f'已连接到服务器{server_address}。')
thread = threading.Thread(target=receive)
thread.start()

try:
    while True:
        s = input()
        client_socket.send((s+'\n').encode('utf-8'))
except:
    pass
finally:
    client_socket.close()