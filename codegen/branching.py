"""
REDCap branching logic transpiler.
"""
from __future__ import annotations

import ast
import re
from typing import Callable, Dict, Any

from codegen.redcap_dict_to_code import sanitize_choice_code

TOKEN_RE = re.compile(
    r"(?P<cb>\[(?P<cb_field>[A-Za-z_][A-Za-z0-9_]*)\((?P<cb_code>[^)]+)\)\])|"
    r"(?P<scalar>\[(?P<scalar_field>[A-Za-z_][A-Za-z0-9_]*)\])|"
    r"(?P<str_sq>'[^']*')|"
    r"(?P<str_dq>\"[^\"]*\")|"
    r"(?P<num>-?\d+(?:\.\d+)?)|"
    r"(?P<op><>|<=|>=|=|<|>)|"
    r"(?P<bool_and>(?i:and\b))|"
    r"(?P<bool_or>(?i:or\b))|"
    r"(?P<bool_not>(?i:not\b))|"
    r"(?P<paren>[()])|"
    r"(?P<ws>\s+)|"
    r"(?P<err>.)"
)

def transpile(expr: str) -> str:
    out = []
    pos = 0
    while pos < len(expr):
        m = TOKEN_RE.match(expr, pos)
        if not m:
            ctx = expr[pos:pos+40]
            raise ValueError(f"Unparseable token at offset {pos}: {ctx!r}")
        
        d = m.groupdict()
        if d['cb']:
            f = d['cb_field'].lower()
            c = d['cb_code']
            out.append(f"_cb(record, {f!r}, {c!r})")
        elif d['scalar']:
            f = d['scalar_field'].lower()
            out.append(f"_v(record, {f!r})")
        elif d['str_sq'] or d['str_dq']:
            out.append(m.group(0))
        elif d['num']:
            out.append(m.group(0))
        elif d['op']:
            op = d['op']
            if op == '=': out.append('==')
            elif op == '<>': out.append('!=')
            else: out.append(op)
        elif d['bool_and']: out.append(' and ')
        elif d['bool_or']: out.append(' or ')
        elif d['bool_not']: out.append(' not ')
        elif d['paren']: out.append(d['paren'])
        elif d['ws']: out.append(' ')
        elif d['err']:
            ctx = expr[pos:pos+40]
            raise ValueError(f"Unparseable token at offset {pos}: {ctx!r}")
            
        pos = m.end()
        
    return "".join(out)


class BranchingTransformer(ast.NodeTransformer):
    def wrap_truthy(self, node):
        if isinstance(node, ast.Call) and getattr(node.func, 'id', None) == '_cmp':
            return node
        if getattr(node, '_truthy_wrapped', False):
            return node
        
        call = ast.Call(
            func=ast.Name(id='_truthy', ctx=ast.Load()),
            args=[node],
            keywords=[]
        )
        call._truthy_wrapped = True
        return call

    def visit_Compare(self, node):
        node = self.generic_visit(node)
        if len(node.ops) != 1 or len(node.comparators) != 1:
            raise ValueError("Dangling comparison or multiple operators")
        op = node.ops[0]
        if isinstance(op, ast.Eq): op_str = "="
        elif isinstance(op, ast.NotEq): op_str = "<>"
        elif isinstance(op, ast.Lt): op_str = "<"
        elif isinstance(op, ast.LtE): op_str = "<="
        elif isinstance(op, ast.Gt): op_str = ">"
        elif isinstance(op, ast.GtE): op_str = ">="
        else:
            raise ValueError(f"Unsupported op: {type(op)}")
            
        return ast.Call(
            func=ast.Name(id='_cmp', ctx=ast.Load()),
            args=[ast.Constant(value=op_str), node.left, node.comparators[0]],
            keywords=[]
        )
        
    def visit_BoolOp(self, node):
        node = self.generic_visit(node)
        node.values = [self.wrap_truthy(v) for v in node.values]
        return node
        
    def visit_UnaryOp(self, node):
        node = self.generic_visit(node)
        if isinstance(node.op, ast.Not):
            node.operand = self.wrap_truthy(node.operand)
        return node


def _truthy(val: Any) -> bool:
    if isinstance(val, bool):
        return val
    if not val or val == "0" or val == 0:
        return False
    return True

def _cmp(op: str, left: Any, right: Any) -> bool:
    left_str = str(left) if left is not None else ""
    right_str = str(right) if right is not None else ""
    
    if op in ("<", "<=", ">", ">="):
        if left_str.strip() == "":
            return False
            
    left_num = None
    right_num = None
    try:
        left_num = float(left_str)
        right_num = float(right_str)
    except ValueError:
        pass
        
    if left_num is not None and right_num is not None:
        l, r = left_num, right_num
    else:
        l, r = left_str, right_str
        
    if op == "=": return l == r
    if op == "<>": return l != r
    if op == "<": return l < r
    if op == "<=": return l <= r
    if op == ">": return l > r
    if op == ">=": return l >= r
    return False

def _v(record: Dict[str, str], field: str) -> str:
    return record.get(field, "")

def _cb(record: Dict[str, str], field: str, code: str) -> str:
    col = f"{field}___{sanitize_choice_code(str(code))}"
    return record.get(col, "")


def validate(src: str) -> ast.Expression:
    try:
        tree = ast.parse(src, mode='eval')
    except SyntaxError as e:
        raise ValueError(f"Parse error: {e}")
        
    tree = BranchingTransformer().visit(tree)
    tree = ast.fix_missing_locations(tree)
    
    allowlist = {
        ast.Expression, ast.Call, ast.Name, ast.Load, ast.Constant, 
        ast.BoolOp, ast.And, ast.Or, ast.UnaryOp, ast.Not,
        ast.Compare, ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE
    }
    
    for node in ast.walk(tree):
        if type(node) not in allowlist:
            raise ValueError(f"Malicious or unsupported node: {type(node)}")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                raise ValueError("Call target must be a simple Name")
            if node.func.id not in {'_v', '_cb', '_cmp', '_truthy'}:
                raise ValueError(f"Call to forbidden function: {node.func.id}")
            if node.keywords:
                raise ValueError("Keyword arguments not allowed")
                
    return tree


def compile_predicate(expr: str) -> Callable[[Dict[str, str]], bool]:
    src = transpile(expr)
    tree = validate(src)
    code = compile(tree, filename='<ast>', mode='eval')
    
    def predicate(record: Dict[str, str]) -> bool:
        res = eval(code, {"__builtins__": {}}, {
            "_v": _v,
            "_cb": _cb,
            "_cmp": _cmp,
            "_truthy": _truthy,
            "record": record
        })
        return bool(_truthy(res))
        
    if hasattr(ast, 'unparse'):
        predicate.source = ast.unparse(tree)
    else:
        predicate.source = src
        
    predicate.redcap = expr
    return predicate

