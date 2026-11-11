# Documentation claim auditor

An offline, deterministic auditor for claims about finding words that are
spelled wrong and suggesting the right spelling for them. Requires Python
3.9 or newer and only the standard library at runtime. Inspected code is
never executed. The auditor makes no network requests and writes no files.

## Install and run

```sh
python3 -m pip install .
spell-checking-claim-audit --version
spell-checking-claim-audit audit
spell-checking-claim-audit audit /path/to/repo --json
python3 -m spell_checking_claim_audit audit . --verbose
spell-checking-claim-audit audit --ignore vendor/ .
spell-checking-claim-audit audit . --ignore vendor/ --ignore generated/ --fail-on medium
```

The repository defaults to the current directory. Each repeatable ignore
option takes one relative path prefix. Verbose output reports scope and
per-file decisions on standard error. JSON output is an array of findings;
each contains rule, severity, verdict, and message fields. An empty array
means PASS. Exit 0 means no findings at the selected threshold, exit 2 means
findings at or above it, and exit 1 means usage or input/output error.
The default threshold is high; medium also fails when explicitly selected.

## Scope and rules

The root README.md and Markdown files recursively beneath docs/ are the
shipped documentation. Triple-backtick fenced code blocks are excluded;
inline backticks are removed while their content remains prose. Matching
uses case-insensitive exact substrings without stemming, fuzzy matching,
or hyphen normalization. Denial spans are removed before positive matching.
Longest-first matching blanks each span, making each occurrence match once
under its longest phrase. Restatements can be missed.

A positive claim without evidence is HIGH. A denial contradicted by source
evidence is HIGH. A denial with no evidence passes. Claims only in files
under a tests/ directory produce MEDIUM when evidence is absent. Multiple
occurrences collapse into one finding per rule family. No claims passes.

```text
documented-spell-checking-claim-false
documented-no-spell-checking-claim-false
```

All Python sources are checked recursively, excluding .git/, bytecode
caches, and virtual environments, including directories with pyvenv.cfg.
Imports and aliases are resolved within a single module. A local function
or class shadows its route name throughout that module. Imports alone,
comments, strings, uncalled references, external commands, and pairs split
between modules provide no evidence.

## Evidence routes

The five library routes require construction plus a call on its result,
through an assigned receiver name or a direct chained expression in the
same module. Bare constructors require the matching import. Attribute
constructors require the matching library base. The exact forms are:

```text
1. spellchecker.SpellChecker -> correction / candidates / unknown / known
2. autocorrect.Speller -> instance(...) / autocorrect_word / autocorrect_sentence
3. symspellpy.SymSpell or symspellpy.symspellpy.SymSpell -> lookup / lookup_compound
4. hunspell.HunSpell or hunspell.Hunspell -> spell / suggest / bulk_suggest
5. textblob.TextBlob -> correct

All support from-imported constructors and aliases.
Generic attribute calls on any base, or from-imported/aliased bare calls:
correct_spelling, check_spelling, spell_check, spellcheck, fix_spelling,
correct_typos, fix_typos, detect_typos, find_typos, correct_misspellings,
check_typos, suggest_corrections, get_corrections, correct_word,
correct_text, spell_correct, fix_misspelling, detect_misspellings,
find_misspellings, suggest_spelling, correct_spellings, check_misspellings,
run_spell_check, apply_spell_check

load_dictionary, existing, get_candidates, word_frequency.load_text_file,
word_frequency.load_words, sentiment, words, translate, detect_language
alone do not supply the required call half.
```

## Differentiation

These neighboring tools check repairing grammar, rewording text, producing
new text, rendering text in another language, reading printed words, and
splitting text into tokens, respectively:

```text
grammar-correction-claim-audit
paraphrasing-claim-audit
text-generation-claim-audit
translation-claim-audit
ocr-claim-audit
tokenization-claim-audit
```

Those operations alone do not establish the checked capability: finding
words that are spelled wrong and suggesting the right spelling for them.
Stemming and lemmatization normalize word forms and also provide no evidence.

## Limitations

This is static pattern matching, not semantic judgement. Exact phrases
are recognized, not restatement. Syntax errors provide no evidence. There
is no runtime validation or cross-module data flow. The following phrase
can describe fixing errors by hand and still matches:

```text
our editors correct typos by hand before release
```

The shared method below counts only on a receiver bound to the specified
construction (or on the construction directly). Calling it on a grammar
library object provides no evidence, even when both objects exist:

```python
from textblob import TextBlob
from language_tool_python import LanguageTool
blob = TextBlob('word')
tool = LanguageTool('en')
tool.correct('sentence')  # does not count
blob.correct()            # counts
```

The generic route accepts a shared method name even on an unrelated object;
this intentional collision counts as evidence:

```python
unrelated.spellcheck('word')
```

## Development

```sh
python3 -m unittest discover
python3 -m build
```

The source archive includes the discoverable test package. The README-only
self-audit passes. Scanning the whole project produces a MEDIUM finding
from the fixed phrase-oracle literals in tests/.

Licensed under MIT.
