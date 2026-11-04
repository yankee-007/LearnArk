"""m1/agent.py — 最小工具调用 Agent 的第二版（离线 demo 合成作品，不是真实学习证据）。

相对第一版：工具定义补齐 parameters 类型，工具异常统一转成 error observation 回填，
模型调用失败也有可读信息。这一版用于演示复评达标与防御性解释。
"""

import json
import os
import urllib.request

API_URL = os.environ.get("DEEPSEEK_BASE", "https://api.deepseek.com") + "/chat/completions"
MAX_STEPS = 6
TOOLS = [
    {"type": "function", "function": {"name": "read_file", "description": "读取文本文件",
     "parameters": {"type": "object", "properties": {"path": {"type": "string"}},
                    "required": ["path"]}}},
    {"type": "function", "function": {"name": "calc", "description": "计算加减乘除表达式",
     "parameters": {"type": "object", "properties": {"expr": {"type": "string"}},
                    "required": ["expr"]}}},
]


def read_file(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def calc(expr):
    allowed = set("0123456789+-*/.() ")
    if not set(expr) <= allowed:
        return "error: expr must be digits/operators"
    return str(eval(expr, {"__builtins__": {}}, {}))


def run_tool(name, args):
    if name == "read_file":
        try:
            return read_file(str(args.get("path", "")))
        except OSError as exc:
            return "error: " + str(exc)
    if name == "calc":
        return calc(str(args.get("expr", "")))
    return "error: unknown tool"


def call_model(messages):
    body = json.dumps({"model": "deepseek-chat", "messages": messages, "tools": TOOLS}).encode("utf-8")
    request = urllib.request.Request(API_URL, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))["choices"][0]["message"]


def main(task):
    messages = [{"role": "user", "content": task}]
    for step in range(MAX_STEPS):
        try:
            reply = call_model(messages)
        except OSError as exc:
            return "error: model call failed: " + str(exc)
        messages.append(reply)
        calls = reply.get("tool_calls") or []
        if not calls:
            return reply.get("content", "")
        for call in calls:
            name = call["function"]["name"]
            args = json.loads(call["function"].get("arguments") or "{}")
            messages.append({"role": "tool", "content": run_tool(name, args)})
    return "error: step limit reached"


if __name__ == "__main__":
    print(main("把 in.txt 里的数字求和"))
