"""Offline documentation checks and module-local AST evidence detection."""
import argparse
import ast
import json
import os
from pathlib import Path
import re
import sys

from .phrases import SPELLCHECKING, NOSPELLCHECKING, GENERIC_NAMES

ROUTES = ({'names': ['SpellChecker'], 'sources': ['spellchecker'], 'methods': ['correction', 'candidates', 'unknown', 'known'], 'direct': False}, {'names': ['Speller'], 'sources': ['autocorrect'], 'methods': ['autocorrect_word', 'autocorrect_sentence'], 'direct': True}, {'names': ['SymSpell'], 'sources': ['symspellpy', 'symspellpy.symspellpy'], 'methods': ['lookup', 'lookup_compound'], 'direct': False}, {'names': ['HunSpell', 'Hunspell'], 'sources': ['hunspell'], 'methods': ['spell', 'suggest', 'bulk_suggest'], 'direct': False}, {'names': ['TextBlob'], 'sources': ['textblob'], 'methods': ['correct'], 'direct': False})
GENERIC_CALL_FORMS = ("attribute-any-base", "from-imported-or-aliased-bare")
PAIR_REQUIREMENT = "assigned receiver or direct chained construction, same module"
EXCLUDED = {'.git', '__pycache__', '.venv', 'venv', 'env', '.env', 'virtualenv'}


def match_phrases(text):
    """Return denial and positive occurrences, removing longest spans first."""
    text = text.lower()
    groups = []
    for phrases in (NOSPELLCHECKING, SPELLCHECKING):
        matches = []
        for phrase in sorted(phrases, key=len, reverse=True):
            start = text.find(phrase)
            while start >= 0:
                matches.append(phrase)
                text = text[:start] + ' ' * len(phrase) + text[start + len(phrase):]
                start = text.find(phrase)
        groups.append(matches)
    return tuple(groups)


def prose(text):
    result = []
    fenced = False
    for line in text.splitlines():
        if line.lstrip().startswith('```'):
            fenced = not fenced
        elif not fenced:
            result.append(line.replace('`', ''))
    return '\n'.join(result)


def has_evidence(source):
    """Recognize paired calls without importing or executing inspected code."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return False
    nodes = list(ast.walk(tree))
    shadows = {n.name for n in nodes if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
    imports = {}
    from_imports = set()
    for node in nodes:
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports[alias.asname or alias.name.split('.')[0]] = alias.name if alias.asname else alias.name.split('.')[0]
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            for alias in node.names:
                imports[alias.asname or alias.name] = node.module + '.' + alias.name
                from_imports.add(alias.asname or alias.name)

    def resolve(expr):
        if isinstance(expr, ast.Name):
            return '' if expr.id in shadows else imports.get(expr.id, '')
        if isinstance(expr, ast.Attribute):
            base = resolve(expr.value)
            if expr.attr in shadows:
                return ''
            return base + '.' + expr.attr if base else ''
        return ''

    def construction(expr):
        if isinstance(expr, ast.Call):
            path = resolve(expr.func)
            for index, route in enumerate(ROUTES):
                if path in {source + '.' + name for source in route['sources'] for name in route['names']}:
                    if path.split('.')[-1] not in shadows:
                        return index
        return None

    instances = {}

    def instance(expr):
        if isinstance(expr, ast.Name) and expr.id not in shadows:
            return instances.get(expr.id)
        return construction(expr)

    def visit(node):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr in GENERIC_NAMES and func.attr not in shadows:
                return True
            if isinstance(func, ast.Name) and func.id in from_imports and resolve(func).split('.')[-1] in GENERIC_NAMES and resolve(func).split('.')[-1] not in shadows:
                return True
            if isinstance(func, ast.Attribute):
                kind = instance(func.value)
                if kind is not None and func.attr in ROUTES[kind]['methods']:
                    return True
            kind = instance(func)
            if kind is not None and ROUTES[kind]['direct']:
                return True
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            if node.value is not None and visit(node.value):
                return True
            kind = construction(node.value)
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name):
                    instances[target.id] = kind
            return False
        return any(visit(child) for child in ast.iter_child_nodes(node))

    return visit(tree)


def audit(repo, ignore=(), verbose=False):
    repo = Path(repo)
    if not repo.is_dir():
        raise OSError('Repository is not a directory: ' + str(repo))
    positives, denials, test_claims, evidence = [], [], [], []
    decisions = []
    def paths():
        def onerror(error):
            raise error
        for directory, dirs, files in os.walk(repo, onerror=onerror):
            base = Path(directory)
            kept = []
            for name in sorted(dirs):
                path = base / name
                label = path.relative_to(repo).as_posix()
                if name in EXCLUDED or path.is_symlink() or (path / 'pyvenv.cfg').is_file() or any(label.startswith(prefix) or (label + '/').startswith(prefix) for prefix in ignore):
                    decisions.append('skip ' + label)
                else:
                    kept.append(name)
            dirs[:] = kept
            for name in sorted(files):
                yield base / name

    for path in paths():
        relative = path.relative_to(repo)
        label = relative.as_posix()
        if any(part in EXCLUDED for part in relative.parts) or any((repo.joinpath(*relative.parts[:i]) / 'pyvenv.cfg').is_file() for i in range(1, len(relative.parts))):
            continue
        if any(label.startswith(prefix) for prefix in ignore):
            decisions.append('skip ' + label)
            continue
        if path.is_symlink() or not path.is_file():
            continue
        doc = label == 'README.md' or (relative.parts[0] == 'docs' and path.suffix == '.md')
        test = 'tests' in relative.parts[:-1]
        if doc or test or path.suffix == '.py':
            text = path.read_text(encoding='utf-8')
            decisions.append('scan ' + label)
            if doc or test:
                no, yes = match_phrases(prose(text))
                if doc:
                    positives.extend(yes)
                    denials.extend(no)
                elif test:
                    test_claims.extend(yes)
            if path.suffix == '.py':
                found = has_evidence(text)
                decisions.append('evidence ' + label + ': ' + str(found))
                if found:
                    evidence.append(label)
    findings = []
    def finding(rule, severity, message):
        findings.append({'rule': rule, 'severity': severity, 'verdict': 'FAIL', 'message': message})
    if positives and not evidence:
        finding('documented-spell-checking-claim-false', 'HIGH', 'Documentation claims the checked feature, but no source evidence was found.')
    elif test_claims and not evidence:
        finding('documented-spell-checking-claim-false', 'MEDIUM', 'Only test fixtures claim the checked feature; no source evidence was found.')
    if denials and evidence:
        finding('documented-no-spell-checking-claim-false', 'HIGH', 'Documentation denies the checked feature, but source evidence was found.')
    return findings, decisions


class Parser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(1, self.prog + ': error: ' + message + '\n')


def main(argv=None):
    parser = Parser(prog='spell-checking-claim-audit')
    parser.add_argument('--version', action='version', version='0.1.0')
    sub = parser.add_subparsers(dest='command', required=True, parser_class=Parser)
    command = sub.add_parser('audit')
    command.add_argument('repo', nargs='?', default='.')
    command.add_argument('--json', action='store_true')
    command.add_argument('--verbose', action='store_true')
    command.add_argument('--ignore', action='append', default=[])
    command.add_argument('--fail-on', choices=['high', 'medium'], default='high')
    args = parser.parse_args(argv)
    try:
        findings, decisions = audit(args.repo, args.ignore)
    except (OSError, UnicodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if args.verbose:
        print('Scope: README.md, docs/**/*.md, tests/**; evidence: repository *.py', file=sys.stderr)
        for decision in decisions:
            print(decision, file=sys.stderr)
    if args.json:
        print(json.dumps(findings))
    elif findings:
        for item in findings:
            print('{severity} {rule}: {message}'.format(**item))
    else:
        print('PASS: no contradictory claims found.')
    return 2 if any(f['severity'] == 'HIGH' or args.fail_on == 'medium' for f in findings) else 0
