from pathlib import Path
from typing import Dict, List, Pattern
import re


DEFAULT_CATEGORIES: Dict[str, Dict] = {
    "images": {
        "name": "图片",
        "extensions": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg", ".ico", ".tiff", ".heic", ".raw"],
        "target_dir": "Images",
    },
    "videos": {
        "name": "视频",
        "extensions": [".mp4", ".avi", ".mov", ".wmv", ".flv", ".mkv", ".webm", ".m4v", ".mpeg", ".mpg", ".3gp"],
        "target_dir": "Videos",
    },
    "documents": {
        "name": "文档",
        "extensions": [".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".md", ".rtf", ".odt", ".csv"],
        "target_dir": "Documents",
    },
    "audio": {
        "name": "音频",
        "extensions": [".mp3", ".wav", ".flac", ".aac", ".ogg", ".wma", ".m4a", ".aiff"],
        "target_dir": "Audio",
    },
    "archives": {
        "name": "压缩包",
        "extensions": [".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".tgz"],
        "target_dir": "Archives",
    },
    "programs": {
        "name": "安装包",
        "extensions": [".exe", ".msi", ".dmg", ".pkg", ".deb", ".rpm", ".apk", ".iso"],
        "target_dir": "Programs",
    },
    "screenshots": {
        "name": "截图",
        "regex_patterns": [
            r"^屏幕截图.*",
            r"^Screenshot.*",
            r"^截图.*",
            r"^Snipaste.*",
            r"^微信截图.*",
            r"^QQ截图.*",
        ],
        "target_dir": "Screenshots",
    },
    "downloads": {
        "name": "下载",
        "regex_patterns": [
            r".*\(\d+\)\.\w+$",
        ],
        "target_dir": "Downloads",
    },
    "code": {
        "name": "代码",
        "extensions": [".py", ".js", ".ts", ".html", ".css", ".java", ".cpp", ".c", ".h", ".go", ".rs", ".php", ".rb", ".swift", ".kt", ".vue", ".jsx", ".tsx"],
        "target_dir": "Code",
    },
    "fonts": {
        "name": "字体",
        "extensions": [".ttf", ".otf", ".woff", ".woff2", ".eot"],
        "target_dir": "Fonts",
    },
}

TEMP_PATTERNS: List[Pattern] = [
    re.compile(r"^~\$.*", re.IGNORECASE),
    re.compile(r"^~lock.*", re.IGNORECASE),
    re.compile(r"^~.*\.tmp$", re.IGNORECASE),
    re.compile(r".*\.tmp$", re.IGNORECASE),
    re.compile(r".*\.temp$", re.IGNORECASE),
    re.compile(r".*\.bak$", re.IGNORECASE),
    re.compile(r".*\.log$", re.IGNORECASE),
    re.compile(r".*\.crdownload$", re.IGNORECASE),
    re.compile(r".*\.part$", re.IGNORECASE),
    re.compile(r"^\.DS_Store$", re.IGNORECASE),
    re.compile(r"^Thumbs\.db$", re.IGNORECASE),
    re.compile(r"^desktop\.ini$", re.IGNORECASE),
    re.compile(r".*\.cache.*", re.IGNORECASE),
]

DEFAULT_EXCLUDE_DIRS: List[str] = [
    ".git",
    "$RECYCLE.BIN",
    "System Volume Information",
    "Program Files",
    "Program Files (x86)",
    "Windows",
    "AppData",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    ".idea",
    ".vscode",
]

DEFAULT_MIN_SIZE: int = 0
DEFAULT_MAX_SIZE: int = -1

def is_temporary_file(filename: str) -> bool:
    return any(pattern.match(filename) for pattern in TEMP_PATTERNS)

def match_name_pattern(filename: str, patterns: List[str]) -> bool:
    return any(re.match(pattern, filename, re.IGNORECASE) for pattern in patterns)

def match_glob_pattern(filename: str, patterns: List[str]) -> bool:
    import fnmatch
    return any(fnmatch.fnmatch(filename, pattern) for pattern in patterns)

def get_category_by_extension(ext: str) -> str:
    ext_lower = ext.lower()
    for category, config in DEFAULT_CATEGORIES.items():
        if "extensions" in config and ext_lower in config["extensions"]:
            return category
    return "other"

def get_category_by_name(filename: str) -> str:
    for category, config in DEFAULT_CATEGORIES.items():
        if "regex_patterns" in config and match_name_pattern(filename, config["regex_patterns"]):
            return category
        if "patterns" in config and match_glob_pattern(filename, config["patterns"]):
            return category
    return ""

def get_target_dir(category: str) -> str:
    if category in DEFAULT_CATEGORIES and "target_dir" in DEFAULT_CATEGORIES[category]:
        return DEFAULT_CATEGORIES[category]["target_dir"]
    return "Other"
