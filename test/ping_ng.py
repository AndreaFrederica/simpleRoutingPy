# encoding:utf-8
import asyncio
import time
import struct
import socket
import select
import os
import platform
import argparse
import logging
from typing import Optional, TypedDict


class PingStats(TypedDict):
    host: str
    dst_addr: str
    sent: int
    received: int
    lost: int
    loss_percent: float
    min_rtt: float
    max_rtt: float
    avg_rtt: float
    rtt_list: list[float]


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
        float: 数据包发送时的时间戳（使用 time.perf_counter()）。
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

def ping(
    host: str,
    count: int = 4,
    payload: bytes = b"abcdefghijklmnopqrstuvwabcdefghi",
    delay: float = 0.7,
    iface: str | None = None,
    quiet: bool = False
) -> None:
    """
    对指定主机发送 ICMP Echo Request，并打印统计信息。

    参数:
        host (str): 要 ping 的主机名或 IP 地址。
        count (int): 发送的 ICMP 包数量；若为 0 则无限发送，直到用户中断。
        payload (bytes): ICMP 数据包的负载数据。
        delay (float): 每个包发送后的延时，单位为秒。
        iface (str|None): 指定使用的网络接口（如 "eth0"），仅在支持的系统上有效；
                          在 Windows 上不支持该功能，会发出警告并忽略此参数。
        quiet (bool): 是否关闭日志输出（True 表示关闭），用于最大化发送速度。

    返回:
        None
    """
    try:
        dst_addr = socket.gethostbyname(host)
    except socket.gaierror as e:
        logging.error(f"无法解析主机 {host}: {e}")
        return

    logging.info(f"正在 Ping {host} [{dst_addr}] 具有 {len(payload)} 字节的数据:")

    data_ID = os.getpid() & 0xFFFF
    data_type = 8         # ICMP Echo Request
    data_code = 0         # 必须为0
    data_checksum = 0     # 校验和初始值为0
    data_Sequence = 1

    try:
        raw_sock = create_raw_socket()
    except PermissionError:
        logging.error("需要管理员权限运行此程序")
        return

    if iface:
        if platform.system() == "Windows":
            logging.warning("警告: Windows平台不支持指定网络接口功能，将忽略 iface 参数。")
        else:
            try:
                raw_sock.setsockopt(socket.SOL_SOCKET, 25, iface.encode('utf-8'))
            except Exception as e:
                logging.error(f"设置网络接口 {iface} 失败: {e}")

    sent = 0
    received = 0
    rtt_list = []
    iteration = 0

    try:
        while count == 0 or iteration < count:
            seq = data_Sequence + iteration
            icmp_packet = request_ping(data_type, data_code, data_checksum, data_ID, seq, payload)
            send_time = send_ping(raw_sock, dst_addr, icmp_packet)
            sent += 1
            rtt = reply_ping(raw_sock, send_time, seq, timeout=2)
            if rtt >= 0:
                logging.info(f"来自 {dst_addr} 的回复: 字节={len(payload)} 时间={rtt*1000:.2f}ms")
                received += 1
                rtt_list.append(rtt * 1000)
            else:
                logging.info("请求超时。")
            iteration += 1
            if delay != 0:
                time.sleep(delay)
    except KeyboardInterrupt:
        logging.info("\n用户中断。")

    lost = sent - received
    loss_percent = (lost / sent) * 100
    if rtt_list:
        min_rtt = min(rtt_list)
        max_rtt = max(rtt_list)
        avg_rtt = sum(rtt_list) / len(rtt_list)
    else:
        min_rtt = max_rtt = avg_rtt = 0.0
    logging.info(f"\n{dst_addr} 的 Ping 统计信息:")
    logging.info(f"    数据包: 已发送 = {sent}, 已接收 = {received}, 丢失 = {lost} ({loss_percent:.1f}% 丢失)")
    logging.info("往返行程的估计时间(以毫秒为单位):")
    logging.info(f"    最短 = {min_rtt:.2f}ms, 最长 = {max_rtt:.2f}ms, 平均 = {avg_rtt:.2f}ms")

def ping_with_return(
    host: str,
    count: int = 4,
    payload: bytes = b"abcdefghijklmnopqrstuvwabcdefghi",
    delay: float = 0.7,
    iface: Optional[str] = None,
    quiet: bool = False,
) -> PingStats:
    """
    对指定主机发送 ICMP Echo Request，并返回统计信息的字典。

    返回字典包含如下键：
        - host: 用户输入的主机名
        - dst_addr: 解析得到的目标 IP 地址
        - sent: 发送的包数量
        - received: 接收到的包数量
        - lost: 丢失的包数量
        - loss_percent: 丢包百分比
        - min_rtt: 最小往返时间（毫秒）
        - max_rtt: 最大往返时间（毫秒）
        - avg_rtt: 平均往返时间（毫秒）
        - rtt_list: 每个成功接收包的往返时间列表（毫秒）

    参数:
        host (str): 要 ping 的主机名或 IP 地址。
        count (int): 发送的 ICMP 包数量；若为 0 则无限发送，直到用户中断。
        payload (bytes): ICMP 数据包的负载数据。
        delay (float): 每个包发送后的延时，单位为秒。
        iface (str|None): 指定使用的网络接口（如 "eth0"），仅在支持的系统上有效；
                          在 Windows 上不支持该功能，会发出警告并忽略此参数。
        quiet (bool): 是否关闭日志输出（True 表示关闭）。

    返回:
        PingStats: 包含统计信息的字典。
    """
    try:
        dst_addr = socket.gethostbyname(host)
    except socket.gaierror as e:
        err_msg = f"无法解析主机 {host}: {e}"
        if not quiet:
            logging.error(err_msg)
        return PingStats(
            host=host,
            dst_addr="",
            sent=0,
            received=0,
            lost=0,
            loss_percent=0.0,
            min_rtt=0.0,
            max_rtt=0.0,
            avg_rtt=0.0,
            rtt_list=[],
        )

    if not quiet:
        logging.info(f"正在 Ping {host} [{dst_addr}] 具有 {len(payload)} 字节的数据:")

    data_ID = os.getpid() & 0xFFFF
    data_type = 8         # ICMP Echo Request
    data_code = 0         # 必须为 0
    data_checksum = 0     # 校验和初始值为 0
    data_Sequence = 1

    try:
        raw_sock = create_raw_socket()  # 此函数需在其它位置定义
    except PermissionError:
        err_msg = "需要管理员权限运行此程序"
        if not quiet:
            logging.error(err_msg)
        return PingStats(
            host=host,
            dst_addr=dst_addr,
            sent=0,
            received=0,
            lost=0,
            loss_percent=0.0,
            min_rtt=0.0,
            max_rtt=0.0,
            avg_rtt=0.0,
            rtt_list=[],
        )

    if iface:
        if platform.system() == "Windows":
            if not quiet:
                logging.warning("警告: Windows平台不支持指定网络接口功能，将忽略 iface 参数。")
        else:
            try:
                raw_sock.setsockopt(socket.SOL_SOCKET, 25, iface.encode('utf-8'))
            except Exception as e:
                err_msg = f"设置网络接口 {iface} 失败: {e}"
                if not quiet:
                    logging.error(err_msg)
                return PingStats(
                    host=host,
                    dst_addr=dst_addr,
                    sent=0,
                    received=0,
                    lost=0,
                    loss_percent=0.0,
                    min_rtt=0.0,
                    max_rtt=0.0,
                    avg_rtt=0.0,
                    rtt_list=[],
                )

    sent = 0
    received = 0
    rtt_list: list[float] = []
    iteration = 0

    try:
        while count == 0 or iteration < count:
            seq = data_Sequence + iteration
            icmp_packet = request_ping(data_type, data_code, data_checksum, data_ID, seq, payload)
            send_time = send_ping(raw_sock, dst_addr, icmp_packet)
            sent += 1
            rtt = reply_ping(raw_sock, send_time, seq, timeout=2)
            if rtt >= 0:
                if not quiet:
                    logging.info(f"来自 {dst_addr} 的回复: 字节={len(payload)} 时间={rtt*1000:.2f}ms")
                received += 1
                rtt_list.append(rtt * 1000)
            else:
                if not quiet:
                    logging.info("请求超时。")
            iteration += 1
            if delay != 0:
                time.sleep(delay)
    except KeyboardInterrupt:
        if not quiet:
            logging.info("用户中断。")

    lost = sent - received
    loss_percent = (lost / sent) * 100 if sent > 0 else 0.0
    if rtt_list:
        min_rtt = min(rtt_list)
        max_rtt = max(rtt_list)
        avg_rtt = sum(rtt_list) / len(rtt_list)
    else:
        min_rtt = max_rtt = avg_rtt = 0.0

    return PingStats(
        host=host,
        dst_addr=dst_addr,
        sent=sent,
        received=received,
        lost=lost,
        loss_percent=loss_percent,
        min_rtt=min_rtt,
        max_rtt=max_rtt,
        avg_rtt=avg_rtt,
        rtt_list=rtt_list,
    )
    
async def async_ping_with_return(
    host: str,
    count: int = 4,
    payload: bytes = b"abcdefghijklmnopqrstuvwabcdefghi",
    delay: float = 0.7,
    iface: Optional[str] = None,
    quiet: bool = False,
) -> PingStats:
    """
    异步封装的 ping_with_return 函数，便于在协程中使用。
    对指定主机发送 ICMP Echo Request，并返回统计信息的字典。

    返回字典包含如下键：
        - host: 用户输入的主机名
        - dst_addr: 解析得到的目标 IP 地址
        - sent: 发送的包数量
        - received: 接收到的包数量
        - lost: 丢失的包数量
        - loss_percent: 丢包百分比
        - min_rtt: 最小往返时间（毫秒）
        - max_rtt: 最大往返时间（毫秒）
        - avg_rtt: 平均往返时间（毫秒）
        - rtt_list: 每个成功接收包的往返时间列表（毫秒）

    参数:
        host (str): 要 ping 的主机名或 IP 地址。
        count (int): 发送的 ICMP 包数量；若为 0 则无限发送，直到用户中断。
        payload (bytes): ICMP 数据包的负载数据。
        delay (float): 每个包发送后的延时，单位为秒。
        iface (str|None): 指定使用的网络接口（如 "eth0"），仅在支持的系统上有效；
                          在 Windows 上不支持该功能，会发出警告并忽略此参数。
        quiet (bool): 是否关闭日志输出（True 表示关闭）。

    返回:
        PingStats: 包含统计信息的字典。
    """
    return await asyncio.to_thread(
        ping_with_return,
        host,
        count,
        payload,
        delay,
        iface,
        quiet,
    )

def main() -> None:
    parser = argparse.ArgumentParser(description="类似系统 ping 工具的 Python 版 ICMP ping")
    parser.add_argument("host", help="要 ping 的主机名或 IP 地址")
    parser.add_argument("-c", "--count", type=int, default=4, help="发送的包数量，0 表示无限发送")
    parser.add_argument("-d", "--delay", type=float, default=0.7, help="每个包之间的延时（秒）")
    parser.add_argument("-i", "--iface", type=str, default=None, help="指定网络接口（如 eth0），Windows 下无效")
    parser.add_argument("-p", "--payload", type=str, default="abcdefghijklmnopqrstuvwabcdefghi",
                        help="ICMP 数据包的负载内容（字符串）")
    parser.add_argument("-q", "--quiet", action="store_true", help="关闭日志输出，最大化发送速率")
    args = parser.parse_args()

    # 配置日志输出，如果启用 --quiet 则只输出 ERROR 级别日志
    log_level = logging.ERROR if args.quiet else logging.INFO
    logging.basicConfig(format="%(message)s", level=log_level)

    # 将 payload 转换为字节
    payload_bytes = args.payload.encode("utf-8")
    ping(args.host, count=args.count, payload=payload_bytes, delay=args.delay, iface=args.iface, quiet=args.quiet)

if __name__ == "__main__":
    main()
