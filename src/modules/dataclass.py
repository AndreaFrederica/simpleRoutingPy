from dataclasses import dataclass
import re
import subprocess
from typing import Optional

import src.context as context
from src.context import logger

@dataclass
class RouteRule:
    type: str
    max_packet_loss: float
    max_latency_ms: int
    check_interval_sec: int
    ping_address: Optional[str] = None
    
    def __str__(self) -> str:
        return (
            f"RouteRule(type={self.type}, "
            f"max_packet_loss={self.max_packet_loss}, "
            f"max_latency_ms={self.max_latency_ms}, "
            f"check_interval_sec={self.check_interval_sec}, "
            f"ping_address={self.ping_address})"
        )

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
    
    def __str__(self) -> str:
        rule_str = str(self.rule) if self.rule else "None"
        return (
            f"RouteEntry(id={self.id}, "
            f"destination={self.destination}, "
            f"gateway={self.gateway}, "
            f"interface={self.interface}, "
            f"metric={self.metric}, "
            f"priority={self.priority}, "
            f"proto={self.proto}, "
            f"rule={rule_str}, "
            f"useable={self.useable})"
        )

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
                    with context.event_lock:
                        if warning_key not in context.ping_warnings:
                            logger.warning(f"[{self.id}] 网络警告: {'，'.join(warning_msg)}")
                            context.ping_warnings.add(warning_key)
                else:
                    with context.event_lock:
                        if warning_key in context.ping_warnings:
                            context.logger.warning(f"[{self.id}] 网络状况恢复")
                            context.ping_warnings.remove(warning_key)

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