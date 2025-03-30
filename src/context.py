import threading

event_lock = threading.Lock()
route_status = {}
ping_warnings = set()