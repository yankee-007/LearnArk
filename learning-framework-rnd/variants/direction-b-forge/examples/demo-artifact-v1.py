"""m1/agent.py — 最小工具调用 Agent 的第一版（离线 demo 合成作品，不是真实学习证据）。

这一版故意留两个缺口：工具定义没有参数类型，工具异常直接抛出。review 会把它打成
contract=2 / robustness=2，并生成两张缺口卡。
"""

import json
import os
import urllib.request

API_URL = os.environ.get("DEEPSEEK_BASE", "https://api.deepseek.com") + "/chat/completions"
MAX_STEPS = 6

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "读取文本文件",
            "parameters": {},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calc",
            "description": "计算加减乘除表达式",
            "parameters": {},
        },
    },
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
        return read_file(str(args.get("path", "")))
    if name == "calc":
        return calc(str(args.get("expr", "")))
    return "error: unknown tool"


def main(task):
    messages = [{"role": "user", "content": task}]
    for step in range(MAX_STEPS):
        body = json.dumps(
            {"model": "deepseek-chat", "messages": messages, "tools": TOOLS}
        ).encode("utf-8")
        request = urllib.request.Request(
            API_URL, data=body, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            reply = json.loads(response.read().decode("utf-8"))["choices"][0]["message"]
        messages.append(reply)
        calls = reply.get("tool_calls") or []
        if not calls:
            return reply.get("content", "")
        for call in calls:
            name = call["function"]["name"]
            args = json.loads(call["function"].get("arguments") or "{}")
            observation = run_tool(name, args)
            messages.append({"role": "tool", "content": observation})
    return "error: step limit reached"


if __name__ == "__main__":
    print(main("把 in.txt 里的数字求和"))
