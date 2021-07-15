#!/usr/bin/env python3
# -*- coding: UTF-8 -*-

"""
webserver script
"""
import machine
import socket
import sys
import time
import ubinascii
import uos


class WebServer:
    def __init__(self, user, password, port=80, maximum_connections=10):
        self._sock = None
        self._run = False
        self._user = user
        self._password = password
        self._port = port
        self._maximum_connections = maximum_connections
        self._is_active = False

    def get_status(self):
        return self._is_active

    def stop(self):
        print('Stopping WebServer ...')

        try:
            self._run = False
            self._sock.close()
        except Exception as e:
            print('Failed to stop webserver due to {}'.format(e))

        print('WebServer stopped')

    def start(self):
        try:
            self.stop()
            self._run = True
            self._sock = socket.socket()
            self._sock.bind(('0.0.0.0', self._port))
            self._sock.listen(self._maximum_connections)
            self._is_active = True
        except Exception as e:
            print('Failed to start webserver due to {}'.format(e))

    def _split(self, line, split_char):
        return line.decode().strip().split(split_char)

    def process(self, accept_timeout):
        client_sock = None
        f = None
        try:
            self._sock.settimeout(accept_timeout)
            client_sock, client_addr = self._sock.accept()

            if not client_sock:
                return

            print('WebServer - connection from {}'.format(client_addr))

            client_sock.settimeout(0.3)

            first_line = client_sock.readline()
            if not first_line:
                client_sock.close()
                return

            parts = self._split(first_line, ' ')
            req_method = parts[0].upper()
            req_path = parts[1].lower()

            req_auth = None
            while True:
                line = client_sock.readline()

                if not line:
                    break

                parts = self._split(line, ':')

                if len(parts) < 2:
                    break
                if parts[0].lower() == 'authorization':
                    req_auth = parts[1].strip().split()[1]

            if req_auth:
                user_pass = ubinascii.a2b_base64(req_auth).decode().split(':')
            else:
                user_pass = None

            if ((not user_pass) or
               (user_pass[0] != self._user) or
               (user_pass[1] != self._password)):
                if user_pass:
                    print('WebServer - access attempt from {}'.
                          format(client_addr))

                client_sock.send('HTTP/1.1 401 Unauthorized\r\n')
                client_sock.send('WWW-Authenticate: Basic realm="Device Config"\r\n\r\n')
                client_sock.close()
                return

            print('WebServer - request from: {} of type {} to {}'.
                  format(client_addr, req_method, req_path))

            if req_path == '/config' or req_path == '/config-network':
                filename = "{}.py".format(req_path.strip('/'))

                if req_method == 'POST':
                    state = 0
                    while True:
                        line = client_sock.readline()

                        if not line:
                            break

                        line = line.decode().strip()

                        if state == 0:
                            if ((line.startswith('Content-Disposition: ')) and
                               (line.endswith('filename="{}"'.
                                              format(filename)))):
                                state = 1
                        elif state == 1:
                            if line == '':
                                state = 2
                                f = open('{}.tmp'.format(filename), 'wb')
                        elif state == 2:
                            if line.startswith('--'):
                                f.close()
                                state = 3
                                try:
                                    uos.remove(filename)
                                except Exception as e:
                                    print('Failed to remove "{}" due to {}'.
                                          format(filename, e))
                                state = 4
                                uos.rename('{}.tmp'.format(filename), filename)
                                state = 5
                                break

                            f.write(line)
                            f.write('\n')

                    # readall is not a valid attribute for socket
                    # client_sock.readall()

                    client_sock.send('HTTP/1.1 303 See Other\r\n')
                    client_sock.send('Location: /?state={}\r\n'.format(state))
                    client_sock.send('Content-Type: text/html\r\n\r\n')

                    # reboot if network config changed
                    if (state == 5) and (req_path == '/config-network'):
                        print('Config uploaded - restarting in 3 sec ...')
                        time.sleep(3)
                        machine.reset()
                else:
                    # on GET
                    client_sock.send('HTTP/1.1 200 OK\r\n')
                    client_sock.send('Connection: close\r\n')

                    try:
                        stat = uos.stat(filename)
                        client_sock.send('Content-Disposition: attachment; filename={}\r\n'.format(filename))
                        client_sock.send('Content-Type: application/force-download\r\n')
                        client_sock.send('Content-Transfer-Encoding: binary\r\n')
                        client_sock.send('Content-Length: {}\r\n\r\n'.
                                         format(stat[6]))
                        f = open(filename, 'rb')
                        client_sock.send(f.read())
                    except Exception as e:
                        client_sock.send('Content-Type: text/html\r\n\r\n')
                        client_sock.send('Not configured')
            elif req_path == '/favicon.ico':
                client_sock.send('HTTP/1.1 404 Not Found\r\n')
                client_sock.send('Connection: close\r\n\r\n')
            else:
                client_sock.send('HTTP/1.1 200 OK\r\n')
                client_sock.send('Connection: close\r\n')
                client_sock.send('Content-Type: text/html\r\n')
                stat = uos.stat("index.html")
                client_sock.send('Content-Length: {}\r\n\r\n'.format(stat[6]))
                f = open('index.html', 'rb')
                client_sock.send(f.read())
        except OSError as e:
            if e.args[0] != 11:     # 11 = timeout expired
                print("WebServer - OSError: {}".format(e))
                sys.print_exception(e)
        except Exception as e:
            if self._run:
                print("WebServer - process error: {}".format(e))
                sys.print_exception(e)
            else:
                print("WebServer - process stopped")

        try:
            f.close()
        except Exception:
            pass

        try:
            client_sock.close()
        except Exception:
            pass
