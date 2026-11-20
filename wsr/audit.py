"""Flag kernel runs that may break the process rules, for a labeller to review.

  python -m wsr.audit <run_dir>        writes <run_dir>/audit.json

Flags are leads, not verdicts: a labeller reads and judges each one, and the labels made before the results are
recorded in audit.json's "review".
The rules are the Sparks Exp 8 rules: any analysis of the weights and of forward-pass results is allowed (one
weight matrix applied to measured activations, as attribution, included); simulating the network's computation on an
input in the kernel, and training or iterative fitting, are not.
  activation_product   a matrix product in a run that uses both the weights and forward-pass results (allowed as
                       analysis; a violation when it chains layers to compute what the model would output)
  embedding_lookup     rows of the embedding matrix indexed in code, directly or through a name bound to it in the
                       same run (could be rebuilding the model's input; weight algebra on vocabulary rows is allowed)
  layer_math           softmax-, RMSNorm- or RoPE-like arithmetic in a run that loads weights or has a matrix product
                       (could be part of a forward pass in the agent's own code)
  autograd             gradients turned back on, backward passes or optimizers (training, forbidden)
The kernel is persistent, so each run is checked together with the functions it calls (directly or through each
other) that earlier runs defined; what is found inside them is reported at the line of the call.
"""
import ast
import json
import sys
from pathlib import Path

GRAD_CALLS = {"backward", "enable_grad", "grad", "vjp", "jvp", "jacrev", "jacfwd"}
PRODUCT_CALLS = {"dot", "matmul", "einsum", "tensordot", "inner", "vdot", "multi_dot"}
ACTIVATIONS = ("fwd_", "hidden_", "mlp_act_", "attn_")


def names(node: ast.AST) -> set[str]:
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)} | \
           {n.attr for n in ast.walk(node) if isinstance(n, ast.Attribute)}


def strings(node: ast.AST) -> list[str]:
    return [n.value for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, str)]


def called(node: ast.AST) -> set[str]:
    return {n.func.id for n in ast.walk(node) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}


def parse(code: str) -> ast.Module:
    try:
        return ast.parse(code)
    except SyntaxError:
        return ast.Module(body=[], type_ignores=[])


def flags(tree: ast.Module, defs: dict[str, ast.FunctionDef]) -> dict[str, list[int]]:
    nodes = list(ast.walk(tree))
    helpers, todo = {}, called(tree)
    while todo:  # earlier runs' functions this run calls, directly or through each other
        f = todo.pop()
        if f in defs and f not in helpers:
            helpers[f] = defs[f]
            todo |= called(defs[f])
    calls = [n.lineno for n in nodes if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and
             n.func.id in helpers]
    line = {id(n): min(calls, default=0) for f in helpers.values() for n in ast.walk(f)}
    nodes += [n for f in helpers.values() for n in ast.walk(f)]

    def lines(found: list[ast.AST]) -> list[int]:
        return sorted({line.get(id(n), n.lineno) for n in found})

    products = [n for n in nodes if isinstance(n, ast.BinOp) and isinstance(n.op, ast.MatMult)] + \
               [n for n in nodes if isinstance(n, ast.Call) and (names(n.func) & PRODUCT_CALLS)]
    uses_weights = bool(names(tree) & {"load", "load_original"} or
                        any(names(f) & {"load", "load_original"} for f in helpers.values()))
    uses_activations = any(a in s for t in [tree, *helpers.values()] for s in strings(t) for a in ACTIVATIONS)
    out = {}
    if products and uses_weights and uses_activations:
        out["activation_product"] = lines(products)
    embedding = {t.id for n in nodes if isinstance(n, ast.Assign) and "embed_tokens" in " ".join(strings(n.value))
                 for t in n.targets if isinstance(t, ast.Name)}  # names bound to the embedding matrix in this run
    lookups = [n for n in nodes if isinstance(n, ast.Subscript) and isinstance(n.ctx, ast.Load) and
               ("embed_tokens" in " ".join(strings(n.value)) or names(n.value) & embedding)]
    if lookups:
        out["embedding_lookup"] = lines(lookups)
    math = [n for n in nodes if isinstance(n, ast.Call) and names(n.func) & {"exp", "rsqrt", "softmax"}] + \
           [n for n in nodes if isinstance(n, ast.Call) and "sqrt" in names(n.func) and "mean" in names(n)]
    trig = [n for n in nodes if isinstance(n, ast.Call) and names(n.func) & {"cos", "sin"}]
    if {"cos", "sin"} <= set().union(*(names(n.func) for n in trig)):  # rotary position embedding
        math += trig
    if math and (uses_weights or products):  # weights loaded by earlier runs persist; a product stands in for them
        out["layer_math"] = lines(math)
    grads = [n for n in nodes if isinstance(n, ast.Call) and (names(n.func) & GRAD_CALLS or
             (names(n.func) & {"set_grad_enabled", "requires_grad_"} and not
              any(isinstance(a, ast.Constant) and a.value is False for a in n.args)))] + \
            [n for n in nodes if isinstance(n, ast.Attribute) and n.attr in {"optim", "autograd"}] + \
            [n for n in nodes if isinstance(n, ast.keyword) and n.arg == "requires_grad" and
             not (isinstance(n.value, ast.Constant) and n.value.value is False)]
    if grads:
        out["autograd"] = lines(grads)
    return out


def main() -> None:
    run_dir = Path(sys.argv[1])
    events = [json.loads(l) for l in (run_dir / "tool_calls.jsonl").read_text().splitlines()]
    runs = [e["code"] for e in events if e["kind"] == "python"]
    found, defs = [], {}
    for i, code in enumerate(runs, 1):
        tree = parse(code)
        if f := flags(tree, defs):
            found.append({"run": i, "flags": f})
        defs |= {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    path = run_dir / "audit.json"
    review = json.loads(path.read_text())["review"] if path.exists() else {}
    path.write_text(json.dumps({"runs": len(runs), "flagged": found, "review": review}, indent=1))
    print(json.dumps(found))


if __name__ == "__main__":
    main()
