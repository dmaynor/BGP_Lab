#!/usr/bin/env python3
# MIT License
#
# Copyright (c) 2024 BGP Lab contributors
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

"""
Simple TCP/UDP probe tool for BGP lab visibility.

Modes:
    listen:
        Runs both UDP and TCP listeners and logs incoming packets.

    send:
        Sends UDP datagrams and TCP packets to a target.

Usage:
    # Listen
    python3 netprobe.py listen --bind 0.0.0.0 --udp-port 5000 --tcp-port 5000

    # Send packets
    python3 netprobe.py send --target 10.10.1.200 --udp-port 5000 --tcp-port 5000
"""

import argparse
import socket
import threading
import time
from typing import Optional


def log(msg: str) -> None:
    now = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    print(f"[{now}] {msg}", flush=True)


def udp_listener(bind: str, port: int) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((bind, port))
    log(f"UDP listener on {bind}:{port}")
    while True:
        data, addr = sock.recvfrom(2048)
        log(f"UDP from {addr[0]}:{addr[1]} -> {bind}:{port} | {len(data)} bytes | {data[:50]!r}")


def tcp_listener(bind: str, port: int) -> None:
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((bind, port))
    server.listen(8)
    log(f"TCP listener on {bind}:{port}")

    while True:
        conn, addr = server.accept()
        log(f"TCP connection from {addr[0]}:{addr[1]}")
        data = conn.recv(2048)
        log(f"TCP data from {addr[0]}:{addr[1]} | {len(data)} bytes | {data[:50]!r}")
        conn.close()


def run_listeners(bind: str, udp_port: int, tcp_port: int) -> None:
    threading.Thread(target=udp_listener, args=(bind, udp_port), daemon=True).start()
    threading.Thread(target=tcp_listener, args=(bind, tcp_port), daemon=True).start()
    log(f"Listening on UDP {udp_port} and TCP {tcp_port} ...")
    while True:
        time.sleep(3600)


def send_udp(target: str, port: int, msg: str, sock: Optional[socket.socket] = None):
    close = False
    if sock is None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        close = True
    data = msg.encode()
    sock.sendto(data, (target, port))
    log(f"Sent UDP to {target}:{port} | {len(data)} bytes | {msg!r}")
    if close:
        sock.close()


def send_tcp(target: str, port: int, msg: str):
    data = msg.encode()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(2)
    try:
        sock.connect((target, port))
        sock.sendall(data)
        log(f"Sent TCP to {target}:{port} | {len(data)} bytes | {msg!r}")
    except Exception as e:
        log(f"TCP error to {target}:{port}: {e}")
    finally:
        sock.close()


def send_probes(target: str, udp_port: int, tcp_port: int, count: int, interval: float):
    udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    for i in range(1, count + 1):
        send_udp(target, udp_port, f"NETPROBE UDP seq={i}", udp_sock)
        send_tcp(target, tcp_port, f"NETPROBE TCP seq={i}")
        time.sleep(interval)
    udp_sock.close()
    log("Probe sending complete")


def parse_args():
    p = argparse.ArgumentParser(description="Simple TCP/UDP probe tool for BGP lab")
    sub = p.add_subparsers(dest="cmd", required=True)

    L = sub.add_parser("listen", help="Run TCP + UDP listeners")
    L.add_argument("--bind", default="0.0.0.0")
    L.add_argument("--udp-port", type=int, default=5000)
    L.add_argument("--tcp-port", type=int, default=5000)

    S = sub.add_parser("send", help="Send TCP + UDP probes")
    S.add_argument("--target", required=True)
    S.add_argument("--udp-port", type=int, default=5000)
    S.add_argument("--tcp-port", type=int, default=5000)
    S.add_argument("--count", type=int, default=10)
    S.add_argument("--interval", type=float, default=1.0)

    return p.parse_args()


def main():
    args = parse_args()
    if args.cmd == "listen":
        run_listeners(args.bind, args.udp_port, args.tcp_port)
    elif args.cmd == "send":
        send_probes(args.target, args.udp_port, args.tcp_port, args.count, args.interval)


if __name__ == "__main__":
    main()

