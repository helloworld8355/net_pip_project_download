import socket
import threading
import sys
import re

PORT = 12345

def parse_quoted(s):
    return re.findall(r'"([^"]*)"', s)

class Client:
    def __init__(self, host):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((host, PORT))
        self.running = True

    def recv_loop(self):
        buf = ""
        while self.running:
            try:
                data = self.sock.recv(4096)
                if not data:
                    print("\n[!] Disconnected from server.")
                    self.running = False
                    break
                buf += data.decode()
                while '\n' in buf:
                    line, buf = buf.split('\n', 1)
                    self.handle_msg(line.strip())
            except:
                break

    def handle_msg(self, msg):
        if msg.startswith("USERLIST "):
            users = msg[9:].split(',') if msg[9:] else []
            print(f"\n[Online] {', '.join(users)}")
        elif msg.startswith("PRIVMSG "):
            content = msg[8:]
            if ': ' in content:
                src, text = content.split(': ', 1)
                print(f"\n[Private from {src}] {text}")
            else:
                print(f"\n[Private] {content}")
        elif msg.startswith("BROADCAST_MSG "):
            content = msg[14:]
            if ': ' in content:
                src, text = content.split(': ', 1)
                print(f"\n[Broadcast from {src}] {text}")
            else:
                print(f"\n[Broadcast] {content}")
        elif msg.startswith("BROADCAST_OK"):
            print("\n[Server] Broadcast sent.")
        elif msg.startswith("UPLOAD_OK"):
            print(f"\n[Server] {msg}")
        elif msg.startswith("ERROR "):
            print(f"\n[Error] {msg[6:]}")
        else:
            print(f"\n{msg}")

    def send_cmd(self, cmd):
        try:
            self.sock.sendall((cmd + '\n').encode())
        except:
            self.running = False

    def input_loop(self):
        print("Commands:\n"
              "  /to \"username\" \"message\"\n"
              "  /broadcast \"message\"\n"
              "  /upload \"filepath\"\n"
              "  /quit")
        while self.running:
            try:
                inp = input()
            except (KeyboardInterrupt, EOFError):
                break
            if not self.running: break
            if not inp: continue

            if inp.startswith("/to "):
                parts = parse_quoted(inp)
                if len(parts) >= 2:
                    self.send_cmd(f"MSG {parts[0]} {parts[1]}")
                else:
                    print("Usage: /to \"username\" \"message\"")
            elif inp.startswith("/broadcast "):
                parts = parse_quoted(inp)
                if parts:
                    self.send_cmd(f"BROADCAST {parts[0]}")
                else:
                    print("Usage: /broadcast \"message\"")
            elif inp.startswith("/upload "):
                parts = parse_quoted(inp)
                if parts:
                    path = parts[0]
                    try:
                        with open(path, 'rb') as f:
                            data = f.read()
                        fname = path.replace('\\', '/').split('/')[-1]
                        # 文件大小以字符串发送，服务端会用引号提取
                        self.sock.sendall(f'UPLOAD "{fname}" "{len(data)}"\n'.encode())
                        self.sock.sendall(data)
                        print(f"[Uploading] {fname} ({len(data)} bytes)...")
                    except FileNotFoundError:
                        print("File not found.")
                else:
                    print("Usage: /upload \"filepath\"")
            elif inp == "/quit":
                self.send_cmd("QUIT")
                self.running = False
                break
            else:
                print("Unknown command.")

    def run(self):
        name = input("Enter username (no quotes needed): ")
        self.send_cmd(f"LOGIN {name}")
        threading.Thread(target=self.recv_loop, daemon=True).start()
        self.input_loop()
        self.sock.close()
        print("Goodbye.")

if __name__ == '__main__':
    host = sys.argv[1] if len(sys.argv) > 1 else '127.0.0.1'
    Client(host).run()
