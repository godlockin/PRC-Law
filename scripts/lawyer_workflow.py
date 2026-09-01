#!/usr/bin/env python3
"""
lawyer_workflow.py — 6 步律师副驾驶工作流 (W7.5 + W15)

演示完整闭环:
  Step 1: 接案/案件摘要 (matter-intake)
  Step 2: 调解策略 + 本地校准 (mediation_hint + local_calibration)
  Step 3: 法条检索 (retrieval_router 6 级降级)
  Step 4: 文书生成 (md2template_docx + 高亮占位符)
  Step 5: 时效预警 — W14 自动 (timeline → deadline) / W7.2 兜底 (matter-dir)
  Step 6: 总报告 (workflow-report.md)

不引入 LangGraph/AutoGen/ORCHESTRATOR 等复杂框架,
纯 Python 串接, 每个 step 独立可调用, 失败不影响其他 step.

用法:
  python3 scripts/lawyer_workflow.py \\
      --case-json case.json --template templates/lawyer-letter.md \\
      --output-dir ./output/

case.json schema:
  {
    "case_id": "M-2026-001",
    "client": "上海远大贸易有限公司",
    "matter_type": "合同纠纷",
    "amount": 200.0,
    "lawyer_role": "原告",
    "evidence_plaintiff": "强",
    "evidence_defendant": "弱",
    "demand": "...",
    "defense": "...",
    "trigger_date": "2026-08-15",
    "procedural_stage": "诉前",
    "timeline": [                                // W14 优化: 时间线触发自动时效计算
      {"date": "2025-05-01", "event": "应付款日, 被告未付",
       "source": "合同 §4.1 + 发票", "certainty": "确定", "category": "违约日"},
      ...
    ]
  }
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

# W16: 接入 Workspace 单例 (律师工作目录统一解析)
try:
    from workspace import Workspace
except ImportError:
    Workspace = None
SCRIPTS = ROOT / "scripts"


@dataclass
class WorkflowStep:
    name: str
    status: str = "pending"  # pending / running / done / failed / skipped
    output_files: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    elapsed_seconds: float = 0.0


@dataclass
class WorkflowResult:
    case_id: str
    steps: list[WorkflowStep]
    summary: str

    def to_markdown(self) -> str:
        md = f"""# 律师工作流执行报告

> ⚠️ **AI 辅助生成 — 律师审阅后使用** (上海律协指引 2025-08 §13)
> 本报告展示 6 步律师副驾驶工作流执行结果.
> 每步输出文件需律师人工复核, 不替代律师决策.

**案件**: {self.case_id}
**日期**: {date.today().isoformat()}

## 执行步骤

"""
        for i, s in enumerate(self.steps, 1):
            icon = {
                "done": "✅", "failed": "❌", "skipped": "⏭️",
                "running": "⏳", "pending": "❔",
            }.get(s.status, "❔")
            md += f"### Step {i}: {s.name} {icon}\n\n"
            md += f"状态: {s.status} | 耗时: {s.elapsed_seconds:.1f}s\n\n"
            if s.output_files:
                md += "输出:\n"
                for f in s.output_files:
                    md += f"- `{f}`\n"
                md += "\n"
            if s.notes:
                md += "备注:\n"
                for n in s.notes:
                    md += f"- {n}\n"
                md += "\n"

        md += f"""
## 总结

{self.summary}

---

## 律师审阅闸

> ⚠️ **6 步工作流为辅助工具**, 律师必须:
> 1. 复核每步输出文件 (调解策略 / 文书 Word / 时效报告)
> 2. 评估本地校准样本量是否足够
> 3. 评估法条检索来源可信度
> 4. 对 EXPIRED 时效案件立即处理
> 5. 最终决策由律师 + 当事人共同作出
"""
        return md


def run_step(name: str, cmd: list[str], cwd: Path = ROOT,
             timeout: int = 60) -> tuple[bool, str, str]:
    """运行一个 step (subprocess)

    Returns:
        (success, stdout, stderr)
    """
    try:
        result = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return False, "", f"timeout ({timeout}s)"
    except Exception as e:
        return False, "", str(e)


def main():
    parser = argparse.ArgumentParser(
        description="6 步律师副驾驶工作流 (W7.5 + W15 + W16)")
    parser.add_argument("--case-json", required=False,
                        help="案件 JSON 文件")
    parser.add_argument("--output-dir", default=None,
                        help="输出目录 (默认 ~/lawyer-work/matters/<case-id>/)")
    parser.add_argument("--calibration", default=None,
                        help="本地校准 JSON (W7.1, 默认从 Workspace.calibration_path)")
    parser.add_argument("--template", default=None,
                        help="文书模板 (可选, 不提供跳过 Step 4)")
    parser.add_argument("--matters-dir", default=None,
                        help="matter 目录 (默认从 Workspace.matters_dir)")
    parser.add_argument("--workspace", action="store_true",
                        help="打印 Workspace 信息并退出")
    args = parser.parse_args()

    # W16: 加载 Workspace 单例 (律师工作目录)
    if Workspace is None:
        print("❌ workspace 模块不可用, 请检查 scripts/workspace.py", file=sys.stderr)
        sys.exit(1)

    ws = Workspace.load(env_existing=args.matters_dir)
    if args.workspace:
        print(ws.summary())
        return 0

    # 用 Workspace 默认路径覆盖 (如果参数未显式指定)
    if args.calibration is None:
        args.calibration = str(ws.calibration_path) if ws.calibration_path.exists() else None
    if args.matters_dir is None:
        args.matters_dir = str(ws.matters_dir)
    if args.output_dir is None:
        # 输出到 matter/<case-id>/
        case_id = ""
        try:
            case_data = json.loads(Path(args.case_json).read_text(encoding="utf-8"))
            case_id = case_data.get("case_id", "")
        except Exception:
            pass
        if case_id:
            args.output_dir = str(ws.matters_dir / case_id)
        else:
            args.output_dir = str(ws.matters_dir / "_workflow-out")

    case = json.loads(Path(args.case_json).read_text(encoding="utf-8"))
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    steps: list[WorkflowStep] = []
    print(f"\n{'='*60}\n律师副驾驶工作流\n案件: {case.get('case_id', '?')}\n{'='*60}\n")

    # === Step 1: 案件摘要 (matter-intake 等价) ===
    s = WorkflowStep(name="接案 + 案件摘要")
    print(f"\n[Step 1] {s.name}")
    intake_path = output_dir / "01-intake.json"
    intake_data = {
        "case_id": case.get("case_id", "未知"),
        "client": case.get("client", "(待填)"),
        "matter_type": case.get("matter_type", "未知"),
        "amount": case.get("amount", 0),
        "procedural_stage": case.get("procedural_stage", "诉前"),
        "lawyer_role": case.get("lawyer_role", "原告"),
        "evidence": {
            "plaintiff": case.get("evidence_plaintiff", "中"),
            "defendant": case.get("evidence_defendant", "中"),
        },
        "demand": case.get("demand", ""),
        "defense": case.get("defense", ""),
    }
    intake_path.write_text(
        json.dumps(intake_data, ensure_ascii=False, indent=2),
        encoding="utf-8")
    s.output_files.append(str(intake_path))
    s.notes.append(f"案件类型: {intake_data['matter_type']}, 标的: {intake_data['amount']} 万")
    s.status = "done"
    steps.append(s)
    print(f"  ✅ 接案信息已记录: {intake_path}")

    # === Step 2: 调解策略 + 本地校准 ===
    s = WorkflowStep(name="调解策略 + 本地校准")
    print(f"\n[Step 2] {s.name}")
    strategy_path = output_dir / "02-strategy.md"
    cmd = [
        sys.executable, str(SCRIPTS / "mediation_hint.py"),
        "--amount", str(case.get("amount", 0)),
        "--case-type", case.get("matter_type", "合同纠纷"),
        "--role", case.get("lawyer_role", "原告"),
        "--stage", case.get("procedural_stage", "诉前"),
        "--ev-plaintiff", case.get("evidence_plaintiff", "中"),
        "--ev-defendant", case.get("evidence_defendant", "中"),
        "--demand", case.get("demand", ""),
        "--defense", case.get("defense", ""),
        "-o", str(strategy_path),
    ]
    if args.calibration:
        cmd.extend(["--calibration", args.calibration])

    ok, stdout, stderr = run_step("mediation_hint", cmd)
    if ok:
        s.output_files.append(str(strategy_path))
        if args.calibration:
            s.notes.append(f"使用本地校准: {args.calibration}")
        s.status = "done"
        print(f"  ✅ 策略单已生成: {strategy_path}")
    else:
        s.notes.append(f"⚠ mediation_hint 失败: {stderr[:200]}")
        s.status = "failed"
        print(f"  ❌ 失败: {stderr[:100]}")
    steps.append(s)

    # === Step 3: 法条检索 (示例: 民法典 577 条) ===
    s = WorkflowStep(name="关键法条检索")
    print(f"\n[Step 3] {s.name}")
    retrieval_path = output_dir / "03-statute.json"
    # 民事案由通常引 577 (违约) / 188 (时效)
    matter = case.get("matter_type", "合同纠纷")
    if matter in ("合同纠纷", "借贷"):
        article = "577"
        law = "民法典"
    elif matter in ("劳动争议",):
        article = "87"
        law = "劳动合同法"
    elif matter in ("侵权", "交通事故", "医疗损害"):
        article = "1165"
        law = "民法典"
    else:
        article = "188"
        law = "民法典"

    cmd = [
        sys.executable, str(SCRIPTS / "retrieval_router.py"),
        "--law", law, "--article", article,
        "--cross-verify", "--critical", "--json",
    ]
    ok, stdout, stderr = run_step("retrieval", cmd)
    # Step 3 特殊: 即使 exit != 0, 输出合法 JSON 视为降级成功 (W7.3 本身已诚实标注)
    if stdout.strip().startswith("{"):
        retrieval_path.write_text(stdout, encoding="utf-8")
        s.output_files.append(str(retrieval_path))
        try:
            data = json.loads(stdout)
            sc = data.get("source_count", 0)
            cons = data.get("consensus", False)
            s.notes.append(f"{law} 第 {article} 条: {sc} 源, 一致性={cons}")
            if sc < 2:
                s.notes.append("⚠ 单源/零源结果, 律师需复核")
            s.status = "done" if sc > 0 else "skipped"
        except json.JSONDecodeError:
            s.status = "failed"
        print(f"  {'✅' if s.status == 'done' else '⏭️'} 检索结果: {retrieval_path} (源数={sc})")
    else:
        s.notes.append(f"⚠ 检索失败或非 JSON: {stderr[:200]}")
        s.status = "failed"
        print(f"  ❌ 失败")
    steps.append(s)

    # === Step 4: 文书生成 (可选) ===
    s = WorkflowStep(name="文书生成")
    print(f"\n[Step 4] {s.name}")
    if args.template:
        template = Path(args.template)
        if not template.exists():
            s.notes.append(f"⚠ 模板不存在: {template}")
            s.status = "failed"
        else:
            docx_path = output_dir / "04-document.docx"
            cmd = [
                sys.executable, str(SCRIPTS / "md2template_docx.py"),
                str(template),
                "-o", str(docx_path),
                "--no-disclaimer",  # 律师工作流不重复 AI 标识
            ]
            ok, stdout, stderr = run_step("docx", cmd)
            if ok:
                s.output_files.append(str(docx_path))
                s.notes.append("占位符已高亮 (黄色), 律师手动填字段")
                s.status = "done"
                print(f"  ✅ Word 文书已生成: {docx_path}")
            else:
                s.notes.append(f"⚠ Word 生成失败: {stderr[:200]}")
                s.status = "failed"
                print(f"  ❌ 失败")
    else:
        s.notes.append("未提供 --template, 跳过")
        s.status = "skipped"
        print(f"  ⏭️  跳过 (无模板)")
    steps.append(s)

    # === Step 5: 时效预警 (W14 优先, W7.2 兜底) ===
    s = WorkflowStep(name="时效预警 (自动)")
    print(f"\n[Step 5] {s.name}")
    deadline_path = output_dir / "05-deadline.md"
    case_id = case.get("case_id", "未命名案件")
    case_type = case.get("matter_type", "合同纠纷")

    # Step 5a: 优先用 W14 自动计算 (从时间线 JSON)
    timeline_path = output_dir / "05a-timeline.json"
    # 如果 case.json 里有 timeline 字段,先落盘
    timeline_data = case.get("timeline", [])
    if timeline_data:
        timeline_path.write_text(
            json.dumps(timeline_data, ensure_ascii=False, indent=2),
            encoding="utf-8")
        s.notes.append(f"使用 case.json 内置时间线 ({len(timeline_data)} 节点)")

    if timeline_path.exists() and timeline_data:
        cmd = [
            sys.executable, str(SCRIPTS / "deadline_monitor.py"),
            "--timeline", str(timeline_path),
            "--case-type", case_type,
            "--case-id", case_id,
            "--output", str(deadline_path),
        ]
        step_mode = "W14 自动 (时间线)"
    elif args.matters_dir:
        # W7.2 兜底
        cmd = [
            sys.executable, str(SCRIPTS / "deadline_monitor.py"),
            "--matters-dir", args.matters_dir,
            "--output", str(deadline_path),
        ]
        step_mode = "W7.2 (matter-dir)"
    else:
        # W16: 用 Workspace.cases_db 替代硬编码
        cmd = [
            sys.executable, str(SCRIPTS / "deadline_monitor.py"),
            "--db", str(ws.cases_db),
            "--output", str(deadline_path),
        ]
        step_mode = "W7.2 (cases.db)"

    s.notes.append(f"模式: {step_mode}")
    ok, stdout, stderr = run_step("deadline", cmd, timeout=30)
    if ok and deadline_path.exists():
        s.output_files.append(str(deadline_path))
        # 统计 EXPIRED / CRITICAL
        try:
            content = deadline_path.read_text(encoding="utf-8")
            n_exp = content.count("| EXPIRED |") + content.count("🔴 EXPIRED")
            n_cri = content.count("| CRITICAL |") + content.count("🟠 CRITICAL")
            if n_exp:
                s.notes.append(f"⚠ {n_exp} 个时效已过期")
            if n_cri:
                s.notes.append(f"⚠ {n_cri} 个时效 ≤ 7 天")
        except Exception:
            pass
        s.status = "done"
        print(f"  ✅ 时效报告: {deadline_path} (模式: {step_mode})")
    else:
        s.notes.append(f"⚠ 时效预警失败 (cases.db 不存在?)")
        s.status = "skipped"
        print(f"  ⏭️  跳过")
    steps.append(s)

    # === 输出总报告 ===
    summary_lines = [
        f"6 步工作流完成, 案件 {case.get('case_id', '?')}",
        f"- 已完成: {sum(1 for s in steps if s.status == 'done')}/{len(steps)} 步",
        f"- 已跳过: {sum(1 for s in steps if s.status == 'skipped')}",
        f"- 失败: {sum(1 for s in steps if s.status == 'failed')}",
        "",
        "下一步律师审阅:",
        "1. 看 02-strategy.md 调解策略单",
        "2. 看 03-statute.json 法条核验结果",
        "3. 看 04-document.docx 文书, 手动填字段",
        "4. 看 05-deadline.md 时效预警",
    ]
    result = WorkflowResult(
        case_id=case.get("case_id", "?"),
        steps=steps,
        summary="\n".join(summary_lines),
    )

    report_path = output_dir / "00-workflow-report.md"
    report_path.write_text(result.to_markdown(), encoding="utf-8")
    print(f"\n{'='*60}")
    print(f"✅ 工作流完成. 总报告: {report_path}")
    print(f"{'='*60}\n")

    # 总结
    print(f"📊 步骤汇总:")
    for i, st in enumerate(steps, 1):
        icon = {"done": "✅", "failed": "❌", "skipped": "⏭️"}.get(st.status, "❔")
        print(f"   {icon} Step {i}: {st.name}")

    return 0 if not any(s.status == "failed" for s in steps) else 1


if __name__ == "__main__":
    sys.exit(main())