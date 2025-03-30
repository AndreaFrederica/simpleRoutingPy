import os
import sys
from pathlib import Path
import tempfile
import time
from typing import Optional
import uuid

class AppPathResolver:
    def __init__(
        self,
        app_name: str,
        file_name: str,
        sub_dir: Optional[str] = None,
        linux_system_wide: bool = True
    ):
        """
        跨平台应用路径解析器（仅生成路径，不处理读写）

        :param app_name: 应用名称（用于目录命名，如"MyApp"）
        :param file_name: 文件名（如"config.json"）
        :param sub_dir: 可选的子目录（如"settings"）
        :param linux_system_wide: 是否在Linux下使用系统级路径（默认为True）
        """
        self._app_name = app_name
        self._file_name = file_name
        self._sub_dir = sub_dir
        self._linux_system_wide = linux_system_wide

        # 生成路径并确保目录存在
        self._base_dir = self._resolve_base_dir()
        self._full_dir = self._build_full_dir()
        self._file_path = self._build_file_path()

    def _resolve_base_dir(self) -> Path:
        """解析操作系统对应的基础目录"""
        if sys.platform.startswith("win"):
            # Windows: APPDATA/AppName
            appdata_dir = os.getenv("APPDATA")
            if not appdata_dir:
                appdata_dir = Path.home() / "AppData" / "Roaming"
            return Path(appdata_dir) / self._app_name
        else:
            # Linux/macOS: 系统级或用户级路径
            if self._linux_system_wide:
                return Path("/etc") / self._app_name
            else:
                return Path.home() / ".config" / self._app_name

    def _build_full_dir(self) -> Path:
        """构建完整目录路径"""
        full_dir = self._base_dir
        if self._sub_dir:
            full_dir /= self._sub_dir
        # 自动创建目录（如果不存在）
        full_dir.mkdir(parents=True, exist_ok=True)
        return full_dir

    def _build_file_path(self) -> Path:
        """构建完整文件路径"""
        return self._full_dir / self._file_name

    @property
    def directory(self) -> Path:
        """返回配置目录路径（只读）"""
        return self._full_dir

    @property
    def file_path(self) -> Path:
        """返回文件完整路径（只读）"""
        return self._file_path

    @property
    def directory_str(self) -> str:
        """返回配置目录路径（只读）"""
        return str(self._full_dir)

    @property
    def file_path_str(self) -> str:
        """返回文件完整路径（只读）"""
        return str(self._file_path)


class TemporaryPathResolver:
    def __init__(
        self,
        app_name: str,
        file_name: Optional[str] = None,
        sub_dir: Optional[str] = None,
        use_system_temp_dir: bool = True,
        auto_generate_filename: bool = False
    ):
        """
        跨平台临时文件路径解析器

        :param app_name: 应用名称（用于隔离临时文件目录，如"MyApp"）
        :param file_name: 指定文件名（如"cache.tmp"；若为None且启用auto_generate_filename，则自动生成唯一文件名）
        :param sub_dir: 可选的子目录（如"cache"）
        :param use_system_temp_dir: 是否使用系统临时目录（否则根据操作系统生成路径）
        :param auto_generate_filename: 是否自动生成唯一文件名（当file_name为None时生效）
        """
        self._app_name = app_name
        self._file_name = file_name
        self._sub_dir = sub_dir
        self._use_system_temp_dir = use_system_temp_dir
        self._auto_generate_filename = auto_generate_filename

        # 生成路径
        self._base_dir = self._resolve_base_dir()
        self._full_dir = self._build_full_dir()
        self._file_path = self._build_file_path()

    def _resolve_base_dir(self) -> Path:
        """解析基础临时目录"""
        if self._use_system_temp_dir:
            # 使用Python识别的系统临时目录
            return Path(tempfile.gettempdir()) / self._app_name
        else:
            # 手动指定操作系统默认临时目录（非Python标准）
            if sys.platform.startswith("win"):
                # Windows: LocalAppData/Temp
                local_temp = Path(os.getenv("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "Temp"
                return local_temp / self._app_name
            else:
                # Linux/macOS: /tmp
                return Path("/tmp") / self._app_name

    def _build_full_dir(self) -> Path:
        """构建完整目录路径"""
        full_dir = self._base_dir
        if self._sub_dir:
            full_dir /= self._sub_dir
        full_dir.mkdir(parents=True, exist_ok=True)  # 确保目录存在
        return full_dir

    def _build_file_path(self) -> Path:
        """生成文件路径"""
        if self._file_name:
            # 直接使用指定文件名
            return self._full_dir / self._file_name
        elif self._auto_generate_filename:
            # 自动生成唯一文件名（UUID + 时间戳）
            unique_id = f"{uuid.uuid4().hex}_{int(time.time()*1000)}"
            return self._full_dir / f"temp_{unique_id}.tmp"
        else:
            # 返回目录路径（当不需要具体文件时）
            return self._full_dir

    @property
    def directory(self) -> Path:
        """返回临时文件目录路径"""
        return self._full_dir

    @property
    def file_path(self) -> Path:
        """返回临时文件完整路径"""
        return self._file_path
    @property
    def directory_str(self) -> str:
        """返回配置目录路径（只读）"""
        return str(self._full_dir)

    @property
    def file_path_str(self) -> str:
        """返回文件完整路径（只读）"""
        return str(self._file_path)