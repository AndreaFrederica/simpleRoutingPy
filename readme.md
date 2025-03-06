# SimpleRouting 路由管理工具
**文档采用DeepSeek生成**
## 🚀 项目简介
简单的的动态路由管理方案，通过Ping检测实现多线路故障切换，可替代mwan3。支持OpenWrt等Linux发行版，解决FRR路由套件缺失的链路检测能力。

---

## 🌟 核心特性
| 功能                      | 描述                                                                 |
|---------------------------|--------------------------------------------------------------------|
| **故障切换**           | 基于Ping的实时网络质量检测，支持自定义丢包率/延迟阈值                   |
| **优先级路由策略**         | 多路径优先级管理（值越小优先级越高）                                    |
| **零外部依赖**             | 仅使用标准`ip route`命令，无需复杂路由套件                              |
| **轻量级设计**             | 单文件架构，内存占用＜5MB（也许）                                             |
| **详尽的日志系统**         | 循环日志文件+实时状态监控，支持调试模式                                 |

---

## 📦 安装部署

### 系统要求
- **Python 3.6+**（OpenWrt需手动安装）
- Linux内核 ≥ 3.10
- iproute2工具集

### OpenWrt环境配置
```bash
# 安装Python3运行时
opkg update
opkg install python3 python3-pip

# 创建配置目录
mkdir -p /etc/config
```

### 获取程序
```bash
wget https://example.com/main.py -O /usr/local/bin/simplerouting
chmod +x /usr/local/bin/simplerouting
```

---

## ⚙️ 配置指南

### 配置文件路径
`/etc/config/simplerouting.json`

### 配置示例
```json
[
    {
        "id": "wan_primary",
        "route": "0.0.0.0/0",
        "gateway": "192.168.1.1",
        "port": "eth0",
        "metric": 100,
        "priority": 1,
        "rule": {
            "type": "ping",
            "ping_address": "8.8.8.8",
            "max_packet_loss": 5.0,
            "max_latency_ms": 500,
            "check_interval_sec": 5
        }
    },
    {
        "id": "wan_backup",
        "route": "0.0.0.0/0",
        "gateway": "192.168.2.1",
        "port": "eth1",
        "metric": 200,
        "priority": 2,
        "rule": {
            "type": "ping",
            "max_packet_loss": 10.0,
            "max_latency_ms": 1000,
            "check_interval_sec": 10
        }
    }
]
```

### 字段说明
| 字段         | 必填 | 格式示例           | 说明                          |
|--------------|------|--------------------|-----------------------------|
| `id`         | ✔️   | "wan_primary"      | 路由唯一标识（建议英文命名）    |
| `route`      | ✔️   | "0.0.0.0/0"        | 目标网络（CIDR或"default"）    |
| `gateway`    | ✖️   | "192.168.1.1"      | 网关IP（未指定则用接口默认网关）|
| `port`       | ✔️   | "eth0"             | 物理/虚拟接口名称              |
| `metric`     | ✔️   | 100                | 路由权重值（值越小优先级越高）  |
| `priority`   | ✔️   | 1                  | 配置优先级（值越小优先级越高）  |
| `rule`       | ✔️   | {...}              | 链路检测规则配置               |

---

## 📜 日志管理

### 日志文件
- **路径**: `/tmp/routing.log`
- **轮转策略**: 保留3个历史文件，每个最大5MB

### 典型日志事件
```log
2023-08-20 14:30:00 - INFO - 接口上线: eth0(wan_primary)
2023-08-20 14:35:22 - WARNING - [wan_primary] 网络警告: 丢包率 12%
2023-08-20 14:35:25 - CRITICAL - [OK] 已添加路由: wan_backup
2023-08-20 14:35:30 - ERROR - 接口故障: eth0(wan_primary)
```

---

## 🛠️ 服务化管理

### Systemd服务配置
创建`/etc/systemd/system/simplerouting.service`：
```ini
[Unit]
Description=SimpleRouting Dynamic Routing Service
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 /usr/local/bin/simplerouting
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### 服务命令
```bash
systemctl daemon-reload
systemctl start simplerouting
systemctl enable simplerouting
```

---

## ⚠️ 注意事项
1. **权限要求**: 必须使用root权限运行（需要修改路由表）
2. **路由冲突**: 会覆盖非kernel协议的路由（如dhcp生成的）
3. **检测间隔**: 建议≥3秒，避免系统负载过高
4. **双栈支持**: 目前仅支持IPv4路由管理
5. **Ping限制**: 确保`/bin/ping`存在且具有执行权限

---

## 🔍 故障排查

### 常用诊断命令
```bash
# 查看实时日志
tail -f /tmp/routing.log

# 验证当前路由表
ip route show table all

# 手动测试链路检测
ping -I eth0 -c 3 -W 1 8.8.8.8

# 检查Python版本
python3 --version
```

### 调试模式
```bash
./simplerouting -debug  # 显示详细过程信息
```

---

> 🛠 项目持续维护中，欢迎提交Issue反馈问题  
> 📌 已知限制：暂不支持策略路由，复杂场景建议结合FRR使用
