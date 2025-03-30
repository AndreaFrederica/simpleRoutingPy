import json
import os
import config
from modules.dataclass import RouteEntry, RouteRule


def load_route_config(file_path: str = config.system_config.file_path_str) -> list[RouteEntry]:
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