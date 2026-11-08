"""Prevent standalone TE text from acquiring BPM-only references."""
from copy import deepcopy
import unittest
from translation_bridge import render,entries,RELATIVE
from translations.loclib import digest


class TranslationBridgeTests(unittest.TestCase):
    def setUp(self):
        self.en={'tax':'Tax $BPM_ONLY$ +0.25','culture':'Active: 7300 days'}
        self.memory={key:{'en_sha256':digest(value),'ru':ru} for (key,value),ru in zip(
            self.en.items(),('Налог $BPM_ONLY$ +0,25','Активность: 7300 дней'))}

    def test_native_entries_emitted_once(self):
        text,report=render(self.en,{'culture':self.memory['culture']['ru']},self.memory)
        self.assertIn('$BPM_ONLY$',text)
        self.assertNotIn('culture:',text)
        self.assertEqual(report['translated_keys'],1)

    def test_source_drift_is_blocked(self):
        for source in ({**self.en,'new':'New'}, {**self.en,'tax':'Changed $BPM_ONLY$ +0.25'}):
            with self.assertRaises(ValueError):render(source,{},self.memory)

    def test_missing_token_and_sign_flip_are_blocked(self):
        for changed in ('Налог +0,25','Налог $BPM_ONLY$ −0,25'):
            memory=deepcopy(self.memory);memory['tax']['ru']=changed
            with self.assertRaises(ValueError):render(self.en,{},memory)

    def test_native_conflict_is_blocked(self):
        with self.assertRaises(ValueError):render(self.en,{'culture':'Другой текст'},self.memory)

    def test_old_generated_file_cannot_validate_itself(self):
        self.assertEqual(entries({RELATIVE:'l_russian:\n tax:0 "Старый перевод"'},'russian'),{})


if __name__=='__main__':unittest.main()
