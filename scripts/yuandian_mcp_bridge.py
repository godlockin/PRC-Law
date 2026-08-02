#!/usr/bin/env python3
"""元典法律 MCP stdio bridge

把元典 REST API 包装为 MCP stdio server，供 Claude Code 直接调用。
解决 SSE 流握手失败问题。
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
import urllib.error


API_KEY = os.environ.get("YUANDIAN_API_KEY", "YOUR_API_KEY_HERE")
BASE_URL = "https://open.chineselaw.com"


def call_yuandian(endpoint: str, payload: dict) -> dict:
    """调用元典 REST API (POST)"""
    url = f"{BASE_URL}{endpoint}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "X-API-Key": API_KEY,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}: {e.reason}", "body": e.read().decode(errors="replace")[:500]}
    except Exception as e:
        return {"error": str(e)}


def call_yuandian_get(endpoint: str, params: dict) -> dict:
    """调用元典 REST API (GET)"""
    import urllib.parse
    qs = urllib.parse.urlencode(params)
    url = f"{BASE_URL}{endpoint}?{qs}"
    req = urllib.request.Request(
        url,
        headers={"X-API-Key": API_KEY},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}: {e.reason}", "body": e.read().decode(errors="replace")[:500]}
    except Exception as e:
        return {"error": str(e)}


# ── Tool definitions ──────────────────────────────────────────

TOOLS = [
    {
        "name": "yuandian_law_search",
        "description": "元典法律法规语义检索 — 按自然语言 query 做法条级语义检索，支持时效性/效力级别/日期过滤。返回法条内容及所属法规信息。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "检索问题 / 自然语言查询"},
                "sxx": {"type": "string", "description": "时效性过滤：现行有效/失效/已被修改/部分失效/尚未生效"},
                "effect_level": {"type": "string", "description": "效力级别：法律/行政法规/司法解释/部门规章 等"},
                "return_num": {"type": "number", "description": "返回数量，默认 20，最大 45"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "yuandian_ft_search",
        "description": "元典法条关键词检索 — 按 keyword 检索法条内容，支持效力级别/时效性/地域/发布部门过滤。返回法条列表含内容、条号、所属法规。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "keyword": {"type": "string", "description": "法条内容关键词（必填）"},
                "sxx": {"type": "string", "description": "时效性过滤"},
                "xljb": {"type": "string", "description": "效力级别过滤"},
                "dy": {"type": "string", "description": "地域过滤"},
                "top_k": {"type": "number", "description": "返回条数，默认 10，最大 50"},
            },
            "required": ["keyword"],
        },
    },
    {
        "name": "yuandian_fg_search",
        "description": "元典法规检索 — 检索法规列表，支持法规名称/时效性/地域/效力级别/发布日期等过滤。返回法规基础信息和片段。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "keyword": {"type": "string", "description": "法规内容关键词"},
                "fgmc": {"type": "string", "description": "法规名称过滤"},
                "sxx": {"type": "string", "description": "时效性过滤"},
                "xljb": {"type": "string", "description": "效力级别过滤"},
                "dy": {"type": "string", "description": "地域过滤"},
                "top_k": {"type": "number", "description": "返回条数，默认 10，最大 50"},
            },
        },
    },
    {
        "name": "yuandian_fg_detail",
        "description": "元典法规详情 — 查询法规详情，含法规内容全文、时效性、发布/实施日期、发布部门。支持按日期定位历史版本。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "法规 ID"},
                "fgmc": {"type": "string", "description": "法规名称（id 为空时必填）"},
                "refer_date": {"type": "string", "description": "参考日期 yyyy-MM-dd，用于定位当时有效版本"},
            },
        },
    },
    {
        "name": "yuandian_ft_detail",
        "description": "元典法条详情 — 查询单条法条详情，可通过 id 或法规名+法条号查询，支持按日期定位版本。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "法条 ID"},
                "fgmc": {"type": "string", "description": "法规名称"},
                "ftnum": {"type": "string", "description": "法条号/名称"},
                "refer_date": {"type": "string", "description": "参考日期 yyyy-MM-dd"},
            },
        },
    },
    {
        "name": "yuandian_case_search",
        "description": "元典案例检索 — 检索裁判文书，按关键词/案号/案由/法院/审判程序/裁判日期过滤。返回案例列表含案号、法院、案由、裁判日期等。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "keyword": {"type": "string", "description": "案例关键词"},
                "case_number": {"type": "string", "description": "案号"},
                "cause_of_action": {"type": "string", "description": "案由"},
                "court": {"type": "string", "description": "法院名称"},
                "procedure": {"type": "string", "description": "审判程序：一审/二审/再审/执行"},
                "judgment_date_start": {"type": "string", "description": "裁判日期起 yyyy-MM-dd"},
                "judgment_date_end": {"type": "string", "description": "裁判日期止 yyyy-MM-dd"},
                "top_k": {"type": "number", "description": "返回条数，默认 10，最大 30"},
            },
        },
    },
    {
        "name": "yuandian_company_search",
        "description": "元典企业信息检索 — 按企业名称/统一社会信用代码/注册号检索工商登记信息。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "keyword": {"type": "string", "description": "企业名称/统一社会信用代码/注册号"},
                "top_k": {"type": "number", "description": "返回条数，默认 10"},
            },
            "required": ["keyword"],
        },
    },
    {
        "name": "yuandian_balance",
        "description": "查询元典 API 账户剩余积分和权益余额。无需参数。",
        "inputSchema": {"type": "object", "properties": {}},
    },
]

# ── MCP stdio handler ────────────────────────────────────────

def handle_request(req: dict) -> dict:
    method = req.get("method", "")
    req_id = req.get("id", 0)

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {
                    "name": "yuandian-mcp-bridge",
                    "version": "1.0.0",
                },
            },
        }

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}

    if method == "tools/call":
        params = req.get("params", {})
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        result = _call_tool(tool_name, arguments)
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
        }

    if method == "notifications/initialized":
        return None  # no response for notifications

    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Method not found: {method}"}}


def _call_tool(name: str, args: dict) -> dict:
    if name == "yuandian_law_search":
        payload = {
            "query": args.get("query", ""),
            "return_num": args.get("return_num", 20),
        }
        if args.get("sxx"):
            payload["fatiao_filter"] = payload.get("fatiao_filter", {})
            payload["fatiao_filter"]["sxx"] = [args["sxx"]]
        if args.get("effect_level"):
            payload["fatiao_filter"] = payload.get("fatiao_filter", {})
            payload["fatiao_filter"]["effect1"] = [args["effect_level"]]
        return call_yuandian("/open/law_vector_search", payload)

    elif name == "yuandian_ft_search":
        return call_yuandian("/open/rh_ft_search", {
            k: v for k, v in {
                "keyword": args.get("keyword", ""),
                "top_k": args.get("top_k", 10),
                "sxx": args.get("sxx"),
                "xljb_1": args.get("xljb"),
                "dy": args.get("dy"),
            }.items() if v is not None
        })

    elif name == "yuandian_fg_search":
        return call_yuandian("/open/rh_fg_search", {
            k: v for k, v in {
                "keyword": args.get("keyword"),
                "fgmc": args.get("fgmc"),
                "sxx": args.get("sxx"),
                "xljb_1": args.get("xljb"),
                "dy": args.get("dy"),
                "top_k": args.get("top_k", 10),
            }.items() if v is not None
        })

    elif name == "yuandian_fg_detail":
        return call_yuandian("/open/rh_fg_detail", {
            k: v for k, v in {
                "id": args.get("id"),
                "fgmc": args.get("fgmc"),
                "refer_date": args.get("refer_date"),
            }.items() if v is not None
        })

    elif name == "yuandian_ft_detail":
        return call_yuandian("/open/rh_ft_detail", {
            k: v for k, v in {
                "id": args.get("id"),
                "fgmc": args.get("fgmc"),
                "ftnum": args.get("ftnum"),
                "refer_date": args.get("refer_date"),
            }.items() if v is not None
        })

    elif name == "yuandian_case_search":
        payload = {"top_k": args.get("top_k", 10)}
        if args.get("keyword"):
            payload["keyword"] = args["keyword"]
        if args.get("case_number"):
            payload["ah"] = args["case_number"]
        if args.get("cause_of_action"):
            payload["ay"] = [args["cause_of_action"]]
        if args.get("court"):
            payload["jbdw"] = [args["court"]]
        if args.get("procedure"):
            payload["spcx"] = args["procedure"]
        if args.get("judgment_date_start"):
            payload["cprq_start"] = args["judgment_date_start"]
        if args.get("judgment_date_end"):
            payload["cprq_end"] = args["judgment_date_end"]
        return call_yuandian("/open/rh_ptal_search", payload)

    elif name == "yuandian_company_search":
        # GET 接口，参数名是 name 不是 keyword
        return call_yuandian_get("/open/rh_enterpriseSearch", {
            "name": args.get("keyword", ""),
            "top_k": str(args.get("top_k", 10)),
        })

    elif name == "yuandian_balance":
        # 无对应 REST 接口，返回提示
        return {"error": "余额查询接口暂不可用（API 目录中无 user_balance 路由）", "hint": "请登录 https://open.chineselaw.com 查看余额"}

    return {"error": f"Unknown tool: {name}"}


def main():
    if not API_KEY:
        error_msg = json.dumps({
            "jsonrpc": "2.0", "id": 0,
            "error": {"code": -32000, "message": "YUANDIAN_API_KEY not set. Export it in ~/.zsh/env or environment."}
        })
        print(error_msg, flush=True)
        sys.exit(1)

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        resp = handle_request(req)
        if resp is not None:
            print(json.dumps(resp, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
