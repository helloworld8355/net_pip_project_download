import socket
import threading
import os
import re

HOST = '0.0.0.0'
PORT = 12345
UPLOAD_DIR = 'uploads'

def parse_quoted(s):
    """提取所有被双引号包裹的参数，返回列表"""
    return re.findall(r'"([^"]*)"', s)

class Server:
    def __init__(self):
        self.clients = {}
        self.lock = threading.Lock()
        self.broadcast_perm = set()
        os.makedirs(UPLOAD_DIR, exist_ok=True)

    def broadcast(self, msg, sender=None):
        with self.lock:
            for user, c in self.clients.items():
                if sender is None or user != sender:
                    try:
                        c['conn'].sendall((msg + '\n').encode())
                    except:
                        pass

    def send_to(self, user, msg):
        with self.lock:
            if user in self.clients:
                try:
                    self.clients[user]['conn'].sendall((msg + '\n').encode())
                except:
                    pass

    def broadcast_userlist(self):
        with self.lock:
            users = ','.join(self.clients.keys())
        self.broadcast(f"USERLIST {users}")

    def handle_client(self, conn, addr):
        username = None
        try:
            conn.sendall("Welcome! Login with: LOGIN \"username\"\n".encode())
            data = conn.recv(1024).decode().strip()
            if data.startswith("LOGIN "):
                username = data[6:].strip().strip('"')
                if not username:
                    conn.sendall("ERROR Invalid username\n".encode())
                    conn.close()
                    return
                with self.lock:
                    if username in self.clients:
                        conn.sendall("ERROR Username already taken\n".encode())
                        conn.close()
                        return
                    self.clients[username] = {'conn': conn, 'addr': addr}
                print(f"[+] {username} connected from {addr}")
                conn.sendall("LOGIN_OK\n".encode())
                self.broadcast_userlist()
                self.broadcast(f"Server: {username} has joined the chat.")
            else:
                conn.sendall("ERROR Expected LOGIN\n".encode())
                conn.close()
                return

            while True:
                data = conn.recv(4096)
                if not data:
                    break
                for line in data.decode().split('\n'):
                    line = line.strip()
                    if not line:
                        continue
                    print(f"[{username}] {line}")

                    if line.startswith("MSG "):
                        parts = parse_quoted(line)
                        if len(parts) >= 2:
                            target, msg = parts[0], parts[1]
                            self.send_to(target, f"PRIVMSG {username}: {msg}")
                        else:
                            self.send_to(username, "ERROR MSG needs \"target\" \"message\"")
                    elif line.startswith("BROADCAST "):
                        parts = parse_quoted(line)
                        if parts:
                            msg = parts[0]
                            if username in self.broadcast_perm:
                                self.broadcast(f"BROADCAST_MSG {username}: {msg}", sender=username)
                                self.send_to(username, "BROADCAST_OK")
                            else:
                                self.send_to(username, "ERROR No broadcast permission")
                        else:
                            self.send_to(username, "ERROR BROADCAST needs \"message\"")
                    elif line.startswith("UPLOAD "):
                        parts = parse_quoted(line)
                        if len(parts) >= 2:
                            fname, fsize = parts[0], parts[1]
                            try:
                                fsize = int(fsize)
                            except:
                                self.send_to(username, "ERROR Invalid UPLOAD format")
                                continue
                            conn.sendall("READY\n".encode())
                            received = b''
                            while len(received) < fsize:
                                chunk = conn.recv(min(4096, fsize - len(received)))
                                if not chunk: break
                                received += chunk
                            if len(received) == fsize:
                                path = os.path.join(UPLOAD_DIR, f"{username}_{fname}")
                                with open(path, 'wb') as f:
                                    f.write(received)
                                conn.sendall("UPLOAD_OK\n".encode())
                                print(f"[File] {username} uploaded {fname} ({fsize} bytes)")
                            else:
                                conn.sendall("ERROR Upload incomplete\n".encode())
                        else:
                            self.send_to(username, "ERROR UPLOAD needs \"filename\" \"filesize\"")
                    elif line == "QUIT":
                        break
                    else:
                        conn.sendall("ERROR Unknown command\n".encode())
        except Exception as e:
            print(f"[!] Error with {username}: {e}")
        finally:
            if username:
                with self.lock:
                    if username in self.clients:
                        del self.clients[username]
                print(f"[-] {username} disconnected")
                self.broadcast(f"Server: {username} has left the chat.")
                self.broadcast_userlist()
            conn.close()

    def admin_console(self):
        print("Admin commands: broadcast \"msg\" | grant \"user\" | revoke \"user\" | kick \"user\" | users | quit")
        while True:
            cmd = input().strip()
            if cmd.startswith("broadcast "):
                parts = parse_quoted(cmd)
                if parts:
                    self.broadcast(f"BROADCAST_MSG Server: {parts[0]}")
                else:
                    print("Usage: broadcast \"message\"")
            elif cmd.startswith("grant "):
                parts = parse_quoted(cmd)
                if parts:
                    user = parts[0]
                    self.broadcast_perm.add(user)
                    self.send_to(user, "Server: You now have broadcast permission.")
                    print(f"Granted broadcast to {user}")
                else:
                    print("Usage: grant \"username\"")
            elif cmd.startswith("revoke "):
                parts = parse_quoted(cmd)
                if parts:
                    user = parts[0]
                    self.broadcast_perm.discard(user)
                    self.send_to(user, "Server: Broadcast permission revoked.")
                    print(f"Revoked broadcast from {user}")
                else:
                    print("Usage: revoke \"username\"")
            elif cmd.startswith("kick "):
                parts = parse_quoted(cmd)
                if parts:
                    user = parts[0]
                    with self.lock:
                        if user in self.clients:
                            self.send_to(user, "You have been kicked by admin.")
                            self.clients[user]['conn'].close()
                            del self.clients[user]
                            print(f"Kicked {user}")
                            self.broadcast(f"Server: {user} has been kicked.")
                            self.broadcast_userlist()
                        else:
                            print("User not online.")
                else:
                    print("Usage: kick \"username\"")
            elif cmd == "users":
                with self.lock:
                    print("Online:", list(self.clients.keys()))
            elif cmd == "quit":
                self.broadcast("Server: Shutting down")
                with self.lock:
                    for c in self.clients.values():
                        c['conn'].close()
                break
            else:
                print("Unknown command")

    def start(self):
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((HOST, PORT))
        server.listen(10)
        print(f"Server listening on {HOST}:{PORT}")
        threading.Thread(target=self.admin_console, daemon=True).start()
        try:
            while True:
                conn, addr = server.accept()
                threading.Thread(target=self.handle_client, args=(conn, addr), daemon=True).start()
        except KeyboardInterrupt:
            print("Server stopped.")
        finally:
            server.close()

if __name__ == '__main__':
    Server().start()
