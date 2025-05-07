from server_manager import server_manager as sm, lock
import socket
import traceback
import threading
server_socket = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
server_socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, False)

server_address = ('::', 8090)
server_socket.bind(server_address)
server_socket.listen(5)

def run(client_socket: socket.socket, client_address) -> None:
    try:
        self_sm = sm()
        print(f'已连接客户端：{client_address}。\n', end='')
        self_sm.io_mode = 1
        self_sm.client_socket = client_socket
        self_sm.main()
    except Exception as e:
        traceback.print_exc()
    finally:
        client_socket.close()
        if lock.locked():
            lock.release()
        print(f'与客户端{client_address}的连接已断开。\n', end='')

while True:
    print(f'服务器正在监听{server_address}……\n', end='')
    client_socket, client_address = server_socket.accept()
    thread = threading.Thread(target=run, args=(client_socket, client_address))
    thread.start()