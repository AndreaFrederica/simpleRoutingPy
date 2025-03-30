# encoding:utf-8
import time
import struct
import socket
import select
import os
from typing import Tuple


def check_sum(data: bytes) -> int:
    """
    计算给定数据的 ICMP 校验和。

    参数:
        data (bytes): 用于计算校验和的数据。

    返回:
        int: 计算得到的16位校验和值。
    """
    n = len(data)
    m = n % 2
    sum_val = 0
    for i in range(0, n - m, 2):
        sum_val += data[i] + (data[i + 1] << 8)
    if m:
        sum_val += data[-1]
    sum_val = (sum_val >> 16) + (sum_val & 0xFFFF)
    sum_val += sum_val >> 16
    answer = ~sum_val & 0xFFFF
    answer = (answer >> 8) | ((answer << 8) & 0xFF00)
    return answer


def request_ping(
    data_type: int,
    data_code: int,
    data_checksum: int,
    data_ID: int,
    data_Sequence: int,
    payload_body: bytes,
) -> bytes:
    """
    构造一个 ICMP Echo Request 包，并计算正确的校验和。

    参数:
        data_type (int): ICMP 类型（通常为 8 表示 Echo Request）。
        data_code (int): ICMP 代码（通常为 0）。
        data_checksum (int): 初始校验和值（计算前为 0）。
        data_ID (int): 标识符字段。
        data_Sequence (int): 序列号。
        payload_body (bytes): 数据载荷，通常为 32 字节。

    返回:
        bytes: 构造好的 ICMP 包，可直接发送。
    """
    # 初次打包，校验和字段设为 0
    icmp_packet = struct.pack(
        ">BBHHH32s",
        data_type,
        data_code,
        data_checksum,
        data_ID,
        data_Sequence,
        payload_body,
    )
    icmp_checksum = check_sum(icmp_packet)
    # 使用正确的校验和重新打包
    icmp_packet = struct.pack(
        ">BBHHH32s",
        data_type,
        data_code,
        icmp_checksum,
        data_ID,
        data_Sequence,
        payload_body,
    )
    return icmp_packet


def create_raw_socket() -> socket.socket:
    """
    创建一个用于发送 ICMP 数据包的原始套接字。

    返回:
        socket.socket: 创建好的原始套接字对象。
    """
    return socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.getprotobyname("icmp"))


def send_ping(raw_socket: socket.socket, dst_addr: str, icmp_packet: bytes) -> float:
    """
    发送 ICMP 包并返回发送的时间戳。

    参数:
        raw_socket (socket.socket): 用于发送数据的原始套接字。
        dst_addr (str): 目标 IP 地址。
        icmp_packet (bytes): 待发送的 ICMP 包。

    返回:
        float: 数据包发送时的时间戳。
    """
    send_time = time.perf_counter()
    raw_socket.sendto(icmp_packet, (dst_addr, 0))
    return send_time


def reply_ping(
    raw_socket: socket.socket, send_time: float, expected_seq: int, timeout: float = 2
) -> float:
    """
    等待接收 ICMP 回复并计算往返时间。

    参数:
        raw_socket (socket.socket): 用于接收数据的原始套接字。
        send_time (float): 发送数据包的时间戳。
        expected_seq (int): 期望回复的序列号。
        timeout (float): 超时时间，单位为秒，默认2秒。

    返回:
        float: 若成功接收到回复，则返回往返时间（秒）；否则返回 -1。
    """
    time_left = timeout
    while time_left > 0:
        start_select = time.perf_counter()
        ready = select.select([raw_socket], [], [], time_left)
        duration = time.perf_counter() - start_select
        if not ready[0]:
            return -1
        recv_time = time.perf_counter()
        rec_packet, addr = raw_socket.recvfrom(1024)
        icmp_header = rec_packet[20:28]
        type_field, code, checksum, packet_id, sequence = struct.unpack(">BBHHH", icmp_header)
        if type_field == 0 and sequence == expected_seq:
            return recv_time - send_time
        time_left -= duration
    return -1


def ping(host: str) -> None:
    """
    对指定主机发送4个 ICMP Echo Request，并打印统计信息。

    参数:
        host (str): 要 ping 的主机名或 IP 地址。

    返回:
        None
    """
    try:
        dst_addr = socket.gethostbyname(host)
    except socket.gaierror as e:
        print(f"无法解析主机 {host}: {e}")
        return

    print(f"正在 Ping {host} [{dst_addr}] 具有 32 字节的数据:")

    # 使用当前进程ID作为标识符
    data_ID = os.getpid() & 0xFFFF
    data_type = 8  # ICMP Echo Request
    data_code = 0  # 必须为0
    data_checksum = 0  # 校验和初始值为0
    data_Sequence = 1
    payload_body = b"abcdefghijklmnopqrstuvwabcdefghi"  # 32字节载荷

    # 创建单个原始套接字
    try:
        raw_sock = create_raw_socket()
    except PermissionError:
        print("需要管理员权限运行此程序")
        return

    sent = 0
    received = 0
    rtt_list = []

    for i in range(4):
        seq = data_Sequence + i
        icmp_packet = request_ping(
            data_type, data_code, data_checksum, data_ID, seq, payload_body
        )
        send_time = send_ping(raw_sock, dst_addr, icmp_packet)
        sent += 1
        rtt = reply_ping(raw_sock, send_time, seq, timeout=2)
        if rtt >= 0:
            rtt_ms = int(rtt * 1000)
            print(f"来自 {dst_addr} 的回复: 字节=32 时间={rtt_ms}ms")
            received += 1
            rtt_list.append(rtt_ms)
        else:
            print("请求超时。")
        time.sleep(0.7)

    # 统计信息
    lost = sent - received
    loss_percent = (lost / sent) * 100
    if rtt_list:
        min_rtt = min(rtt_list)
        max_rtt = max(rtt_list)
        avg_rtt = sum(rtt_list) / len(rtt_list)
    else:
        min_rtt = max_rtt = avg_rtt = 0
    print(f"\n{dst_addr} 的 Ping 统计信息:")
    print(
        f"    数据包: 已发送 = {sent}, 已接收 = {received}, 丢失 = {lost} ({loss_percent:.1f}% 丢失)"
    )
    print("往返行程的估计时间(以毫秒为单位):")
    print(f"    最短 = {min_rtt}ms, 最长 = {max_rtt}ms, 平均 = {avg_rtt:.1f}ms")


if __name__ == "__main__":
    host_input = input("请输入要ping的主机或域名\n")
    ping(host_input)
