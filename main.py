from collections import defaultdict
import re
import subprocess
import json
import os
from dataclasses import dataclass
import sys
import time
from typing import Dict, List, Optional
import logging
from logging.handlers import RotatingFileHandler
import threading

default_config_path = "/etc/config/simplerouting.json"

# 配置日志参数
log_path = "/tmp/routing.log"
max_log_size = 5 * 1024 * 1024  # 5MB

# 命令行参数解析
debug_mode: bool = "-debug" in sys.argv


# 初始化日志系统
logger = logging.getLogger('RouteLogger')
logger.setLevel(logging.DEBUG)  # 根记录器设置为最低级别

# 终端处理器配置（始终带日期）
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG if debug_mode else logging.INFO)  # 级别控制
console_format = '%(asctime)s - %(levelname)s - %(message)s'
console_handler.setFormatter(logging.Formatter(console_format))

# 文件处理器配置（保持不变）
file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

main_handler = RotatingFileHandler(
    log_path,
    maxBytes=max_log_size,
    backupCount=3,
    encoding='utf-8'
)
main_handler.setLevel(logging.INFO)
main_handler.setFormatter(file_formatter)

# class InfoFilter(logging.Filter):
#     def filter(self, record):
#         return "接口上线" in record.getMessage()

# info_handler = RotatingFileHandler(
#     log_path,
#     maxBytes=max_log_size,
#     backupCount=3,
#     encoding='utf-8'
# )
# info_handler.setLevel(logging.INFO)
# info_handler.addFilter(InfoFilter())
# info_handler.setFormatter(file_formatter)

# 添加处理器
logger.addHandler(console_handler)
logger.addHandler(main_handler)
# logger.addHandler(info_handler)

# 全局状态跟踪
event_lock = threading.Lock()
route_status = {}
ping_warnings = set()



@dataclass
class RouteRule:
    type: str
    max_packet_loss: float
    max_latency_ms: int
    check_interval_sec: int
    ping_address: Optional[str] = None

@dataclass
class RouteEntry:
    id: str
    destination: str
    gateway: Optional[str]
    interface: str
    metric: int
    priority: int
    proto: Optional[str]
    rule: Optional[RouteRule]
    useable: Optional[bool]

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, RouteEntry):
            return NotImplemented

        # 处理 destination 的特殊等价规则
        def normalize_dest(dest: str) -> str:
            return "0.0.0.0/0" if dest == "default" else dest

        return (
            normalize_dest(self.destination) == normalize_dest(other.destination)
            and self.gateway == other.gateway
            and self.interface == other.interface
            and self.metric == other.metric
        )

    def check_status(self) -> bool:
        if not self.rule or self.rule.type != "ping":
            return True

        target = self.rule.ping_address or self.gateway
        if not target:
            return True

        cmd = [
            "ping", "-I", self.interface,
            "-c", "3",
            "-W", str(self.rule.max_latency_ms // 1000 or 1),
            target
        ]

        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True,
                timeout=self.rule.check_interval_sec
            )

            packet_loss, avg_latency = self._parse_ping_output(result.stdout)
            
            meet_condition = True
            if packet_loss > self.rule.max_packet_loss:
                meet_condition = False
            if avg_latency > self.rule.max_latency_ms:
                meet_condition = False

            # 记录网络状况警告
            warning_key = f"{self.id}_net_warning"
            if meet_condition:
                warning_msg = []
                if packet_loss > 0:
                    warning_msg.append(f"丢包率 {packet_loss}%")
                if avg_latency > self.rule.max_latency_ms * 0.8:
                    warning_msg.append(f"延迟 {avg_latency}ms")
                
                if warning_msg:
                    with event_lock:
                        if warning_key not in ping_warnings:
                            logger.warning(f"[{self.id}] 网络警告: {'，'.join(warning_msg)}")
                            ping_warnings.add(warning_key)
                else:
                    with event_lock:
                        if warning_key in ping_warnings:
                            logger.warning(f"[{self.id}] 网络状况恢复")
                            ping_warnings.remove(warning_key)

            self.useable = meet_condition
            return meet_condition

        except subprocess.CalledProcessError as e:
            logger.debug(f"[{self.id}] 检测失败: {e.stderr.strip()}")
            self.useable = False
            return False
        except subprocess.TimeoutExpired:
            logger.warning(f"[{self.id}] 检测超时")
            self.useable = False
            return False

    def _parse_ping_output(self, output: str) -> tuple[float, float]:
        packet_loss = 100.0
        if loss_match := re.search(r"(\d+)% packet loss", output):
            packet_loss = float(loss_match.group(1))

        avg_latency = float("inf")
        if latency_match := re.search(r"=\s.*?/(\d+\.\d+)/", output):
            avg_latency = float(latency_match.group(1))

        return packet_loss, avg_latency

def get_ip_route() -> List[RouteEntry]:
    result = subprocess.run(["ip", "route"], capture_output=True, text=True)
    routes = []
    i = 0

    for line in result.stdout.splitlines():
        parts = line.split()
        dest = parts[0]
        gw = None
        iface = None
        metric = 0
        proto = None

        if "via" in parts:
            gw = parts[parts.index("via") + 1]

        if "dev" in parts:
            iface = parts[parts.index("dev") + 1]

        if "metric" in parts:
            metric = int(parts[parts.index("metric") + 1])

        if "proto" in parts:
            proto = parts[parts.index("proto") + 1]

        if iface:
            routes.append(
                RouteEntry(
                    id=f"sys_route{i}",
                    destination=dest,
                    gateway=gw,
                    interface=iface,
                    metric=metric,
                    priority=0,
                    proto=proto,
                    rule=None,
                    useable=None,
                )
            )
        i += 1

    return routes


def load_route_config(file_path: str = default_config_path) -> List[RouteEntry]:
    if not os.path.exists(file_path):
        default_config = []
        with open(file_path, "w") as f:
            json.dump(default_config, f, indent=4)
        return []

    with open(file_path, "r") as f:
        config = json.load(f)

    routes = []
    for entry in config:
        rule = RouteRule(**entry["rule"]) if "rule" in entry else None
        routes.append(
            RouteEntry(
                id=entry["id"],
                destination=entry["route"],
                gateway=entry.get("gateway"),
                interface=entry["port"],
                metric=entry["metric"],
                priority=entry["priority"],
                proto=None,
                rule=rule,
                useable=False,
            )
        )

    return routes


def add_route(route: RouteEntry) -> bool:
    """通过ip route命令添加路由"""
    # 转换默认路由表示方式
    dest = route.destination
    if dest == "default":
        dest = "0.0.0.0/0"

    # 构建基础命令
    cmd = ["ip", "route", "add", dest]

    # 添加网关参数
    if route.gateway:
        cmd.extend(["via", route.gateway])

    # 添加设备参数
    cmd.extend(["dev", route.interface])

    # 添加metric参数
    if route.metric > 0:
        cmd.extend(["metric", str(route.metric)])

    try:
        subprocess.run(
            cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        logger.critical(f"[OK] 已添加路由: {route.id}")
        return True
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.strip()
        logger.error(f"[ERR] 添加路由失败 {route.id}: {error_msg}")
        return False


def remove_route(route: RouteEntry) -> bool:
    """通过ip route命令删除路由"""
    # 转换默认路由表示方式
    dest = route.destination
    if dest == "default":
        dest = "0.0.0.0/0"

    # 构建基础命令
    cmd = ["ip", "route", "del", dest]

    # 添加网关参数（提升删除准确性）
    if route.gateway:
        cmd.extend(["via", route.gateway])

    # 添加设备参数（提升删除准确性）
    cmd.extend(["dev", route.interface])

    try:
        subprocess.run(
            cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        logger.critical(f"[OK] 已删除路由: {route.id}")
        return True
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.strip()
        logger.error(f"[ERR] 删除路由失败 {route.id}: {error_msg}")
        return False

def apply_routes(
    inject_routes: List[RouteEntry],
    existing_routes: List[RouteEntry],
    remove_routes: List[RouteEntry],
) -> None:
    """
    执行实际路由变更操作
    执行顺序建议：
    1. 先删除需要移除的路由
    2. 再添加新路由（避免网络中断）
    """
    # 删除失效路由
    for route in remove_routes:
        remove_route(route)

    # 注入新路由
    for route in inject_routes:
        add_route(route)

    # 打印状态报告
    logger.debug("执行结果摘要：")
    logger.debug(f"成功注入 {len(inject_routes)} 条路由")
    logger.debug(f"系统已存在 {len(existing_routes)} 条有效路由")
    logger.debug(f"已清理 {len(remove_routes)} 条失效路由")

def enable_config_route(ip_routes: List[RouteEntry], config_routes: List[RouteEntry]) -> None:
    global route_status

    # 跟踪状态变化
    for route in config_routes:
        current = route.useable
        previous = route_status.get(route.id, None)
        
        with event_lock:
            if previous is None:
                route_status[route.id] = current
                if current:
                    logger.info(f"接口上线: {route.interface}({route.id})")
                else:
                    logger.error(f"接口不可用: {route.interface}({route.id})")
            elif current != previous:
                route_status[route.id] = current
                if current:
                    logger.info(f"接口恢复: {route.interface}({route.id})")
                else:
                    logger.error(f"接口故障: {route.interface}({route.id})")

    # 后续原有路由处理逻辑保持不变...
    # 预处理：建立系统路由与配置路由的映射关系
    sys_route_config_map:dict[str,int] = {}
    for sys_route in ip_routes:
        # 查找匹配的配置路由（基于四个核心字段）
        matched_config = next(
            (cr for cr in config_routes if
            #  cr.destination == sys_route.destination and
            #  cr.gateway == sys_route.gateway and
            #  cr.interface == sys_route.interface and
            #  cr.metric == sys_route.metric
            cr == sys_route
            ),
            None
        )
        
        # 记录匹配到的配置优先级（未匹配设为0）
        sys_route_config_map[sys_route.id] = (
            matched_config.priority if matched_config else 0
        )

    # 路由分组与处理逻辑（保持不变）
    destinations2routes = defaultdict(list[RouteEntry])
    for route in config_routes:
        if route.destination == "0.0.0.0/0":
            route.destination = "default"
        destinations2routes[route.destination].append(route)

    # 选择可用路由逻辑（保持不变）
    selected_routes = []
    failed_routes = []
    for dest, routes in destinations2routes.items():
        sorted_routes = sorted(routes, key=lambda x: x.priority)
        available = [r for r in sorted_routes if r.useable]
        if available:
            selected_routes.append(available[0])
        failed_routes.extend(r for r in sorted_routes if not r.useable)

    # 路由决策逻辑
    inject_routes = []
    remove_routes = []
    existing_routes = []

    for candidate in selected_routes:
        # 查找匹配的系统路由
        matched_sys = next(
            (sr for sr in ip_routes if
            #  sr.destination == candidate.destination and
            #  sr.gateway == candidate.gateway and
            #  sr.interface == candidate.interface and
            #  sr.metric == candidate.metric
            sr == candidate
            ),
            None
        )

        if matched_sys:
            # 比较配置优先级与系统记录的优先级
            sys_prio = sys_route_config_map[matched_sys.id]
            if candidate.priority < sys_prio:
                logger.critical(f"路由更新: {candidate.id} (新优先级 {candidate.priority} < 旧 {sys_prio})")
                remove_routes.append(matched_sys)
                inject_routes.append(candidate)
            else:
                existing_routes.append(candidate)
        else:
            inject_routes.append(candidate)

    # 处理失效路由
    for failed in failed_routes:
        matched_sys = next(
            (sr for sr in ip_routes if
            #  sr.destination == failed.destination and
            #  sr.gateway == failed.gateway and
            #  sr.interface == failed.interface and
            #  sr.metric == failed.metric
            sr == failed
            ),
            None
        )
        if matched_sys and matched_sys not in remove_routes:
            remove_routes.append(matched_sys)

    # 执行路由变更
    logger.debug("路由变更计划:")
    logger.debug(f"新增路由: {[r.id for r in inject_routes]}")
    logger.debug(f"删除路由: {[r.id for r in remove_routes]}")
    logger.debug(f"保留路由: {[r.id for r in existing_routes]}")
    logger.debug(f"失效路由: {[r.id for r in failed_routes]}")
    
    apply_routes(
        inject_routes=inject_routes,
        remove_routes=remove_routes,
        existing_routes=existing_routes
    )

# 其余原有函数保持不变...

if __name__ == "__main__":
    # 初始化日志状态
    with event_lock:
        route_status = {}
        ping_warnings = set()
        config_routes = load_route_config()
        logger.info("load config done.")

    while True:
        ip_routes = get_ip_route()
        for route in config_routes:
            route.check_status()
        enable_config_route(ip_routes, config_routes)
        time.sleep(5)