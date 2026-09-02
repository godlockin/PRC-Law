#!/usr/bin/env python3
"""data_audit.py — 构建期双线法条覆盖度审计 (W30)

策略:
- pkulaw (每日 10K 免费积分) + prc-law-data (零 credit) 双线比对
- 测试集覆盖: 民法典核心条 + 三大程序法 + 数据三法 + 司法解释 (10 部法律 + 38 条)
- 输出差异报告 (4 类: consistent / pkulaw_only / prc_law_data_only / all_miss)
- 落 data/audit/dual_source_audit_YYYYMMDD.json 永久保存

积分预算 (1 天):
- pkulaw 25 积分/次 × 48 次 = 1,200 积分 (远低于每日 10K)
- yuandian: 不调用 (留给律师日常检索)

用法:
    python3 scripts/data_audit.py
    python3 scripts/data_audit.py --cases my_cases.json
    python3 scripts/data_audit.py --dry-run
"""
import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import retrieval_router as rr

AUDIT_DIR = ROOT / "data" / "audit"
AUDIT_DIR.mkdir(parents=True, exist_ok=True)

# 测试集 — 覆盖: 民法典各编 + 三大程序法 + 数据三法 + 司法解释
TEST_CASES = [
    # 民法典 总则 + 各编 (10 条)
    ("中华人民共和国民法典", 1, "基本规定", "core"),
    ("中华人民共和国民法典", 13, "胎儿利益", "core"),
    ("中华人民共和国民法典", 116, "法定代表人", "core"),
    ("中华人民共和国民法典", 143, "民事行为能力", "core"),
    ("中华人民共和国民法典", 188, "诉讼时效 3年", "core"),
    ("中华人民共和国民法典", 195, "时效中断", "core"),
    ("中华人民共和国民法典", 462, "财产共有", "core"),
    ("中华人民共和国民法典", 577, "违约责任", "core"),
    ("中华人民共和国民法典", 1062, "夫妻共同财产", "core"),
    ("中华人民共和国民法典", 1165, "侵权责任", "core"),
    # 三大程序法 (6 条)
    ("中华人民共和国民事诉讼法", 126, "答辩期 15 天", "core"),
    ("中华人民共和国民事诉讼法", 216, "再审申请期", "core"),
    ("中华人民共和国民事诉讼法", 253, "履行通知", "core"),
    ("中华人民共和国刑事诉讼法", 33, "辩护权", "core"),
    ("中华人民共和国刑事诉讼法", 56, "取保候审", "core"),
    ("中华人民共和国行政诉讼法", 46, "起诉期限 6 个月", "core"),
    # 刑法核心 (6 条)
    ("中华人民共和国刑法", 13, "犯罪概念", "core"),
    ("中华人民共和国刑法", 14, "刑事责任年龄", "core"),
    ("中华人民共和国刑法", 16, "无罪", "core"),
    ("中华人民共和国刑法", 17, "未成年人", "core"),
    ("中华人民共和国刑法", 20, "正当防卫", "core"),
    ("中华人民共和国刑法", 21, "紧急避险", "core"),
    # 劳动 + 公司 + 消法 (6 条)
    ("中华人民共和国劳动合同法", 10, "订立合同", "core"),
    ("中华人民共和国劳动合同法", 39, "过错性辞退", "core"),
    ("中华人民共和国劳动合同法", 87, "违法解除 2N", "core"),
    ("中华人民共和国公司法", 16, "出资义务", "core"),
    ("中华人民共和国消费者权益保护法", 55, "欺诈三倍", "core"),
    ("中华人民共和国劳动争议调解仲裁法", 27, "仲裁时效 1 年", "core"),
    # 数据三法 + 配套 (10 条)
    ("中华人民共和国数据安全法", 21, "数据分类分级", "data"),
    ("中华人民共和国数据安全法", 32, "数据出境", "data"),
    ("中华人民共和国个人信息保护法", 13, "个人信息定义", "data"),
    ("中华人民共和国个人信息保护法", 38, "跨境传输条件", "data"),
    ("中华人民共和国个人信息保护法", 66, "罚款上限", "data"),
    ("中华人民共和国网络安全法", 37, "关键信息基础设施", "data"),
    ("中华人民共和国网络安全法", 41, "个人信息保护", "data"),
    ("关键信息基础设施安全保护条例", 8, "运营者义务", "data"),
    ("个人信息出境标准合同办法", 3, "标准合同适用", "data"),
    ("数据出境安全评估办法", 7, "评估触发条件", "data"),
    # 司法解释 (10 条)
    ("最高人民法院关于审理民间借贷案件适用法律若干问题的规定", 25, "民间借贷利率", "judicial"),
    ("最高人民法院关于审理人身损害赔偿案件适用法律若干问题的解释", 17, "误工费", "judicial"),
    ("最高人民法院关于适用《中华人民共和国合同法》若干问题的解释(二)", 26, "违约金调整", "judicial_old"),
    ("最高人民法院关于审理建设工程施工合同纠纷案件适用法律问题的解释(一)", 25, "工程款利息", "judicial"),
    ("最高人民法院关于审理劳动争议案件适用法律问题的解释(一)", 44, "劳动关系确认", "judicial"),
    ("最高人民法院关于适用《中华人民共和国公司法》若干问题的规定(三)", 17, "股东出资", "judicial"),
    ("最高人民法院关于适用《中华人民共和国民法典》婚姻家庭编的解释(一)", 78, "彩礼返还", "judicial"),
    ("最高人民法院关于审理食品安全民事纠纷案件适用法律若干问题的解释(一)", 14, "十倍赔偿", "judicial"),
    ("最高人民法院关于审理侵犯商业秘密民事案件适用法律若干问题的解释", 14, "商业秘密认定", "judicial"),
    ("最高人民法院关于审理证券市场虚假陈述侵权民事赔偿案件的若干规定", 6, "揭露日", "judicial"),
]


def run_audit(test_cases: list, output_path: Path) -> dict:
    """执行审计 (返回结果 dict)"""
    print(f"=== 双线验证: pkulaw + prc-law-data ===")
    print(f"测试集: {len(test_cases)} 条")
    print(f"开始时间: {datetime.now().isoformat()}\n")

    results = {
        "audit_meta": {
            "date": datetime.now().isoformat(),
            "cases_total": len(test_cases),
            "sources": ["pkulaw", "prc-law-data"],
        },
        "cases": [],
        "summary": {
            "consistent": 0,
            "pkulaw_only": 0,
            "prc_law_data_only": 0,
            "all_miss": 0,
        },
    }

    for law, article, expected_desc, category in test_cases:
        print(f"[{len(results['cases']) + 1}/{len(test_cases)}] {law} 第{article}条 ({expected_desc})...")
        case_result = {
            "law": law,
            "article": article,
            "category": category,
            "expected": expected_desc,
            "sources": {},
        }

        # 1. prc-law-data (本地,零 credit,先做避免 pkulaw 影响)
        try:
            from dataset_client import DatasetClient
            client = DatasetClient()
            if client.is_available():
                hit = client.lookup(law, article)
                if hit:
                    case_result["sources"]["prc_law_data"] = {
                        "content_preview": hit.content[:200],
                        "source_detail": hit.source_detail,
                    }
                else:
                    case_result["sources"]["prc_law_data"] = None
            else:
                case_result["sources"]["prc_law_data"] = "unavailable"
        except Exception as e:
            case_result["sources"]["prc_law_data"] = {"error": str(e)}

        # 2. pkulaw
        try:
            os.environ.pop("YUANDIAN_API_KEY", None)
            r = rr.try_yuandian_pkulaw(law, article, None)
            if r:
                case_result["sources"]["pkulaw"] = {
                    "label": r.get("label"),
                    "url": r.get("pkulaw_url"),
                    "content_preview": (r.get("pkulaw_data", {})
                                         .get("result", {})
                                         .get("content", [{}])[0]
                                         .get("text", ""))[:200],
                }
            else:
                case_result["sources"]["pkulaw"] = None
        except Exception as e:
            case_result["sources"]["pkulaw"] = {"error": str(e)}

        # 3. 分类
        sources_hit = []
        for src in ["pkulaw", "prc_law_data"]:
            v = case_result["sources"].get(src)
            if v is None:
                continue
            if isinstance(v, dict) and "error" in v:
                continue
            if v == "unavailable":
                continue
            sources_hit.append(src)
        case_result["sources_hit"] = sources_hit

        if not sources_hit:
            category_result = "all_miss"
        elif "pkulaw" in sources_hit and "prc_law_data" in sources_hit:
            category_result = "consistent"
        elif "pkulaw" in sources_hit:
            category_result = "pkulaw_only"
        elif "prc_law_data" in sources_hit:
            category_result = "prc_law_data_only"
        else:
            category_result = "all_miss"
        case_result["category"] = category_result
        results["summary"][category_result] = results["summary"].get(category_result, 0) + 1
        results["cases"].append(case_result)
        print(f"   → {category_result} | 命中: {', '.join(sources_hit) if sources_hit else '无'}")

    output_path.write_text(
        json.dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n=== 审计报告 ===")
    print(f"  保存: {output_path}\n")
    print(f"  双源一致: {results['summary']['consistent']}")
    print(f"  仅 pkulaw: {results['summary']['pkulaw_only']} (prc-law-data 缺失)")
    print(f"  仅 prc-law-data: {results['summary'].get('prc_law_data_only', 0)} (pkulaw 未查到)")
    print(f"  都未命中: {results['summary']['all_miss']}\n")
    print(f"  credit 状态: ~/.cache/prc-law/yuandian_credit.json = {rr._yuandian_credit_read()}")
    # 注: 这里只打印配额使用次数,不含任何 token/key 敏感信息 (W19 安全策略)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="W30 构建期双线审计")
    parser.add_argument("--cases", type=str, help="自定义测试集 JSON 文件")
    parser.add_argument("--output", type=str, help="指定输出文件 (必须位于 data/audit/ 目录下)")
    parser.add_argument("--dry-run", action="store_true", help="只展示配置,不实际调 pkulaw")
    args = parser.parse_args()

    cases = TEST_CASES
    if args.cases:
        # 安全: 自定义测试集限制在 PRC-Law 目录内,防任意文件读 (W19/W23 模式)
        custom_path = Path(args.cases).resolve()
        if not str(custom_path).startswith(str(ROOT)):
            parser.error(f"--cases 必须在 {ROOT} 内 (当前: {custom_path})")
        if not custom_path.exists():
            parser.error(f"--cases 文件不存在: {custom_path}")
        custom = json.loads(custom_path.read_text(encoding="utf-8"))
        cases = [(c["law"], c["article"], c["expected"], c.get("category", "custom")) for c in custom]
        print(f"使用自定义测试集: {args.cases} ({len(cases)} 条)")

    output_path = (
        Path(args.output) if args.output else (
            AUDIT_DIR / f"dual_source_audit_{datetime.now().strftime('%Y%m%d')}.json"
        )
    ).resolve()
    # 安全: 输出文件限制在 data/audit/ 目录内,防任意文件写 (W19 SSRF 防护风格)
    if not str(output_path).startswith(str(AUDIT_DIR.resolve())):
        parser.error(f"--output 必须在 {AUDIT_DIR} 内 (当前: {output_path})")

    if args.dry_run:
        print(f"DRY RUN: 测试集 {len(cases)} 条, 输出 {output_path}")
        return

    run_audit(cases, output_path)


if __name__ == "__main__":
    main()