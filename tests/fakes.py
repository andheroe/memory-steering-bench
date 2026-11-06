"""A fake Adaption client for tests: no network, no API key.

Subclasses implement decide(req) and return either
    ("tool", name, input)          a function call, or
    ("text", text, status)         a plain-text answer with no tool call.
`req` is the request seen from the agent's side: system prompt, tool names,
opening message, number of input items so far, and the last tool output.
Every raw request is kept in .requests.
"""

from dataclasses import dataclass
from types import SimpleNamespace


@dataclass
class Req:
    system: str
    tools: list[str]
    opening: str
    n_items: int
    last_output: str | None

    @property
    def employee_id(self) -> str:
        return self.opening.split("employee ID ")[1][:4]


class FakeAdaption:
    def __init__(self):
        self.requests = []
        self.responses = self

    def decide(self, req: Req):
        raise NotImplementedError

    async def create(self, **kw):
        self.requests.append(kw)
        items = kw["input"]
        req = Req(
            system=kw["instructions"],
            tools=[t["name"] for t in kw["tools"]],
            opening=items[0]["content"],
            n_items=len(items),
            last_output=items[-1].get("output"),
        )
        step = self.decide(req)
        if step[0] == "tool":
            _, name, args = step
            out = [{"type": "function_call", "call_id": f"c{len(self.requests)}", "name": name, "arguments": _json(args)}]
            status = "completed"
        else:
            _, text, status = step
            out = [{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": text}]}]
        return SimpleNamespace(
            output=out,
            status=status,
            incomplete_details=None,
            model="fake",
            usage=SimpleNamespace(input_tokens=100, output_tokens=20),
        )


class Scripted(FakeAdaption):
    """Returns the given steps in order, whatever the request."""

    def __init__(self, *steps):
        super().__init__()
        self.steps = list(steps)

    def decide(self, req):
        return self.steps.pop(0)


def _json(args) -> str:
    import json

    return args if isinstance(args, str) else json.dumps(args)
