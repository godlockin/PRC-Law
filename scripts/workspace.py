#!/usr/bin/env python3
"""
workspace.py — PRC-Law 律师工作目录协议 (W16)

解决: 律师客户端 (Claude Code / Trae / WorkBuddy) 加载 PRC-Law skill 时,
     律师案件数据存哪里? skill 如何自动找到?

设计:
  1. Workspace 单例, 提供律师数据路径解析
  2. 三层优先级: 环境变量 > 配置文件 > 自动探测
  3. 工作目录 (读写) + 已有目录 (只读) 分离
  4. 客户端检测, 给律师针对性引导

用法:
  from scripts.workspace import Workspace
  ws = Workspace()
  print(ws.matters_dir)         # ~/lawyer-work/matters (或探测到的)
  print(ws.cases_db_path)       # ~/lawyer-work/cases.db
  print(ws.existing_dir)        # 律师已有目录 (None if 未指定)
  print(ws.client)               # "claude-code" / "trae" / "workbuddy" / "unknown"

环境变量 (可选, 优先级最高):
  PRC_LAW_WORKSPACE          工作目录 (默认 ~/lawyer-work)
  PRC_LAW_EXISTING_DIR       已有案例目录 (只读, 可选)
  PRC_LAW_LAWYER_PROFILE     律师画像路径 (默认 ~/lawyer-work/.lawyer_profile)
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# === 客户端检测 ===
def detect_client() -> str:
    """检测律师使用的 AI 客户端

    Returns:
        "claude-code" / "trae" / "workbuddy" / "unknown"
    """
    # Claude Code: 通常在 ~/.claude/ 目录有配置
    if (Path.home() / ".claude" / "settings.json").exists() \
            or "CLAUDE_CODE" in os.environ:
        return "claude-code"

    # Trae: ~/.trae/ 或 TRAE_ 环境变量
    if (Path.home() / ".trae").exists() or "TRAE" in os.environ:
        return "trae"

    # WorkBuddy: ~/Library/Application Support/WorkBuddy (macOS)
    # 或 ~/.config/WorkBuddy (Linux) 或 Windows 注册表
    if platform.system() == "Darwin":
        if (Path.home() / "Library" / "Application Support" / "WorkBuddy").exists():
            return "workbuddy"
    elif platform.system() == "Linux":
        if (Path.home() / ".config" / "WorkBuddy").exists():
            return "workbuddy"
    elif platform.system() == "Windows":
        # Windows 检测: %APPDATA%\WorkBuddy
        appdata = os.environ.get("APPDATA", "")
        if appdata and (Path(appdata) / "WorkBuddy").exists():
            return "workbuddy"

    return "unknown"


# === 配置文件 ===
CONFIG_PATH = Path.home() / ".config" / "prc-law" / "workspace.json"
LEGACY_CONFIG = Path.home() / ".config" / "prc-law" / "lawyer-workspace.json"


@dataclass
class Workspace:
    """律师工作目录单例

    Attributes:
        workspace_dir: 律师工作目录 (读写, PRC-Law 维护)
        existing_dir: 律师已有目录 (只读, 律师指定)
        config: 完整配置 dict
        client: 律师使用的 AI 客户端
        lawyer_profile: 律师画像路径
        cases_db: 本地案件库 SQLite
        matters_dir: 在办案件目录
        alerts_dir: 提醒输出目录
        calibration_path: 本地校准缓存
    """
    workspace_dir: Path
    existing_dir: Optional[Path] = None
    config: dict = field(default_factory=dict)
    client: str = "unknown"
    lawyer_profile: Path = None
    cases_db: Path = None
    matters_dir: Path = None
    alerts_dir: Path = None
    calibration_path: Path = None
    intake_dir: Path = None  # W16.2 律师已有案卷只读目录

    @classmethod
    def load(cls, env_existing: Optional[str] = None) -> "Workspace":
        """加载 Workspace (按优先级)

        Args:
            env_existing: 临时指定已有目录 (CLI 参数, 优先级最高)
        """
        # === 1. 环境变量 (最高优先级) ===
        ws_dir_str = os.environ.get("PRC_LAW_WORKSPACE", "").strip()
        existing_str = env_existing or os.environ.get("PRC_LAW_EXISTING_DIR", "").strip()

        # === 2. 配置文件 ===
        config = {}
        config_path = CONFIG_PATH if CONFIG_PATH.exists() else LEGACY_CONFIG
        if config_path.exists():
            try:
                config = json.loads(config_path.read_text(encoding="utf-8"))
                if not ws_dir_str:
                    ws_dir_str = config.get("workspace_dir", "").strip()
                if not existing_str:
                    existing_str = config.get("existing_dir", "").strip()
            except Exception:
                pass

        # === 3. 探测常见位置 ===
        if not ws_dir_str:
            candidates = [
                Path.cwd() / "lawyer-work",
                Path.home() / "lawyer-work",
                Path.home() / ".lawyer-work",
            ]
            for cand in candidates:
                if (cand / ".initialized").exists():
                    ws_dir_str = str(cand)
                    break

        # === 4. 默认 ===
        if not ws_dir_str:
            ws_dir_str = str(Path.home() / "lawyer-work")

        # === 解析 ===
        ws_dir = Path(ws_dir_str).expanduser().resolve()
        # 兼容 macOS /tmp → /private/tmp symlink (律师输入 /tmp 时真实路径可能是 /private/tmp)
        if existing_str:
            existing = Path(os.path.realpath(Path(existing_str).expanduser()))
            if not existing.exists():
                existing = None  # 路径无效则忽略
        else:
            existing = None

        profile_path = Path(
            os.environ.get("PRC_LAW_LAWYER_PROFILE") or
            config.get("lawyer_profile") or
            ws_dir / ".lawyer_profile"
        ).expanduser().resolve()

        # 客户端检测
        client = detect_client()

        ws = cls(
            workspace_dir=ws_dir,
            existing_dir=existing,
            config=config,
            client=client,
            lawyer_profile=profile_path,
            cases_db=ws_dir / "cases.db",
            matters_dir=ws_dir / "matters",
            alerts_dir=ws_dir / "alerts",
            calibration_path=ws_dir / ".calibration.json",
            intake_dir=existing,  # W16.2: 已有目录作为"只读入口"
        )
        return ws

    # === 检测与提示 ===
    def is_initialized(self) -> bool:
        """是否已初始化"""
        return (self.workspace_dir / ".initialized").exists()

    def ensure_layout(self) -> None:
        """创建工作目录布局 (matters/, alerts/ 等)"""
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        for d in [self.matters_dir, self.alerts_dir]:
            d.mkdir(parents=True, exist_ok=True)
        # 初始化标记
        if not (self.workspace_dir / ".initialized").exists():
            (self.workspace_dir / ".initialized").write_text(
                json.dumps({
                    "created_at": str(__import__("datetime").datetime.now()),
                    "client": self.client,
                    "version": "v9.0.0",
                }, ensure_ascii=False),
                encoding="utf-8",
            )

    def save_config(self) -> None:
        """保存配置到 ~/.config/prc-law/workspace.json"""
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(
            json.dumps({
                "workspace_dir": str(self.workspace_dir),
                "existing_dir": str(self.existing_dir) if self.existing_dir else None,
                "lawyer_profile": str(self.lawyer_profile),
                "client": self.client,
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def summary(self) -> str:
        """摘要输出 (CLI / 调试用)"""
        lines = [
            f"律师工作目录: {self.workspace_dir}",
            f"已有目录 (只读): {self.existing_dir or '(未指定)'}",
            f"  → matters/:    {self.matters_dir}",
            f"  → cases.db:    {self.cases_db}",
            f"  → alerts/:    {self.alerts_dir}",
            f"  → .lawyer_profile: {self.lawyer_profile}",
            f"  → 已初始化:    {self.is_initialized()}",
            f"客户端:        {self.client}",
        ]
        return "\n".join(lines)


# === 已有目录分析 (W16.2) ===
@dataclass
class ExistingDirAnalysis:
    """律师已有目录分析结果"""
    total_files: int = 0
    total_dirs: int = 0
    estimated_cases: int = 0
    year_distribution: dict = field(default_factory=dict)
    type_distribution: dict = field(default_factory=dict)
    file_types: dict = field(default_factory=dict)
    sample_files: list = field(default_factory=list)
    suggested_mapping: dict = field(default_factory=dict)


def analyze_existing_dir(dir_path: Path) -> ExistingDirAnalysis:
    """只读分析律师已有目录 (不动文件)

    识别:
      - 文件总数 + 目录数
      - 估计案件数 (按子目录结构)
      - 年度分布 (从文件日期/路径)
      - 类型分布 (.docx / .pdf / .txt 等)
      - 案号模式 (如 (2024)沪0115民初1234号)
      - 建议映射 (如何导入 PRC-Law)
    """
    # 兼容 macOS /tmp 与 /private/tmp 命名空间不一致 (sandbox 隔离)
    if not dir_path.exists():
        # 尝试 normalize
        candidates = [
            dir_path,
            Path(str(dir_path).replace("/private/tmp", "/tmp")),
            Path(str(dir_path).replace("/tmp", "/private/tmp")),
        ]
        for cand in candidates:
            if cand.exists():
                dir_path = cand
                break
        else:
            raise FileNotFoundError(f"目录不存在: {dir_path}")

    analysis = ExistingDirAnalysis()
    analysis.total_dirs = sum(1 for _ in dir_path.rglob("*") if _.is_dir())
    files = list(dir_path.rglob("*"))
    analysis.total_files = sum(1 for f in files if f.is_file())

    # 文件类型分布
    for f in files:
        if f.is_file():
            ext = f.suffix.lower() or "(无扩展名)"
            analysis.file_types[ext] = analysis.file_types.get(ext, 0) + 1

    # 估计案件数: 顶层子目录数 (假设每子目录 = 1 案件)
    try:
        top_level = [d for d in dir_path.iterdir() if d.is_dir()]
        analysis.estimated_cases = len(top_level)
    except PermissionError:
        pass

    # 年度分布 (从文件名提取 YYYY)
    import re
    for f in files[:1000]:  # 抽样前 1000 文件 (避免慢)
        if not f.is_file():
            continue
        m = re.search(r"(20\d{2}|19\d{2})", f.name)
        if m:
            year = m.group(1)
            analysis.year_distribution[year] = \
                analysis.year_distribution.get(year, 0) + 1

    # 案号模式 (中国法院案号格式: (YYYY)法院代码+类型+序号)
    case_no_pattern = re.compile(
        r"[\(（](\d{4})[\)）]\s*([一-龥]{2,})?\d+\s*\d+\s*号"
    )
    type_counter: dict[str, int] = {}
    for f in files[:2000]:
        if not f.is_file():
            continue
        m = case_no_pattern.search(f.name)
        if m:
            # 案号类型 (民初/民终/刑初/刑终/行初)
            full = m.group(0)
            if "民初" in full:
                type_counter["民初"] = type_counter.get("民初", 0) + 1
            elif "民终" in full:
                type_counter["民终"] = type_counter.get("民终", 0) + 1
            elif "刑初" in full:
                type_counter["刑初"] = type_counter.get("刑初", 0) + 1
            elif "刑终" in full:
                type_counter["刑终"] = type_counter.get("刑终", 0) + 1
            elif "行初" in full:
                type_counter["行初"] = type_counter.get("行初", 0) + 1
    analysis.type_distribution = type_counter

    # 抽样前 10 个文件
    analysis.sample_files = [
        str(f.relative_to(dir_path)) for f in files[:10] if f.is_file()
    ]

    # 建议映射 (如何导入)
    analysis.suggested_mapping = {
        "docx_files": analysis.file_types.get(".docx", 0),
        "pdf_files": analysis.file_types.get(".pdf", 0),
        "txt_files": analysis.file_types.get(".txt", 0),
        "建议": (
            "用 cn-case-loader 导入 .docx / .txt, "
            "PDF 用 OCR 后导入. "
            "导入后落到 workspace.cases_db (本地库), "
            "原文件保持只读不动"
        ),
    }

    return analysis


# === CLI ===
def main():
    """CLI 入口 (律师 / 开发者调试用)"""
    import argparse
    parser = argparse.ArgumentParser(
        description="PRC-Law 律师工作目录协议 (W16)")
    parser.add_argument("--existing", help="指定已有目录 (只读)")
    parser.add_argument("--analyze", action="store_true",
                        help="分析已有目录")
    parser.add_argument("--init", action="store_true",
                        help="初始化工作目录")
    parser.add_argument("--summary", action="store_true",
                        help="输出摘要")
    args = parser.parse_args()

    ws = Workspace.load(env_existing=args.existing)
    print(f"客户端检测: {ws.client}\n")

    if args.summary or (not args.analyze and not args.init):
        print(ws.summary())

    if args.analyze and ws.existing_dir:
        print(f"\n分析已有目录: {ws.existing_dir}\n")
        analysis = analyze_existing_dir(ws.existing_dir)
        print(f"  总文件: {analysis.total_files}")
        print(f"  总目录: {analysis.total_dirs}")
        print(f"  估计案件数: {analysis.estimated_cases}")
        print(f"  文件类型: {analysis.file_types}")
        print(f"  年度分布: {analysis.year_distribution}")
        print(f"  案号类型分布: {analysis.type_distribution}")
        print(f"  抽样文件: {analysis.sample_files[:5]}")
        print(f"\n  建议:")
        for k, v in analysis.suggested_mapping.items():
            print(f"    {k}: {v}")

    if args.init:
        ws.ensure_layout()
        ws.save_config()
        print(f"\n✅ 初始化完成: {ws.workspace_dir}")
        print(f"   配置: {CONFIG_PATH}")
        print(f"\n下一步: 在工作目录下创建案件:")
        print(f"   mkdir -p {ws.matters_dir}/M-2026-001")


if __name__ == "__main__":
    main()