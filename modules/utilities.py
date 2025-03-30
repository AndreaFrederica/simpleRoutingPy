def normalize_dest(dest: str) -> str:
    return "0.0.0.0/0" if dest == "default" else dest