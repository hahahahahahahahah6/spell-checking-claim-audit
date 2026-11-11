"""Fixed specification oracles and behavioral regressions."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from spell_checking_claim_audit.audit import ROUTES, audit, has_evidence, main, match_phrases
from spell_checking_claim_audit.phrases import SPELLCHECKING, NOSPELLCHECKING, GENERIC_NAMES

EXPECTED_POSITIVE = ('correcting misspelled words', 'corrects misspelled words', 'correct misspelled words', 'fixing spelling mistakes', 'correcting misspellings', 'fixes spelling mistakes', 'detecting misspellings', 'corrects misspellings', 'fix spelling mistakes', 'correct misspellings', 'detects misspellings', 'spelling corrections', 'spelling suggestions', 'fixing misspellings', 'detect misspellings', 'spelling correction', 'spelling-correction', 'fixes misspellings', 'checking spelling', 'corrects spelling', 'spell corrections', 'correct spelling', 'fix misspellings', 'correcting typos', 'spell correction', 'spell-correction', 'checks spelling', 'detecting typos', 'typo correction', 'typo-correction', 'spell checking', 'spell-checking', 'check spelling', 'corrects typos', 'spellchecking', 'spell checker', 'spell-checker', 'correct typos', 'detects typos', 'finding typos', 'spellchecker', 'fixing typos', 'detect typos', 'spell check', 'spell-check', 'fixes typos', 'finds typos', 'spellcheck', 'find typos', 'fix typos')
EXPECTED_NEGATIVE = ('does not support spell checking', 'does not perform spell checking', 'does not provide spell checking', "doesn't support spell checking", 'without spell checking support', 'do not support spell checking', 'never performs spell checking', "don't support spell checking", 'spell checking not supported', 'no spell checking capability', 'spell checking not available', 'does not support spell check', 'does not use spell checking', 'spell checking unsupported', 'no spell checking support', 'no spell checking feature', 'spell checking disabled', 'without spell checking', 'missing spell checking', 'lacks spell checking', 'without spell check', 'no spell checking', 'no spell checker', 'no spell check')
EXPECTED_GENERIC = ('correct_spelling', 'check_spelling', 'spell_check', 'spellcheck', 'fix_spelling', 'correct_typos', 'fix_typos', 'detect_typos', 'find_typos', 'correct_misspellings', 'check_typos', 'suggest_corrections', 'get_corrections', 'correct_word', 'correct_text', 'spell_correct', 'fix_misspelling', 'detect_misspellings', 'find_misspellings', 'suggest_spelling', 'correct_spellings', 'check_misspellings', 'run_spell_check', 'apply_spell_check')

class AuditTests(unittest.TestCase):
    def test_phrase_oracle(self):
        self.assertEqual(SPELLCHECKING, EXPECTED_POSITIVE)
        self.assertEqual(NOSPELLCHECKING, EXPECTED_NEGATIVE)
        self.assertEqual(len(SPELLCHECKING), 50)
        self.assertEqual(len(NOSPELLCHECKING), 24)

    def test_generic_oracle(self):
        self.assertEqual(GENERIC_NAMES, EXPECTED_GENERIC)
        self.assertEqual(len(GENERIC_NAMES), 24)

    def test_route_oracle(self):
        self.assertEqual(ROUTES, ({'names': ['SpellChecker'], 'sources': ['spellchecker'], 'methods': ['correction', 'candidates', 'unknown', 'known'], 'direct': False}, {'names': ['Speller'], 'sources': ['autocorrect'], 'methods': ['autocorrect_word', 'autocorrect_sentence'], 'direct': True}, {'names': ['SymSpell'], 'sources': ['symspellpy', 'symspellpy.symspellpy'], 'methods': ['lookup', 'lookup_compound'], 'direct': False}, {'names': ['HunSpell', 'Hunspell'], 'sources': ['hunspell'], 'methods': ['spell', 'suggest', 'bulk_suggest'], 'direct': False}, {'names': ['TextBlob'], 'sources': ['textblob'], 'methods': ['correct'], 'direct': False}))
        from spell_checking_claim_audit.audit import GENERIC_CALL_FORMS, PAIR_REQUIREMENT
        self.assertEqual(GENERIC_CALL_FORMS, ("attribute-any-base", "from-imported-or-aliased-bare"))
        self.assertEqual(PAIR_REQUIREMENT, "assigned receiver or direct chained construction, same module")

    def fixture(self, docs='', source='', test=None):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        (root / 'README.md').write_text(docs)
        if source:
            (root / 'app.py').write_text(source)
        if test is not None:
            (root / 'tests').mkdir()
            (root / 'tests/fixture.py').write_text(test)
        return root

    def cli(self, args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(args)
        return code, output.getvalue()

    def test_span_removal(self):
        self.assertEqual(match_phrases('does not support spell checking'), (['does not support spell checking'], []))

    def test_longest_checker(self):
        self.assertEqual(match_phrases('spell checker'), ([], ['spell checker']))

    def test_longest_corrections(self):
        self.assertEqual(match_phrases('spelling corrections'), ([], ['spelling corrections']))

    def test_repeated_spans(self):
        self.assertEqual(match_phrases('spell checker; spell checker')[1], ['spell checker'] * 2)

    def test_case(self):
        root = self.fixture('SPELL CHECKING')
        self.assertEqual(audit(root)[0][0]['severity'], 'HIGH')

    def test_manual_collision(self):
        self.assertEqual(match_phrases('our editors correct typos by hand before release')[1], ['correct typos'])

    def test_face_collision(self):
        self.assertEqual(match_phrases('we check spelling on faces')[1], ['check spelling'])

    def test_fenced(self):
        root = self.fixture('```text\nspell checking\n```')
        self.assertEqual(audit(root)[0], [])

    def test_inline(self):
        root = self.fixture('`spell checking`')
        self.assertEqual(audit(root)[0][0]['severity'], 'HIGH')

    def test_no_normalization(self):
        self.assertEqual(match_phrases('spell--checking'), ([], []))

    def test_good_cli(self):
        root = self.fixture('spell checking', 'x.check_spelling(image)')
        code, output = self.cli(['audit', str(root)])
        self.assertEqual(code, 0)
        self.assertIn('PASS', output)

    def test_bad_cli(self):
        root = self.fixture('spell checking; check spelling')
        code, output = self.cli(['audit', str(root), '--json'])
        self.assertEqual(code, 2)
        findings = json.loads(output)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]['rule'], 'documented-spell-checking-claim-false')
        self.assertEqual(findings[0]['severity'], 'HIGH')
        self.assertEqual(findings[0]['verdict'], 'FAIL')
        self.assertTrue(findings[0]['message'])

    def test_denial_cli(self):
        root = self.fixture('does not support spell checking', 'x.check_spelling(image)')
        code, output = self.cli(['audit', str(root), '--json'])
        self.assertEqual(code, 2)
        findings = json.loads(output)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]['rule'], 'documented-no-spell-checking-claim-false')
        self.assertEqual(findings[0]['severity'], 'HIGH')

    def test_denial_no_source(self):
        self.assertEqual(audit(self.fixture('no spell checking'))[0], [])

    def test_no_claim_cli(self):
        code, output = self.cli(['audit', str(self.fixture('Hello'))])
        self.assertEqual(code, 0)
        self.assertIn('PASS', output)

    def test_test_only_cli(self):
        root = self.fixture(test='"spell checking"')
        code, output = self.cli(['audit', str(root), '--json'])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output)[0]['severity'], 'MEDIUM')
        self.assertEqual(self.cli(['audit', str(root), '--fail-on', 'medium'])[0], 2)

    def test_ignore(self):
        root = self.fixture('spell checking')
        self.assertEqual(self.cli(['audit', str(root), '--ignore', 'READ'])[0], 0)

    def test_ignore_before_positional(self):
        root = self.fixture('spell checking')
        self.assertEqual(self.cli(['audit', '--ignore', 'READ', str(root)])[0], 0)

    def test_ignore_repeatable(self):
        root = self.fixture('spell checking', test='"spell checking"')
        self.assertEqual(self.cli(['audit', '--ignore', 'README', '--ignore', 'tests/', str(root)])[0], 0)

    def test_version(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), self.assertRaises(SystemExit) as cm:
            main(['--version'])
        self.assertEqual(cm.exception.code, 0)
        self.assertEqual(output.getvalue().strip(), '0.1.0')

    def test_readme_self_audit(self):
        readme = Path(__file__).resolve().parents[1] / 'README.md'
        root = self.fixture(readme.read_text())
        self.assertEqual(audit(root)[0], [])
        from spell_checking_claim_audit.audit import prose
        self.assertEqual(match_phrases(prose(readme.read_text())), ([], []))

    def test_split_modules(self):
        root = self.fixture('spell checking', 'from spellchecker import SpellChecker\np = SpellChecker()')
        (root / 'other.py').write_text('p.correction(image)')
        self.assertEqual(audit(root)[0][0]['severity'], 'HIGH')

    def test_docs_scope(self):
        root = self.fixture()
        (root / 'docs/nested').mkdir(parents=True)
        (root / 'docs/nested/guide.md').write_text('spell checking')
        self.assertEqual(audit(root)[0][0]['severity'], 'HIGH')

    def test_outside_docs(self):
        root = self.fixture()
        (root / 'other.md').write_text('spell checking')
        self.assertEqual(audit(root)[0], [])

    def test_excluded_sources(self):
        root = self.fixture('spell checking')
        for directory in ['.git', '__pycache__', '.venv', 'custom_env']:
            (root / directory).mkdir()
            (root / directory / 'code.py').write_text('x.check_spelling()')
        (root / 'custom_env/pyvenv.cfg').write_text('home = /tmp')
        self.assertEqual(audit(root)[0][0]['severity'], 'HIGH')

    def test_verbose(self):
        root = self.fixture('Hello')
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(self.cli(['audit', str(root), '--verbose'])[0], 0)
        self.assertIn('Scope:', err.getvalue())
        self.assertIn('scan README.md', err.getvalue())

    def test_usage_and_io(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as cm:
            main(['audit', '--fail-on', 'low'])
        self.assertEqual(cm.exception.code, 1)
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(['audit', '/nonexistent-audit-directory']), 1)


    def test_SpellChecker_correction_bare(self):
        self.assertTrue(has_evidence("from spellchecker import SpellChecker\np=SpellChecker()\np.correction('w')"))

    def test_SpellChecker_correction_alias(self):
        self.assertTrue(has_evidence("from spellchecker import SpellChecker as C\np=C()\np.correction('w')"))

    def test_SpellChecker_correction_attribute(self):
        self.assertTrue(has_evidence("import spellchecker\np=spellchecker.SpellChecker()\np.correction('w')"))

    def test_SpellChecker_correction_module_alias(self):
        self.assertTrue(has_evidence("import spellchecker as m\np=m.SpellChecker()\np.correction('w')"))

    def test_SpellChecker_correction_chain(self):
        self.assertTrue(has_evidence("from spellchecker import SpellChecker\nSpellChecker().correction('w')"))

    def test_SpellChecker_candidates_bare(self):
        self.assertTrue(has_evidence("from spellchecker import SpellChecker\np=SpellChecker()\np.candidates('w')"))

    def test_SpellChecker_candidates_alias(self):
        self.assertTrue(has_evidence("from spellchecker import SpellChecker as C\np=C()\np.candidates('w')"))

    def test_SpellChecker_candidates_attribute(self):
        self.assertTrue(has_evidence("import spellchecker\np=spellchecker.SpellChecker()\np.candidates('w')"))

    def test_SpellChecker_candidates_module_alias(self):
        self.assertTrue(has_evidence("import spellchecker as m\np=m.SpellChecker()\np.candidates('w')"))

    def test_SpellChecker_candidates_chain(self):
        self.assertTrue(has_evidence("from spellchecker import SpellChecker\nSpellChecker().candidates('w')"))

    def test_SpellChecker_unknown_bare(self):
        self.assertTrue(has_evidence("from spellchecker import SpellChecker\np=SpellChecker()\np.unknown('w')"))

    def test_SpellChecker_unknown_alias(self):
        self.assertTrue(has_evidence("from spellchecker import SpellChecker as C\np=C()\np.unknown('w')"))

    def test_SpellChecker_unknown_attribute(self):
        self.assertTrue(has_evidence("import spellchecker\np=spellchecker.SpellChecker()\np.unknown('w')"))

    def test_SpellChecker_unknown_module_alias(self):
        self.assertTrue(has_evidence("import spellchecker as m\np=m.SpellChecker()\np.unknown('w')"))

    def test_SpellChecker_unknown_chain(self):
        self.assertTrue(has_evidence("from spellchecker import SpellChecker\nSpellChecker().unknown('w')"))

    def test_SpellChecker_known_bare(self):
        self.assertTrue(has_evidence("from spellchecker import SpellChecker\np=SpellChecker()\np.known('w')"))

    def test_SpellChecker_known_alias(self):
        self.assertTrue(has_evidence("from spellchecker import SpellChecker as C\np=C()\np.known('w')"))

    def test_SpellChecker_known_attribute(self):
        self.assertTrue(has_evidence("import spellchecker\np=spellchecker.SpellChecker()\np.known('w')"))

    def test_SpellChecker_known_module_alias(self):
        self.assertTrue(has_evidence("import spellchecker as m\np=m.SpellChecker()\np.known('w')"))

    def test_SpellChecker_known_chain(self):
        self.assertTrue(has_evidence("from spellchecker import SpellChecker\nSpellChecker().known('w')"))

    def test_SpellChecker_no_import(self):
        self.assertFalse(has_evidence("p=SpellChecker()\np.known('w')"))

    def test_SpellChecker_wrong_import(self):
        self.assertFalse(has_evidence("from other import SpellChecker\np=SpellChecker()\np.known('w')"))

    def test_SpellChecker_wrong_base(self):
        self.assertFalse(has_evidence("import other\np=other.SpellChecker()\np.known('w')"))

    def test_SpellChecker_construct_only(self):
        self.assertFalse(has_evidence('from spellchecker import SpellChecker\np=SpellChecker()'))

    def test_SpellChecker_call_only(self):
        self.assertFalse(has_evidence("import spellchecker\np.known('w')"))

    def test_SpellChecker_wrong_receiver(self):
        self.assertFalse(has_evidence("from spellchecker import SpellChecker\np=SpellChecker()\nq.known('w')"))

    def test_SpellChecker_rebound(self):
        self.assertFalse(has_evidence("from spellchecker import SpellChecker\np=SpellChecker()\np=other()\np.known('w')"))

    def test_SpellChecker_shadow_def(self):
        self.assertFalse(has_evidence("from spellchecker import SpellChecker\np=SpellChecker()\np.known('w')\ndef SpellChecker(): pass"))

    def test_SpellChecker_shadow_class(self):
        self.assertFalse(has_evidence("from spellchecker import SpellChecker\np=SpellChecker()\np.known('w')\nclass SpellChecker: pass"))

    def test_Speller___call___bare(self):
        self.assertTrue(has_evidence("from autocorrect import Speller\np=Speller()\np('w')"))

    def test_Speller___call___alias(self):
        self.assertTrue(has_evidence("from autocorrect import Speller as C\np=C()\np('w')"))

    def test_Speller___call___attribute(self):
        self.assertTrue(has_evidence("import autocorrect\np=autocorrect.Speller()\np('w')"))

    def test_Speller___call___module_alias(self):
        self.assertTrue(has_evidence("import autocorrect as m\np=m.Speller()\np('w')"))

    def test_Speller___call___chain(self):
        self.assertTrue(has_evidence("from autocorrect import Speller\nSpeller()('w')"))

    def test_Speller_autocorrect_word_bare(self):
        self.assertTrue(has_evidence("from autocorrect import Speller\np=Speller()\np.autocorrect_word('w')"))

    def test_Speller_autocorrect_word_alias(self):
        self.assertTrue(has_evidence("from autocorrect import Speller as C\np=C()\np.autocorrect_word('w')"))

    def test_Speller_autocorrect_word_attribute(self):
        self.assertTrue(has_evidence("import autocorrect\np=autocorrect.Speller()\np.autocorrect_word('w')"))

    def test_Speller_autocorrect_word_module_alias(self):
        self.assertTrue(has_evidence("import autocorrect as m\np=m.Speller()\np.autocorrect_word('w')"))

    def test_Speller_autocorrect_word_chain(self):
        self.assertTrue(has_evidence("from autocorrect import Speller\nSpeller().autocorrect_word('w')"))

    def test_Speller_autocorrect_sentence_bare(self):
        self.assertTrue(has_evidence("from autocorrect import Speller\np=Speller()\np.autocorrect_sentence('w')"))

    def test_Speller_autocorrect_sentence_alias(self):
        self.assertTrue(has_evidence("from autocorrect import Speller as C\np=C()\np.autocorrect_sentence('w')"))

    def test_Speller_autocorrect_sentence_attribute(self):
        self.assertTrue(has_evidence("import autocorrect\np=autocorrect.Speller()\np.autocorrect_sentence('w')"))

    def test_Speller_autocorrect_sentence_module_alias(self):
        self.assertTrue(has_evidence("import autocorrect as m\np=m.Speller()\np.autocorrect_sentence('w')"))

    def test_Speller_autocorrect_sentence_chain(self):
        self.assertTrue(has_evidence("from autocorrect import Speller\nSpeller().autocorrect_sentence('w')"))

    def test_Speller_no_import(self):
        self.assertFalse(has_evidence("p=Speller()\np.autocorrect_sentence('w')"))

    def test_Speller_wrong_import(self):
        self.assertFalse(has_evidence("from other import Speller\np=Speller()\np.autocorrect_sentence('w')"))

    def test_Speller_wrong_base(self):
        self.assertFalse(has_evidence("import other\np=other.Speller()\np.autocorrect_sentence('w')"))

    def test_Speller_construct_only(self):
        self.assertFalse(has_evidence('from autocorrect import Speller\np=Speller()'))

    def test_Speller_call_only(self):
        self.assertFalse(has_evidence("import autocorrect\np.autocorrect_sentence('w')"))

    def test_Speller_wrong_receiver(self):
        self.assertFalse(has_evidence("from autocorrect import Speller\np=Speller()\nq.autocorrect_sentence('w')"))

    def test_Speller_rebound(self):
        self.assertFalse(has_evidence("from autocorrect import Speller\np=Speller()\np=other()\np.autocorrect_sentence('w')"))

    def test_Speller_shadow_def(self):
        self.assertFalse(has_evidence("from autocorrect import Speller\np=Speller()\np.autocorrect_sentence('w')\ndef Speller(): pass"))

    def test_Speller_shadow_class(self):
        self.assertFalse(has_evidence("from autocorrect import Speller\np=Speller()\np.autocorrect_sentence('w')\nclass Speller: pass"))

    def test_SymSpell_lookup_bare(self):
        self.assertTrue(has_evidence("from symspellpy import SymSpell\np=SymSpell()\np.lookup('w')"))

    def test_SymSpell_lookup_alias(self):
        self.assertTrue(has_evidence("from symspellpy import SymSpell as C\np=C()\np.lookup('w')"))

    def test_SymSpell_lookup_attribute(self):
        self.assertTrue(has_evidence("import symspellpy\np=symspellpy.SymSpell()\np.lookup('w')"))

    def test_SymSpell_lookup_module_alias(self):
        self.assertTrue(has_evidence("import symspellpy as m\np=m.SymSpell()\np.lookup('w')"))

    def test_SymSpell_lookup_chain(self):
        self.assertTrue(has_evidence("from symspellpy import SymSpell\nSymSpell().lookup('w')"))

    def test_SymSpell_lookup_compound_bare(self):
        self.assertTrue(has_evidence("from symspellpy import SymSpell\np=SymSpell()\np.lookup_compound('w')"))

    def test_SymSpell_lookup_compound_alias(self):
        self.assertTrue(has_evidence("from symspellpy import SymSpell as C\np=C()\np.lookup_compound('w')"))

    def test_SymSpell_lookup_compound_attribute(self):
        self.assertTrue(has_evidence("import symspellpy\np=symspellpy.SymSpell()\np.lookup_compound('w')"))

    def test_SymSpell_lookup_compound_module_alias(self):
        self.assertTrue(has_evidence("import symspellpy as m\np=m.SymSpell()\np.lookup_compound('w')"))

    def test_SymSpell_lookup_compound_chain(self):
        self.assertTrue(has_evidence("from symspellpy import SymSpell\nSymSpell().lookup_compound('w')"))

    def test_SymSpell_no_import(self):
        self.assertFalse(has_evidence("p=SymSpell()\np.lookup_compound('w')"))

    def test_SymSpell_wrong_import(self):
        self.assertFalse(has_evidence("from other import SymSpell\np=SymSpell()\np.lookup_compound('w')"))

    def test_SymSpell_wrong_base(self):
        self.assertFalse(has_evidence("import other\np=other.SymSpell()\np.lookup_compound('w')"))

    def test_SymSpell_construct_only(self):
        self.assertFalse(has_evidence('from symspellpy import SymSpell\np=SymSpell()'))

    def test_SymSpell_call_only(self):
        self.assertFalse(has_evidence("import symspellpy\np.lookup_compound('w')"))

    def test_SymSpell_wrong_receiver(self):
        self.assertFalse(has_evidence("from symspellpy import SymSpell\np=SymSpell()\nq.lookup_compound('w')"))

    def test_SymSpell_rebound(self):
        self.assertFalse(has_evidence("from symspellpy import SymSpell\np=SymSpell()\np=other()\np.lookup_compound('w')"))

    def test_SymSpell_shadow_def(self):
        self.assertFalse(has_evidence("from symspellpy import SymSpell\np=SymSpell()\np.lookup_compound('w')\ndef SymSpell(): pass"))

    def test_SymSpell_shadow_class(self):
        self.assertFalse(has_evidence("from symspellpy import SymSpell\np=SymSpell()\np.lookup_compound('w')\nclass SymSpell: pass"))

    def test_HunSpell_spell_bare(self):
        self.assertTrue(has_evidence("from hunspell import HunSpell\np=HunSpell()\np.spell('w')"))

    def test_HunSpell_spell_alias(self):
        self.assertTrue(has_evidence("from hunspell import HunSpell as C\np=C()\np.spell('w')"))

    def test_HunSpell_spell_attribute(self):
        self.assertTrue(has_evidence("import hunspell\np=hunspell.HunSpell()\np.spell('w')"))

    def test_HunSpell_spell_module_alias(self):
        self.assertTrue(has_evidence("import hunspell as m\np=m.HunSpell()\np.spell('w')"))

    def test_HunSpell_spell_chain(self):
        self.assertTrue(has_evidence("from hunspell import HunSpell\nHunSpell().spell('w')"))

    def test_HunSpell_suggest_bare(self):
        self.assertTrue(has_evidence("from hunspell import HunSpell\np=HunSpell()\np.suggest('w')"))

    def test_HunSpell_suggest_alias(self):
        self.assertTrue(has_evidence("from hunspell import HunSpell as C\np=C()\np.suggest('w')"))

    def test_HunSpell_suggest_attribute(self):
        self.assertTrue(has_evidence("import hunspell\np=hunspell.HunSpell()\np.suggest('w')"))

    def test_HunSpell_suggest_module_alias(self):
        self.assertTrue(has_evidence("import hunspell as m\np=m.HunSpell()\np.suggest('w')"))

    def test_HunSpell_suggest_chain(self):
        self.assertTrue(has_evidence("from hunspell import HunSpell\nHunSpell().suggest('w')"))

    def test_HunSpell_bulk_suggest_bare(self):
        self.assertTrue(has_evidence("from hunspell import HunSpell\np=HunSpell()\np.bulk_suggest('w')"))

    def test_HunSpell_bulk_suggest_alias(self):
        self.assertTrue(has_evidence("from hunspell import HunSpell as C\np=C()\np.bulk_suggest('w')"))

    def test_HunSpell_bulk_suggest_attribute(self):
        self.assertTrue(has_evidence("import hunspell\np=hunspell.HunSpell()\np.bulk_suggest('w')"))

    def test_HunSpell_bulk_suggest_module_alias(self):
        self.assertTrue(has_evidence("import hunspell as m\np=m.HunSpell()\np.bulk_suggest('w')"))

    def test_HunSpell_bulk_suggest_chain(self):
        self.assertTrue(has_evidence("from hunspell import HunSpell\nHunSpell().bulk_suggest('w')"))

    def test_HunSpell_no_import(self):
        self.assertFalse(has_evidence("p=HunSpell()\np.bulk_suggest('w')"))

    def test_HunSpell_wrong_import(self):
        self.assertFalse(has_evidence("from other import HunSpell\np=HunSpell()\np.bulk_suggest('w')"))

    def test_HunSpell_wrong_base(self):
        self.assertFalse(has_evidence("import other\np=other.HunSpell()\np.bulk_suggest('w')"))

    def test_HunSpell_construct_only(self):
        self.assertFalse(has_evidence('from hunspell import HunSpell\np=HunSpell()'))

    def test_HunSpell_call_only(self):
        self.assertFalse(has_evidence("import hunspell\np.bulk_suggest('w')"))

    def test_HunSpell_wrong_receiver(self):
        self.assertFalse(has_evidence("from hunspell import HunSpell\np=HunSpell()\nq.bulk_suggest('w')"))

    def test_HunSpell_rebound(self):
        self.assertFalse(has_evidence("from hunspell import HunSpell\np=HunSpell()\np=other()\np.bulk_suggest('w')"))

    def test_HunSpell_shadow_def(self):
        self.assertFalse(has_evidence("from hunspell import HunSpell\np=HunSpell()\np.bulk_suggest('w')\ndef HunSpell(): pass"))

    def test_HunSpell_shadow_class(self):
        self.assertFalse(has_evidence("from hunspell import HunSpell\np=HunSpell()\np.bulk_suggest('w')\nclass HunSpell: pass"))

    def test_Hunspell_spell_bare(self):
        self.assertTrue(has_evidence("from hunspell import Hunspell\np=Hunspell()\np.spell('w')"))

    def test_Hunspell_spell_alias(self):
        self.assertTrue(has_evidence("from hunspell import Hunspell as C\np=C()\np.spell('w')"))

    def test_Hunspell_spell_attribute(self):
        self.assertTrue(has_evidence("import hunspell\np=hunspell.Hunspell()\np.spell('w')"))

    def test_Hunspell_spell_module_alias(self):
        self.assertTrue(has_evidence("import hunspell as m\np=m.Hunspell()\np.spell('w')"))

    def test_Hunspell_spell_chain(self):
        self.assertTrue(has_evidence("from hunspell import Hunspell\nHunspell().spell('w')"))

    def test_Hunspell_suggest_bare(self):
        self.assertTrue(has_evidence("from hunspell import Hunspell\np=Hunspell()\np.suggest('w')"))

    def test_Hunspell_suggest_alias(self):
        self.assertTrue(has_evidence("from hunspell import Hunspell as C\np=C()\np.suggest('w')"))

    def test_Hunspell_suggest_attribute(self):
        self.assertTrue(has_evidence("import hunspell\np=hunspell.Hunspell()\np.suggest('w')"))

    def test_Hunspell_suggest_module_alias(self):
        self.assertTrue(has_evidence("import hunspell as m\np=m.Hunspell()\np.suggest('w')"))

    def test_Hunspell_suggest_chain(self):
        self.assertTrue(has_evidence("from hunspell import Hunspell\nHunspell().suggest('w')"))

    def test_Hunspell_bulk_suggest_bare(self):
        self.assertTrue(has_evidence("from hunspell import Hunspell\np=Hunspell()\np.bulk_suggest('w')"))

    def test_Hunspell_bulk_suggest_alias(self):
        self.assertTrue(has_evidence("from hunspell import Hunspell as C\np=C()\np.bulk_suggest('w')"))

    def test_Hunspell_bulk_suggest_attribute(self):
        self.assertTrue(has_evidence("import hunspell\np=hunspell.Hunspell()\np.bulk_suggest('w')"))

    def test_Hunspell_bulk_suggest_module_alias(self):
        self.assertTrue(has_evidence("import hunspell as m\np=m.Hunspell()\np.bulk_suggest('w')"))

    def test_Hunspell_bulk_suggest_chain(self):
        self.assertTrue(has_evidence("from hunspell import Hunspell\nHunspell().bulk_suggest('w')"))

    def test_Hunspell_no_import(self):
        self.assertFalse(has_evidence("p=Hunspell()\np.bulk_suggest('w')"))

    def test_Hunspell_wrong_import(self):
        self.assertFalse(has_evidence("from other import Hunspell\np=Hunspell()\np.bulk_suggest('w')"))

    def test_Hunspell_wrong_base(self):
        self.assertFalse(has_evidence("import other\np=other.Hunspell()\np.bulk_suggest('w')"))

    def test_Hunspell_construct_only(self):
        self.assertFalse(has_evidence('from hunspell import Hunspell\np=Hunspell()'))

    def test_Hunspell_call_only(self):
        self.assertFalse(has_evidence("import hunspell\np.bulk_suggest('w')"))

    def test_Hunspell_wrong_receiver(self):
        self.assertFalse(has_evidence("from hunspell import Hunspell\np=Hunspell()\nq.bulk_suggest('w')"))

    def test_Hunspell_rebound(self):
        self.assertFalse(has_evidence("from hunspell import Hunspell\np=Hunspell()\np=other()\np.bulk_suggest('w')"))

    def test_Hunspell_shadow_def(self):
        self.assertFalse(has_evidence("from hunspell import Hunspell\np=Hunspell()\np.bulk_suggest('w')\ndef Hunspell(): pass"))

    def test_Hunspell_shadow_class(self):
        self.assertFalse(has_evidence("from hunspell import Hunspell\np=Hunspell()\np.bulk_suggest('w')\nclass Hunspell: pass"))

    def test_TextBlob_correct_bare(self):
        self.assertTrue(has_evidence("from textblob import TextBlob\np=TextBlob()\np.correct('w')"))

    def test_TextBlob_correct_alias(self):
        self.assertTrue(has_evidence("from textblob import TextBlob as C\np=C()\np.correct('w')"))

    def test_TextBlob_correct_attribute(self):
        self.assertTrue(has_evidence("import textblob\np=textblob.TextBlob()\np.correct('w')"))

    def test_TextBlob_correct_module_alias(self):
        self.assertTrue(has_evidence("import textblob as m\np=m.TextBlob()\np.correct('w')"))

    def test_TextBlob_correct_chain(self):
        self.assertTrue(has_evidence("from textblob import TextBlob\nTextBlob().correct('w')"))

    def test_TextBlob_no_import(self):
        self.assertFalse(has_evidence("p=TextBlob()\np.correct('w')"))

    def test_TextBlob_wrong_import(self):
        self.assertFalse(has_evidence("from other import TextBlob\np=TextBlob()\np.correct('w')"))

    def test_TextBlob_wrong_base(self):
        self.assertFalse(has_evidence("import other\np=other.TextBlob()\np.correct('w')"))

    def test_TextBlob_construct_only(self):
        self.assertFalse(has_evidence('from textblob import TextBlob\np=TextBlob()'))

    def test_TextBlob_call_only(self):
        self.assertFalse(has_evidence("import textblob\np.correct('w')"))

    def test_TextBlob_wrong_receiver(self):
        self.assertFalse(has_evidence("from textblob import TextBlob\np=TextBlob()\nq.correct('w')"))

    def test_TextBlob_rebound(self):
        self.assertFalse(has_evidence("from textblob import TextBlob\np=TextBlob()\np=other()\np.correct('w')"))

    def test_TextBlob_shadow_def(self):
        self.assertFalse(has_evidence("from textblob import TextBlob\np=TextBlob()\np.correct('w')\ndef TextBlob(): pass"))

    def test_TextBlob_shadow_class(self):
        self.assertFalse(has_evidence("from textblob import TextBlob\np=TextBlob()\np.correct('w')\nclass TextBlob: pass"))

    def test_symspell_submodule_0(self):
        self.assertTrue(has_evidence('from symspellpy.symspellpy import SymSpell\np=SymSpell()\np.lookup_compound("w")'))

    def test_symspell_submodule_1(self):
        self.assertTrue(has_evidence('import symspellpy\np=symspellpy.symspellpy.SymSpell()\np.lookup("w")'))

    def test_symspell_submodule_2(self):
        self.assertTrue(has_evidence('from symspellpy import symspellpy\np=symspellpy.SymSpell()\np.lookup("w")'))

    def test_not_evidence_0(self):
        self.assertFalse(has_evidence('import spellchecker, autocorrect, symspellpy, hunspell, textblob'))

    def test_not_evidence_1(self):
        self.assertFalse(has_evidence('from spellchecker import SpellChecker\np=SpellChecker()\np.word_frequency.load_text_file("x")'))

    def test_not_evidence_2(self):
        self.assertFalse(has_evidence('from spellchecker import SpellChecker\np=SpellChecker()\np.word_frequency.load_words([])'))

    def test_not_evidence_3(self):
        self.assertFalse(has_evidence('from symspellpy import SymSpell\np=SymSpell()\np.load_dictionary("x")'))

    def test_not_evidence_4(self):
        self.assertFalse(has_evidence('from autocorrect import Speller\np=Speller()\np.existing([])'))

    def test_not_evidence_5(self):
        self.assertFalse(has_evidence('from autocorrect import Speller\np=Speller()\np.get_candidates("x")'))

    def test_not_evidence_6(self):
        self.assertFalse(has_evidence('"""spell check typo"""\n# x.spellcheck()\ns="spell checking"'))

    def test_not_evidence_7(self):
        self.assertFalse(has_evidence('from custom import correct_spelling\ncorrect_spelling'))

    def test_not_evidence_8(self):
        self.assertFalse(has_evidence('correct_spelling("w")'))

    def test_not_evidence_9(self):
        self.assertFalse(has_evidence('import subprocess\nsubprocess.run(["hunspell", "word"])'))

    def test_not_evidence_10(self):
        self.assertFalse(has_evidence('paraphraser.paraphrase(text)'))

    def test_not_evidence_11(self):
        self.assertFalse(has_evidence('generator.generate(text)'))

    def test_not_evidence_12(self):
        self.assertFalse(has_evidence('translator.translate(text)'))

    def test_not_evidence_13(self):
        self.assertFalse(has_evidence('ocr.image_to_string(image)'))

    def test_not_evidence_14(self):
        self.assertFalse(has_evidence('tokenizer.tokenize(text)'))

    def test_not_evidence_15(self):
        self.assertFalse(has_evidence('stemmer.stem(text)'))

    def test_not_evidence_16(self):
        self.assertFalse(has_evidence('lemmatizer.lemmatize(text)'))

    def test_not_evidence_17(self):
        self.assertFalse(has_evidence('not valid source!'))

    def test_not_evidence_18(self):
        self.assertFalse(has_evidence('from grammar import LanguageTool\np=LanguageTool()\np.correct("w")'))

    def test_not_evidence_19(self):
        self.assertFalse(has_evidence('from grammar import Gramformer\np=Gramformer()\np.correct("w")'))

    def test_not_evidence_20(self):
        self.assertFalse(has_evidence('from grammar import HappyTextToText\np=HappyTextToText()\np.generate_text("w")'))

    def test_not_evidence_21(self):
        self.assertFalse(has_evidence('from grammar import GingerIt\np=GingerIt()\np.parse("w")'))

    def test_not_evidence_22(self):
        self.assertFalse(has_evidence('from textblob import TextBlob\np=TextBlob("w")\np.sentiment'))

    def test_not_evidence_23(self):
        self.assertFalse(has_evidence('from textblob import TextBlob\np=TextBlob("w")\np.words'))

    def test_not_evidence_24(self):
        self.assertFalse(has_evidence('from textblob import TextBlob\np=TextBlob("w")\np.translate'))

    def test_not_evidence_25(self):
        self.assertFalse(has_evidence('from textblob import TextBlob\np=TextBlob("w")\np.detect_language'))

    def test_generic_shadow_def(self):
        self.assertFalse(has_evidence('from custom import correct_spelling\ncorrect_spelling("w")\ndef correct_spelling(): pass'))

    def test_generic_shadow_class(self):
        self.assertFalse(has_evidence('from custom import correct_spelling\ncorrect_spelling("w")\nclass correct_spelling: pass'))

    def test_receiver_discrimination_negative(self):
        self.assertFalse(has_evidence('from textblob import TextBlob\nfrom language_tool_python import LanguageTool\nb=TextBlob("w")\ng=LanguageTool("en")\ng.correct("w")'))

    def test_receiver_discrimination_positive(self):
        self.assertTrue(has_evidence('from textblob import TextBlob\nfrom language_tool_python import LanguageTool\nb=TextBlob("w")\ng=LanguageTool("en")\nb.correct()'))

    def test_all_generic_names_and_forms(self):
        for name in EXPECTED_GENERIC:
            with self.subTest(name=name):
                self.assertTrue(has_evidence('x.' + name + '("w")'))
                self.assertTrue(has_evidence('from custom import ' + name + '\n' + name + '("w")'))
                self.assertTrue(has_evidence('from custom import ' + name + ' as f\nf("w")'))
                self.assertFalse(has_evidence(name + '("w")'))

    def test_all_phrases(self):
        for phrase in EXPECTED_POSITIVE:
            self.assertEqual(match_phrases(phrase), ([], [phrase]))
        for phrase in EXPECTED_NEGATIVE:
            self.assertEqual(match_phrases(phrase), ([phrase], []))

    def test_generic_collision(self):
        self.assertTrue(has_evidence('unrelated.spellcheck("w")'))

    def test_whole_project_self_audit(self):
        findings = audit(Path(__file__).resolve().parents[1], ignore=('build/', 'dist/'))[0]
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]['severity'], 'MEDIUM')

    def test_phrase_tuple_order(self):
        self.assertIsInstance(SPELLCHECKING, tuple)
        self.assertIsInstance(NOSPELLCHECKING, tuple)
        for phrases in (SPELLCHECKING, NOSPELLCHECKING):
            self.assertEqual(list(map(len, phrases)), sorted(map(len, phrases), reverse=True))

if __name__ == '__main__':
    unittest.main()
