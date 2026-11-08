"""Checks for the localization failures observed in the actual source corpus."""
import tempfile
import unittest
from pathlib import Path
from loclib import ROOT,mask,restore,profile,parse_line,write_localization,load,validate,plain
from loclib import digest,numeric_profile
from maintain import check_binding


class LocalizationTests(unittest.TestCase):
    def test_numbers_and_localized_separators(self):
        self.assertEqual(numeric_profile('10,000 units at 0.5%'),numeric_profile('10 000 единиц при 0,5%'))
        self.assertNotEqual(numeric_profile('At least 15 technologies'),numeric_profile('Хотя бы 20 технологий'))
        self.assertNotEqual(numeric_profile('Spread +0.25'),numeric_profile('Спред −0,25'))
        self.assertEqual(numeric_profile('From 0 to 100'),numeric_profile('Диапазон 0–100'))
        self.assertEqual(numeric_profile('−5 to +10'),numeric_profile('−5…+10'))
        self.assertEqual(numeric_profile('Mid-1850s'),numeric_profile('Середина 1850-х'))
        self.assertEqual(numeric_profile('Base 50; support 15%'),numeric_profile('База — 50; поддержка — 15%'))
        self.assertNotEqual(numeric_profile('5 −10'),numeric_profile('5 +10'))
        self.assertNotEqual(numeric_profile('5 -10'),numeric_profile('5 +10'))
        self.assertEqual(numeric_profile('Missing: -1'),numeric_profile('Нет: −1'))
    def test_changed_english_requires_new_review(self):
        memory={'same':{'en_sha256':digest('old')},'removed':{'en_sha256':digest('gone')}}
        report=check_binding(memory,{'same':{'value':'changed'},'new':{'value':'added'}})
        self.assertEqual(report,{'added':['new'],'removed':['removed'],'changed':['same']})
    def test_nested_scope_and_reordered_tokens(self):
        en="[GetPlayer.MakeScope.Var('x').GetValue|2] $CAPTION$ @money!"
        ru="$CAPTION$: @money! [GetPlayer.MakeScope.Var('x').GetValue|2]"
        self.assertEqual(profile(en),profile(ru))
        self.assertIn('protected_tokens_changed',validate(en,ru.replace("'x'","'y'")))

    def test_compound_directive_and_closer(self):
        value="#tooltippable;tooltip:[Country.GetTooltipTag],LOC_KEY Text#!;\\n- More"
        template,protected=mask(value)
        self.assertEqual(protected,['#tooltippable;tooltip:[Country.GetTooltipTag],LOC_KEY','#!','\\n'])
        self.assertEqual(restore(template,protected),value)
        self.assertEqual(plain(value),'Text;- More')

    def test_concept_display_is_translatable_target_is_not(self):
        en="[Concept('concept_tax', 'Tax')]"
        ru="[Concept('concept_tax', 'Налог')]"
        self.assertEqual(profile(en),profile(ru))
        self.assertNotEqual(profile(en),profile(ru.replace('concept_tax','concept_law')))

    def test_marker_loss_rejected(self):
        template,protected=mask('Price $VALUE$ @money!')
        with self.assertRaises(ValueError):restore(template.replace('__PH1__',''),protected)

    def test_escaped_literal_brackets(self):
        self.assertEqual(profile(r'Author \[editor\]'),{})

    def test_quote_recovery_and_exact_emitted_bytes(self):
        self.assertEqual(parse_line(' key:0 "He said "hello"."',recover=True)[1],'He said "hello".')
        temporary=ROOT/'runtime/translations/test-tmp';temporary.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temporary) as folder:
            path=Path(folder)/'russian/test_l_russian.yml'
            write_localization(path,{'key':'Он сказал "привет".\\n[GetName]','trailing':'Слеш \\'})
            entries,audit=load(folder,'russian',True)
            self.assertEqual(audit['issues'],[])
            self.assertEqual(set(entries),{'key','trailing'})
            self.assertIn(r'\"привет\"',entries['key'].value)
            self.assertNotIn(b'\r\n',path.read_bytes())


if __name__=='__main__':unittest.main()
