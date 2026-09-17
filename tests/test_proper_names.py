import json
import unittest

from bridge.core import (BridgeError, MASK, classify, protect, restore,
                         translatable, validate_translation)
from bridge.proper_names import names
from bridge.provider import build_glossary, translate
from test_bridge import Fixture


class AssociationNameTests(unittest.TestCase):
    def test_pure_names_are_not_translation_candidates(self):
        for source in ('Hana','Zwei','Tres','Shi','Cinq','Liu','Seven','Eight',
                       "Devyat'",'Dieci','Öufi','<b>Hana</b>'):
            with self.subTest(source=source):
                self.assertFalse(translatable(source))
                self.assertIsNone(classify(source,None,False))
                self.assertIsNone(classify(source,source,True))
                validate_translation(source,source)

    def test_translate_surroundings_and_preserve_tokens(self):
        source='Zwei Assoc.\nSouth Section 6 <b>Director</b>'
        masked,tokens=protect(source)
        self.assertEqual(tokens,['Zwei','\n','<b>','</b>'])
        self.assertNotIn('Zwei',masked)
        result=restore(masked.replace(' Assoc.','协会').replace('South Section','南部').replace('Director','科长'),tokens)
        self.assertEqual(result,'Zwei协会\n南部 6 <b>科长</b>')
        validate_translation(source,result)

    def test_names_cannot_be_converted_or_misspelled(self):
        cases=[('Hana Association','一协'),('Öufi Association','Oufi协会'),
               ("Devyat' Assoc.",'Devyat协会'),('Zwei Association','zwei协会'),
               ('Hana Association','HanaHana协会')]
        for source,target in cases:
            with self.subTest(source=source,target=target):
                with self.assertRaises(BridgeError):
                    validate_translation(source,target)

    def test_seven_eight_only_protected_in_name_context(self):
        for source in ('Seven Association','Eight Assoc.','Seven协会','Eight協会'):
            self.assertEqual(len(names(source)),1,source)
            self.assertEqual(len(protect(source)[1]),1,source)
        for source in ('Seven enemies remain.','eight coins','There are seven associations.',
                       'eight','Sevenfold','Eighteen','Hanabi','cinquain'):
            self.assertEqual(names(source),[],source)
            self.assertTrue(translatable(source))
        validate_translation('Seven enemies remain.','还剩七名敌人。')

    def test_repeated_names_and_accent_apostrophe_are_exact(self):
        source="Öufi and Devyat' Association. Hana and Hana."
        masked,tokens=protect(source)
        result=restore(masked.replace(' and ','和').replace(' Association.','协会。').replace('.','。'),tokens)
        self.assertEqual(result,"Öufi和Devyat'协会。 Hana和Hana。")
        validate_translation(source,result)
        with self.assertRaises(BridgeError):
            validate_translation(source,result.replace('Hana和Hana','Hana'))
        with self.assertRaises(BridgeError):
            restore(masked.replace(MASK.findall(masked)[0],''),tokens)

    def test_existing_human_chinese_is_preserved(self):
        self.assertIsNone(classify('Hana Association','一协',True))
        self.assertIsNone(classify('Zwei Assoc.','二协',True))


class AssociationIntegrationTests(Fixture):
    def test_scan_keeps_human_translations_and_ignores_bare_names(self):
        self.write_source('Personalities.json',{'dataList':[
            {'id':1,'name':'Hana'},{'id':2,'name':'Zwei Association'},
            {'id':3,'name':'Cinq Association'}]})
        self.write_zh('Personalities.json',{'dataList':[{'id':2,'name':'二协'}]})
        entries=[e.source for e in self.scan().entries if e.file=='Personalities.json']
        self.assertEqual(entries,['Cinq Association'])

    def test_auto_glossary_avoids_conflicts_without_changing_custom(self):
        self.write_source('AssociationName.json',{'dataList':[
            {'id':1,'content':'Hana Association'},{'id':2,'content':'Blade Lineage'}]})
        self.write_zh('AssociationName.json',{'dataList':[
            {'id':1,'content':'一协'},{'id':2,'content':'剑契'}]})
        scan=self.scan()
        self.assertEqual(build_glossary(scan),{'Blade Lineage':'剑契','Old skill':'人工旧技能'})
        custom={'Hana Association':'一协','Manager':'主管'}
        before=custom.copy()
        self.assertEqual(build_glossary(scan,custom)['Manager'],'主管')
        self.assertEqual(custom,before)

    def test_old_nonconforming_cache_is_not_reused_or_deleted(self):
        self.write_source('Personalities.json',{'dataList':[{'id':1,'name':'Hana Association'}]})
        entry=next(e for e in self.scan().entries if e.file=='Personalities.json')
        with self.cache.connect() as connection:
            connection.execute('INSERT INTO translations VALUES (?,?,?,?,?,?)',
                (entry.uid,entry.cache_hash,entry.source,'一协','old-test-model',0))
        fresh=next(e for e in self.scan().entries if e.file=='Personalities.json')
        self.assertEqual(fresh.status,'pending')
        with self.cache.connect() as connection:
            self.assertEqual(connection.execute('SELECT translated FROM translations').fetchall(),[('一协',)])

    def test_translation_pipeline_sends_masks_and_restores_names(self):
        self.write_source('Personalities.json',{'dataList':[{'id':1,'name':"Devyat' Assoc.\nNorth Section 3"}]})
        seen=[]
        class Client:
            model='mock-names'
            def chat(self,messages):
                data=json.loads(messages[-1]['content'])
                seen.append(data)
                self_source=data['entries'][0]['source']
                assert "Devyat'" not in self_source
                return json.dumps({'translations':[{'id':e['id'],'text':
                    e['source'].replace(' Assoc.','协会').replace('North Section ','北部')+'科'
                    } for e in data['entries']]},ensure_ascii=False)
        scan=self.scan()
        entries=[e for e in scan.entries if e.file=='Personalities.json']
        result=translate(entries,scan,self.cache,Client(),{'interval':0})
        self.assertEqual(result,{'success':1,'failed':0,'total':1})
        fresh=next(e for e in self.scan().entries if e.file=='Personalities.json')
        self.assertEqual(fresh.translation,"Devyat'协会\n北部3科")
        self.assertEqual(fresh.status,'cached')
        self.assertEqual(len(seen),1)
