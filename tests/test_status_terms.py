import copy
import json
import threading
from unittest.mock import patch
from test_bridge import Fixture
from test_validation_retries import SimulatedClient,reply
from bridge.core import Cache,BridgeError,PACK_RULES_VERSION,payload,install_pack,read_json,export_report
from bridge.provider import translate,build_glossary
from bridge.status_terms import align_status_terms,status_context,status_slot


class StatusTermsTests(Fixture):
    def make_status(self,file='Bufs.json',identity='RougeIshmaelEclose',name='Full Makeover',desc='Gain 3 [Binding].'):
        self.write_source(file,{'dataList':[{'id':identity,'name':name,'desc':desc}]})

    def prepare(self):
        self.make_status();self.make_status('BattleKeywords.json')
        return self.scan()

    def status_entries(self,scan):
        return [e for e in scan.entries if status_slot(e.file,e.tokens)]

    def save(self,scan,file,field,value,model='simulation'):
        e=next(e for e in self.status_entries(scan) if e.file==file and e.field==field)
        self.cache.put(e,value,model)
        return e

    def test_existing_two_names_and_identical_descriptions_align_without_cache_rewrite(self):
        scan=self.prepare()
        self.save(scan,'Bufs.json','name','焕然一新')
        self.save(scan,'BattleKeywords.json','name','全新造型')
        self.save(scan,'Bufs.json','desc','获得3层[Binding]。')
        self.save(scan,'BattleKeywords.json','desc','得到 3 [Binding]。')
        raw=self.cache.path.read_bytes()
        result=payload(scan)[0]
        a=json.loads(result['Bufs.json'])['dataList'][0]
        b=json.loads(result['BattleKeywords.json'])['dataList'][0]
        self.assertEqual(a,b);self.assertEqual(a['name'],'焕然一新')
        self.assertEqual(self.cache.path.read_bytes(),raw)
        again=self.scan()
        self.assertEqual({e.translation for e in self.status_entries(again) if e.field=='name'},{'焕然一新'})

    def test_human_translation_wins_without_changing_original_file(self):
        scan=self.prepare()
        self.save(scan,'Bufs.json','name','焕然一新')
        human={'dataList':[{'id':'RougeIshmaelEclose','name':'人工定名','desc':'人工说明'}]}
        self.write_zh('BattleKeywords.json',human)
        original=(self.zh/'BattleKeywords.json').read_bytes()
        scan=self.scan();result=payload(scan)[0]
        self.assertEqual(json.loads(result['Bufs.json'])['dataList'][0]['name'],'人工定名')
        self.assertEqual(result['BattleKeywords.json'],original)
        self.assertEqual((self.zh/'BattleKeywords.json').read_bytes(),original)

    def test_human_translation_is_reused_for_missing_alias_without_api(self):
        self.prepare()
        self.write_zh('Bufs.json',{'dataList':[{'id':'RougeIshmaelEclose','name':'人工定名'}]})
        scan=self.scan()
        e=next(e for e in self.status_entries(scan) if e.file=='BattleKeywords.json' and e.field=='name')
        self.assertEqual(e.status,'cached');self.assertEqual(e.translation,'人工定名')
        client=SimulatedClient(lambda data,n:self.fail('must not request known identical name'))
        self.assertEqual(translate([e],scan,self.cache,client,{'interval':0})['total'],0)
        self.assertEqual(client.calls,[])

    def test_different_ids_are_never_merged_even_when_source_names_match(self):
        self.make_status(identity='first');self.make_status('BattleKeywords.json',identity='second')
        scan=self.scan()
        self.save(scan,'Bufs.json','name','甲名称')
        self.save(scan,'BattleKeywords.json','name','乙名称')
        result=payload(scan)[0]
        self.assertEqual(json.loads(result['Bufs.json'])['dataList'][0]['name'],'甲名称')
        self.assertEqual(json.loads(result['BattleKeywords.json'])['dataList'][0]['name'],'乙名称')

    def test_same_id_with_changed_source_does_not_reuse_previous_wording(self):
        self.make_status();self.make_status('BattleKeywords.json',name='Other Makeover',desc='Gain 4 [Binding].')
        scan=self.scan()
        self.save(scan,'Bufs.json','name','焕然一新')
        self.save(scan,'Bufs.json','desc','获得3层[Binding]。')
        align_status_terms(scan)
        other=[e for e in self.status_entries(scan) if e.file=='BattleKeywords.json']
        self.assertTrue(all(e.status=='pending' for e in other))
        self.assertNotIn('RougeIshmaelEclose',scan.status_terms)

    def test_only_identical_fields_align(self):
        self.make_status();self.make_status('BattleKeywords.json',desc='Gain 4 [Binding].')
        scan=self.scan()
        self.save(scan,'Bufs.json','name','焕然一新')
        self.save(scan,'Bufs.json','desc','获得3层[Binding]。')
        self.save(scan,'BattleKeywords.json','name','全新造型')
        self.save(scan,'BattleKeywords.json','desc','获得4层[Binding]。')
        result=payload(scan)[0]
        a=json.loads(result['Bufs.json'])['dataList'][0]
        b=json.loads(result['BattleKeywords.json'])['dataList'][0]
        self.assertEqual(a['name'],b['name']);self.assertNotEqual(a['desc'],b['desc'])

    def test_latest_manual_review_overrides_ai_and_survives_rescan(self):
        scan=self.prepare()
        self.save(scan,'Bufs.json','name','焕然一新')
        self.save(scan,'BattleKeywords.json','name','手动统一名','manual')
        align_status_terms(scan)
        self.assertEqual({e.translation for e in self.status_entries(scan) if e.field=='name'},{'手动统一名'})
        again=self.scan()
        self.assertEqual({e.translation for e in self.status_entries(again) if e.field=='name'},{'手动统一名'})
        with patch('bridge.core.time.time',return_value=9999999999):
            self.save(again,'Bufs.json','name','再次审校名','manual')
        latest=self.scan()
        self.assertEqual({e.translation for e in self.status_entries(latest) if e.field=='name'},{'再次审校名'})

    def test_conflicting_human_names_preserved_and_reported(self):
        self.prepare();self.make_status('Bufs-new.json')
        self.write_zh('Bufs.json',{'dataList':[{'id':'RougeIshmaelEclose','name':'人工甲'}]})
        self.write_zh('BattleKeywords.json',{'dataList':[{'id':'RougeIshmaelEclose','name':'人工乙'}]})
        scan=self.scan();e=next(e for e in self.status_entries(scan) if e.file=='Bufs-new.json' and e.field=='name')
        self.cache.put(e,'已有补译','simulation')
        result=payload(scan)[0]
        self.assertEqual(json.loads(result['Bufs.json'])['dataList'][0]['name'],'人工甲')
        self.assertEqual(json.loads(result['BattleKeywords.json'])['dataList'][0]['name'],'人工乙')
        self.assertEqual(e.translation,'已有补译')
        self.assertTrue(any(r['reason']=='human_conflict' for r in scan.status_alignment_conflicts))

    def test_protected_names_not_copied_from_incompatible_human_translation(self):
        self.make_status(name='Hana Association');self.make_status('BattleKeywords.json',name='Hana Association')
        self.write_zh('Bufs.json',{'dataList':[{'id':'RougeIshmaelEclose','name':'一协会'}]})
        scan=self.scan()
        e=next(e for e in self.status_entries(scan) if e.file=='BattleKeywords.json' and e.field=='name')
        self.assertEqual(e.status,'pending')
        self.assertTrue(any(r['reason']=='protected_format' for r in scan.status_alignment_conflicts))

    def test_ignored_alias_remains_ignored(self):
        scan=self.prepare();self.save(scan,'Bufs.json','name','焕然一新')
        e=next(e for e in self.status_entries(scan) if e.file=='BattleKeywords.json' and e.field=='name')
        self.cache.ignore(e,True)
        align_status_terms(scan)
        self.assertEqual(e.status,'ignored')
        self.assertEqual(next(e for e in self.status_entries(self.scan()) if e.file=='BattleKeywords.json' and e.field=='name').status,'ignored')

    def test_bad_numeric_translation_is_not_reused(self):
        scan=self.prepare()
        e=next(e for e in self.status_entries(scan) if e.file=='Bufs.json' and e.field=='desc')
        e.translation='获得9层[Binding]。';e.status='cached'
        align_status_terms(scan)
        other=next(e for e in self.status_entries(scan) if e.file=='BattleKeywords.json' and e.field=='desc')
        self.assertEqual(other.status,'pending')
        with self.assertRaises(BridgeError):payload(scan)

    def test_non_status_tables_are_not_aligned(self):
        self.make_status();self.make_status('Enemies.json')
        scan=self.scan();self.save(scan,'Bufs.json','name','焕然一新')
        enemy=next(e for e in scan.entries if e.file=='Enemies.json' and e.field=='name')
        align_status_terms(scan);self.assertEqual(enemy.status,'pending')

    def test_subdirectory_copies_are_excluded_from_alignment(self):
        self.make_status();self.make_status('StoryData/Bufs.json')
        scan=self.scan();self.save(scan,'Bufs.json','name','焕然一新')
        other=next(e for e in scan.entries if e.file=='StoryData/Bufs.json' and e.field=='name')
        align_status_terms(scan);self.assertEqual(other.status,'pending')

    def test_parallel_new_translations_align_before_return(self):
        scan=self.prepare();barrier=threading.Barrier(2,timeout=3)
        chosen=[e for e in self.status_entries(scan) if e.field=='name']
        def handler(data,n):
            barrier.wait()
            return reply([{'id':r['id'],'text':'焕然一新' if r['file']=='Bufs.json' else '全新造型'} for r in data['entries']])
        client=SimulatedClient(handler)
        result=translate(chosen,scan,self.cache,client,{'interval':0,'concurrency':2})
        self.assertEqual(result,{'success':2,'failed':0,'total':2})
        self.assertEqual({e.translation for e in chosen},{'焕然一新'})

    def test_known_status_name_sent_for_protected_keyword_reference(self):
        scan=self.prepare();self.save(scan,'Bufs.json','name','焕然一新')
        self.write_source('Skills_extra.json',{'dataList':[{'id':1,'desc':'Gain [RougeIshmaelEclose].'}]})
        scan=self.scan();skill=next(e for e in scan.entries if e.file=='Skills_extra.json')
        def handler(data,n):
            self.assertEqual(data['status_terms']['RougeIshmaelEclose'],'焕然一新')
            return reply([{'id':r['id'],'text':r['source'].replace('Gain ','获得')} for r in data['entries']])
        result=translate([skill],scan,self.cache,SimulatedClient(handler),{'interval':0})
        self.assertEqual(result['success'],1)

    def test_report_and_pack_version_record_alignment(self):
        scan=self.prepare();self.save(scan,'Bufs.json','name','焕然一新')
        self.save(scan,'BattleKeywords.json','name','全新造型')
        result=install_pack(scan,self.data,check_running=False)
        marker=read_json(self.zh.parent/'LimbusAI_zh-CN/.limbus-ai-bridge.json')
        self.assertEqual(marker['pack_rules_version'],PACK_RULES_VERSION)
        self.assertGreater(result['status_aligned'],0)
        report=export_report(scan,self.data)
        self.assertTrue(read_json(report/'scan.json')['status_alignment'])

    def test_preexisting_human_differences_are_recorded_without_new_ai_warning(self):
        self.prepare()
        self.write_zh('Bufs.json',{'dataList':[{'id':'RougeIshmaelEclose','name':'人工甲'}]})
        self.write_zh('BattleKeywords.json',{'dataList':[{'id':'RougeIshmaelEclose','name':'人工乙'}]})
        scan=self.scan()
        differences=[r for r in scan.status_alignment_conflicts if r['field']=='name']
        self.assertEqual(len(differences),1)
        self.assertFalse(differences[0]['needs_review'])
        self.assertEqual(scan.summary()['status_conflicts'],0)
