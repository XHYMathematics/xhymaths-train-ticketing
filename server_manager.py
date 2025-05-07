import train_ticketing as tt
import subprocess
import requests
import time
import threading

command_format = [
    ('help', '显示此帮助信息'),
    ('help-config', '显示Web应用配置文件格式'),
    ('status', '查看Web服务器状态'),
    ('start', '启动Web服务器'),
    ('stop', '关闭Web服务器'),
    ('restart', '重启Web服务器'),
    ('exit', '退出服务器管理器'),
    ('show-config', '显示Web应用配置信息'),
    ('set-config', '更新Web应用配置文件'),
    ('show-log [x]', '显示最近的x行日志（默认10行）')
]
flask_config_format = [
    ('host x', '将Web服务器监听地址设为x'),
    ('port x', '将Web服务器监听端口设为x'),
    ('debug x', '将Flask应用的debug属性设为x'),
]
msyql_config_format = [
    ('mysql user host password database', '将连接MySQL数据库的用户名、主机名/IP地址、密码、数据库名分别设为user、host、password、database。')
]
ticket_rule_format = [
    ('unit-price x', '将车票单价设为x（单位：元/公里）。'),
    ('set-train-prices str1 p', '将车次号开头字符为str中的任何一个字符的车次的价格系数设为p。'),
    ('seat-prices a b c d e f', '将硬/二等座价格倍数、软/一等座价格倍数、硬/二等卧铺位费、硬/二等卧价格倍数、软/一等卧铺位费、软/一等卧价格倍数分别设为a, b, c, d, e, f（座位的最终价格为：车次号开头字符对应的价格系数*里程*单价*座位类型对应的价格倍数，铺位的最终价格为：车次号开头字符对应的价格系数*(铺位类型对应的铺位费+里程*单价*铺位类型对应的价格倍数)）。'),
    ('set-seat-names str a b c d', '将车次号开头字符为str中的任何一个字符的车次的硬/二等座、软/一等座、硬/二等卧、软/一等卧的具体名称分别设为a, b, c, d。')
]

def str_help(help_list: list, prompt: str = '', newline: bool = False) -> str:
    s = ''
    max_len = max([len(item[0]) for item in help_list]) + 1
    for i in range(len(help_list)):
        if newline:
            s += help_list[i][0] + '：'
        else:
            s += help_list[i][0].ljust(max_len) + '：'
        if newline:
            s += '\n    '
        s += help_list[i][1] + '\n'
        if newline and i != len(help_list) - 1:
            s += '\n'
    return prompt + '\n' + s
def _status() -> tuple:
    response = None
    try:
        response = requests.get('http://[::1]:' + str(tt.port) + '/status')
    except Exception as e:
        return 2, '无法访问服务器，错误如下：\n' + str(e)
    if response.text == "XHYMaths' Train Ticketing System":
        return 0, '服务器运行正常。'
    else:
        return 1, '服务器返回了响应，但响应内容有误，内容如下：\n' + response.text
def str_status(stat: tuple) -> str:
    prompt = '服务器当前状态为：\n'
    return prompt + stat[1]
def _start() -> tuple:
    if _status()[0] == 0:
        return -1, '服务器正在运行，无需启动。'
    try:
        tt.load_config()
        subprocess.Popen(['python', tt.app_path])
    except Exception as e:
        return 2, '服务器进程启动失败，错误如下：\n' + str(e)
    stat = _status()
    if stat[0] == 0:
        return 0, '服务器启动成功。'
    else:
        return 1, '已尝试启动服务器进程，但服务器状态异常。\n' + str_status(stat)
def _stop() -> tuple:
    stat = _status()
    if _status()[0] != 0:
        return 1, '服务器不是正常运行状态，请先检查服务器状态再试。\n' + str_status(stat)
    try:
        requests.post('http://[::1]:' + str(tt.port) + '/exit', data={'password': tt.password})
    except Exception as e:
        pass
    return 0, '已尝试向服务器发送关闭请求。'
def _config() -> str:
    s = ''
    with open(tt.config_path, 'r', encoding='UTF-8') as file:
        for line in file:
            if line:
                s += line
    return s

lock = threading.Lock()

class server_manager:
    def help(self) -> None:
        self.output(str_help(command_format, '命令列表：'))
    def help_config(self) -> None:
        s = ''
        s += str_help(flask_config_format, '配置文件格式：')
        s += str_help(msyql_config_format, newline=True)
        s += str_help(ticket_rule_format, newline=True)
        self.output(s)
    def status(self) -> None:
        self.output(str_status(_status()))
    def start(self) -> None:
        self.output(_start()[1])
    def stop(self) -> None:
        res_stop = _stop()
        self.output(res_stop[1])
        if res_stop[0] == 0:
            time.sleep(0.1)
            stat = _status()
            if stat[0] == 0:
                self.output('服务器现在仍可访问，可能是延迟问题，可稍后再试。')
            elif stat[0] == 2:
                self.output('服务器现在已不可访问，预计其已关闭成功。')
            else:
                self.output(stat[1])
    def restart(self) -> None:
        res_stop = _stop()
        if res_stop[0] == 0:
            time.sleep(0.1)
            res_start = _start()
        else:
            res_start = _start()
        if res_stop[0] == 0:
            if res_start[0] == 0:
                self.output('服务器重启成功。')
            else:
                self.output('已尝试向服务器发送关闭请求，但启动失败，启动失败原因如下：\n' + res_start[1])
        else:
            if res_start[0] == 0:
                self.output('服务器之前不是正常运行状态，但现在已成功启动。')
            else:
                self.output('服务器之前不是正常运行状态，已尝试启动，但启动失败，启动失败原因如下：\n' + res_start[1])
    def show_config(self) -> None:
        try:
            self.output(_config())
        except Exception as e:
            self.output('配置文件读取失败，错误如下：\n' + str(e))
    def set_config(self) -> None:
        self.output('当前配置文件内容为：')
        config = _config()
        if config[-1] != '\n':
            config += '\n'
        self.output(config)
        self.output('接下来请在多行内输入整个配置文件的内容，输入结束后请在一行内输入":::"（不含引号）以结束输入。')
        self.output('如输入错误，请在一行内输入";;;"（不含引号）以放弃本次输入，放弃输入后将不会修改配置文件。')
        s = ''
        while True:
            line = self.read()
            i = len(line)
            while i > 0 and (line[i-1] == '\n' or line[i-1] == '\r'):
                i -= 1
            line = line[:i]
            if line == ':::':
                break
            elif line == ';;;':
                self.output('已放弃本次输入。')
                return
            else:
                s += line + '\n'
        try:
            with open(tt.config_path, 'w', encoding='UTF-8') as file:
                file.write(s)
        except Exception as e:
            self.output('配置文件写入失败，错误如下：\n' + str(e))
            return
        self.output('配置文件已更新。')
        if _status()[0] == 0:
            response = requests.post('http://[::1]:' + str(tt.port) + '/reload', data={'password': tt.password})
            if response.text == 'Reloaded successfully.':
                self.output('Web服务器已重新加载配置文件。')
            else:
                self.output('Web服务器重新加载配置文件失败，请尝试重启服务器以加载新的配置文件。')
        else:
            tt.load_config()
    def show_log(self, linenum: int = 10) -> None:
        result = subprocess.run(['tail', '-n', str(linenum), tt.log_path], capture_output=True, text=True)
        self.output(result.stdout)
    
    def __init__(self):
        self.io_mode = 0
        self.client_socket = None
        self.command = {
            'help': self.help,
            'help-config': self.help_config,
            'status': self.status,
            'start': self.start,
            'stop': self.stop,
            'restart': self.restart,
            'show-config': self.show_config,
            'set-config': self.set_config,
        }

    def read(self, prompt: str = '') -> str:
        if self.io_mode == 1:
            self.client_socket.sendall(prompt.encode('utf-8'))
            return self.client_socket.recv(4096).decode('utf-8')
        else:
            return input(prompt)
    def output(self, s: str) -> None:
        if self.io_mode == 1:
            self.client_socket.sendall((s+'\n').encode('utf-8'))
        else:
            print(s)

    def main(self):
        try:
            self.output('XHYMaths铁路售票系统服务器管理器')
            self.help()
            while True:
                line = self.read('> ')
                line = line.split()
                if not line:
                    continue
                if line[0] == 'exit':
                    self.output('服务器管理器已退出。')
                    break
                if not lock.acquire(blocking=False):
                    self.output('其他线程正在执行命令，请稍后再试。')
                    continue
                if line[0] == 'show-log':
                    if len(line) == 1:
                        self.show_log()
                    else:
                        self.show_log(line[1])
                elif line[0] not in self.command:
                    self.output('未知命令！')
                    self.help()
                else:
                    self.command[line[0]]()
                lock.release()
        except KeyboardInterrupt:
            self.output('\n服务器管理器已退出。')

if __name__ == "__main__":
    sm = server_manager()
    sm.main()