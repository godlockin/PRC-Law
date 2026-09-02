#!/usr/bin/env python3
"""pkulaw MCP stdio bridge — 北大法宝 MCP over HTTPS

把 pkulaw `apim-gateway.pkulaw.com` 的 10 个 MCP 服务包装为 stdio bridge,
供 Claude Code 直接调用。streamablehttp 协议 → 用 urllib POST/GET 模拟。

Token 来源: 环境变量 PKULAW_TOKEN (优先) 或 ~/.zshrc 里 PKULAW_TOKEN=...

10 服务 (积分/次):
- mcp-fatiao (精准查找法条-关键词)    : 25
- mcp-law    (检索法律法规-关键词)    : 25
- mcp-law-search-service (语义)        : 125
- mcp-case   (检索司法案例-关键词)    : 25
- mcp-case-search-service (语义)      : 125
- law_recognition (法条识别与溯源)    : 125
- add-doc-link (法宝超链)              : 125
- pku_citation_validator (修正幻觉)    : 125
- case_number_recognition (案号识别)    : 125
- mcp-law-agg (法律智能检索聚合)       : 125
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request


def _resolve_token() -> str:
    """从环境变量读 PKULAW_TOKEN;若未设置,尝试 source ~/.zshrc"""
    tok = os.environ.get("PKULAW_TOKEN", "").strip()
    if tok and tok != "YOUR_TOKEN_HERE":
        # 允许 "Bearer xxx" 或纯 xxx
        return tok.replace("Bearer ", "").strip()
    # 子进程 fallback (Claude Code / hook 隔离场景)
    try:
        result = subprocess.run(
            ["zsh", "-c", "source ~/.zshrc 2>/dev/null; echo $PKULAW_TOKEN"],
            capture_output=True, text=True, timeout=5,
        )
        tok = result.stdout.strip()
        if tok:
            return tok.replace("Bearer ", "").strip()
    except Exception:
        pass
    return ""


TOKEN = _resolve_token()
BASE_URL = "https://apim-gateway.pkulaw.com"


def call_pkulaw(service: str, tool_name: str, arguments: dict) -> dict:
    """调用 pkulaw MCP 端点 (JSON-RPC over HTTPS POST)

    Args:
        service: 服务路径, 如 "mcp-fatiao" / "mcp-law" / "mcp-law-agg/mcp"
        tool_name: 工具名, 如 "get_law_item_content"
        arguments: 工具入参 dict
    """
    if not TOKEN:
        return {"error": "PKULAW_TOKEN 未配置 (环境变量或 ~/.zshrc)"}

    url = f"{BASE_URL}/{service}"
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": arguments,
        },
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Authorization": f"Bearer {TOKEN}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
            # streamablehttp 可能返回 SSE 格式 (data: {...})
            for line in body.split("\n"):
                if line.startswith("data: "):
                    return json.loads(line[6:])
            return json.loads(body)
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}: {e.reason}",
                "body": e.read().decode(errors="replace")[:500]}
    except Exception as e:
        return {"error": str(e)}


# ── Tool definitions ──────────────────────────────────────────

TOOLS = [
    {
        "name": "get_law_item_content",
        "description": "北大法宝 · 精准查找法条 (关键词) — 按法规名+条号定位法条原文,含两款以上全文+元数据 (Title/Url/IssueDate/TimelinessDic/FullText)。25 积分/次。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "法规名称, 如 '中华人民共和国民法典' 或 '刑法'"},
                "tiao_num": {"type": "number", "description": "条号, 如 188 或 188.1 (第188条第1款)"},
            },
            "required": ["title", "tiao_num"],
        },
    },
    {
        "name": "get_law_list",
        "description": "北大法宝 · 查询法规列表 — 按关键词定位法规,返回前 20 条。25 积分/次。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "关键词 / 法规标题"},
                "category": {"type": "string", "description": "可选分类: 民法/刑法/行政法/经济法/..."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "search_law_semantic",
        "description": "北大法宝 · 检索法律法规 (语义) — 自然语言提问,理解语义返回相关法规。125 积分/次。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "自然语言问题"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "search_case_keyword",
        "description": "北大法宝 · 检索司法案例 (关键词) — 案例标题或关键词定位。25 积分/次。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "案例标题 / 关键词"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "search_case_semantic",
        "description": "北大法宝 · 检索司法案例 (语义) — 案情自然语言描述,语义匹配类案。125 积分/次。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "案情描述"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "law_recognition",
        "description": "北大法宝 · 法条识别与溯源 — 从文本中识别法规名称和条款,返回标准名称+法条原文。125 积分/次。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "含法条引用的文本"},
            },
            "required": ["text"],
        },
    },
    {
        "name": "citation_validator",
        "description": "北大法宝 · 修正生成幻觉-法条 — 分析上下文,返回准确法条原文 (消除 LLM 幻觉)。125 积分/次。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "法条引用问题"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "case_number_recognition",
        "description": "北大法宝 · 案号识别与溯源 — 精准提取案号,关联权威案例原文。125 积分/次。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "含案号的文本"},
            },
            "required": ["text"],
        },
    },
    {
        "name": "smart_search",
        "description": "北大法宝 · 法律智能检索 (聚合) — 一次集成 10 工具, 检索/核验/溯源一站式打通。125 积分/次。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "智能检索问题"},
            },
            "required": ["query"],
        },
    },
]


# ── MCP stdio protocol ───────────────────────────────────────

def handle_request(req: dict) -> dict:
    """处理 MCP JSON-RPC 请求"""
    method = req.get("method")
    req_id = req.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {
                    "name": "pkulaw-bridge",
                    "version": "1.0.0",
                },
            },
        }
    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": TOOLS},
        }
    if method == "tools/call":
        params = req.get("params", {})
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        # 路由到对应服务
        SERVICE_MAP = {
            "get_law_item_content": "mcp-fatiao",
            "get_law_list": "mcp-law",
            "search_law_semantic": "mcp-law-search-service",
            "search_case_keyword": "mcp-case",
            "search_case_semantic": "mcp-case-search-service",
            "law_recognition": "law_recognition",
            "citation_validator": "pku_citation_validator",
            "case_number_recognition": "case_number_recognition",
            "smart_search": "mcp-law-agg/mcp",
        }
        service = SERVICE_MAP.get(tool_name)
        if not service:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"unknown tool: {tool_name}"},
            }

        result = call_pkulaw(service, tool_name, arguments)
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
        }

    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"unknown method: {method}"},
    }


def main() -> None:
    """stdio loop: 读 JSON-RPC 行, 写响应行"""
    if not TOKEN:
        print("⚠ PKULAW_TOKEN 未配置 — 设置环境变量后重试", file=sys.stderr)
        print("  export PKULAW_TOKEN=<your-token>", file=sys.stderr)
        sys.exit(1)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            resp = handle_request(req)
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()
        except json.JSONDecodeError as e:
            err = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": f"parse error: {e}"},
            }
            sys.stdout.write(json.dumps(err) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()