import copy
import json
from test_bridge import Fixture
from bridge.core import (Cache, Entry, digest, dumps, flatten, stable_id, legacy_rpg_id,
                         payload, export_report, validate_translation)
from bridge.ui_model import matches

DIALOGUE='RPGSystem/rpg-loc-dialogue-floor-1.json'

class RPGTests(Fixture):
    def setUp(self):
        super().setUp()
        self.write(self.loc/'RemoteLocalizeFileList.json',{'skill':['Skills_personality-01']})

    def rpg(self,rows,file=DIALOGUE,lang='en'):
        self.write_source(file,{'dataList':rows},lang)

    def lines(self,text='A small shop.',speaker='Dante'):
        return [{'key':'D1','texts':[{'index':0,'text':text,'speaker':speaker}]}]

    def rpg_entries(self,scan,file=DIALOGUE):
        return [e for e in scan.entries if e.file==file]

    def test_unlisted_exported_dialogue_is_visible_on_first_scan(self):
        self.rpg(self.lines())
        scan=self.scan();self.cache.observe(scan);rows=self.rpg_entries(scan)
        self.assertEqual({e.field for e in rows},{'text','speaker'})
        self.assertTrue(all(e.active and e.category=='主线剧情' and e.needs_translation for e in rows))
        self.assertTrue(all(not e.recommended and e.coverage_gap for e in rows))
        self.assertTrue(all(matches(e,'缺漏补查',{'主线剧情'}) for e in rows))
        self.assertTrue(all(matches(e,'待补译',{'主线剧情'}) for e in rows))
        self.assertFalse(any('未识别文本字段 speaker' in w or '未识别文本字段 key ' in w for w in scan.warnings))

    def test_key_and_index_survive_block_and_line_reordering(self):
        rows=self.lines()+[{'key':'D2','texts':[{'index':0,'text':'Second line.'},{'index':1,'text':'Third line.'}]}]
        self.rpg(rows);first=self.rpg_entries(self.scan())
        for e in first:
            if e.source=='Third line.':self.cache.put(e,'第三句。','manual')
        rows.reverse();rows[0]['texts'].reverse();self.rpg(rows)
        again=self.scan();current=self.rpg_entries(again)
        self.assertEqual({e.uid for e in first},{e.uid for e in current})
        self.assertEqual(next(e.translation for e in current if e.source=='Third line.'),'第三句。')
        output,_=payload(again)
        result=json.loads(output[DIALOGUE])
        self.assertEqual(result['dataList'][0]['key'],'D2')
        self.assertEqual(result['dataList'][0]['texts'][0]['text'],'第三句。')

    def test_quest_item_npc_and_ui_fields_are_covered(self):
        fixtures={
            'quest':[{'key':'Q1','title':'A Quest','description':'Find the door.','steps':[{'index':0,'goalDescription1':'Search','goalDescription6':'Return','goalDescription7':'Exit'}]}],
            'item':[{'key':'I1','displayName':'Red Key','description':'A key.','statText':'HP +2','iconId':'Icon-Key'}],
            'npc':[{'key':'N1','displayName':'Guide'}],
            'location':[{'key':'L1','text':'The Hall'}],
            'narration':[{'key':'T1','text':'A narrow passage.'}],
            'dialogue-choice':[{'key':'DC1','text':'Take the left door.'}],
            'ui':[{'key':'ShowMap','text':'Open the map?'}]}
        for kind,rows in fixtures.items():self.rpg(rows,f'RPGSystem/rpg-loc-{kind}-floor-1.json')
        rows=[e for e in self.scan().entries if e.file.startswith('RPGSystem/')]
        self.assertTrue(all(e.active and e.coverage_gap for e in rows))
        self.assertTrue({'goalDescription1','goalDescription6','goalDescription7','displayName','statText'}<={e.field for e in rows})
        self.assertFalse(any(e.field in ('key','iconId','index') for e in rows))

    def test_extra_fields_not_enabled_outside_known_rpg_schema(self):
        self.write_source('Other.json',{'dataList':[{'id':1,'speaker':'Engine Code','displayName':'Engine Name','statText':'Code X','goalDescription1':'Unused'}]})
        self.assertFalse(any(e.file=='Other.json' for e in self.scan().entries))

    def test_unknown_rpg_file_does_not_become_active(self):
        self.rpg(self.lines(),'RPGSystem/rpg-loc-debug-test.json')
        rows=[e for e in self.scan().entries if e.file.endswith('rpg-loc-debug-test.json')]
        self.assertTrue(rows)
        self.assertTrue(all(not e.active and not e.coverage_gap for e in rows))

    def test_explicit_hidden_quest_is_excluded_but_korean_dialogue_is_not(self):
        file='RPGSystem/rpg-loc-quest-floor-1.json'
        self.rpg([{'key':'Q0','title':'오프닝','description':'연출 처리용 숨겨진 퀘스트','steps':[{'index':0}]},
                  {'key':'Q1','title':'Find the exit','description':'Keep moving.'}],file)
        self.rpg(self.lines('여기는 가게 같다.'))
        scan=self.scan()
        self.assertFalse(any(('row','key','Q0') in e.tokens for e in scan.entries))
        self.assertTrue(any(e.source=='여기는 가게 같다.' for e in scan.entries))
        self.assertTrue(any(x['file']==file and x['reason']=='engine_note' for x in scan.exclusions))

    def test_duplicates_and_missing_keys_never_merge_into_another_row(self):
        self.rpg([{'key':'D1','text':'One'},{'key':'D1','text':'Other'},{'text':'Missing key'},
                  {'key':'D2','text':'Safe'}])
        scan=self.scan()
        self.assertEqual([e.source for e in self.rpg_entries(scan)],['Safe'])
        self.assertTrue(any('重复/缺失' in w for w in scan.warnings))

    def test_reference_language_uses_keys_instead_of_positions(self):
        self.rpg([{'key':'D1','text':'One'},{'key':'D2','text':'Two'}])
        self.rpg([{'key':'D2','text':'둘'},{'key':'D1','text':'하나'}],lang='kr')
        row=next(e for e in self.rpg_entries(self.scan()) if e.source=='Two')
        self.assertEqual(row.refs['kr'],'둘')

    def test_human_pack_priority_with_different_row_order(self):
        self.rpg([{'key':'D1','text':'One'},{'key':'D2','text':'Two'}])
        human={'dataList':[{'key':'D2','text':'人工第二句'},{'key':'D1','text':'人工第一句'}]}
        self.write_zh(DIALOGUE,human)
        scan=self.scan()
        self.assertFalse(self.rpg_entries(scan))
        output,_=payload(scan);self.assertEqual(json.loads(output[DIALOGUE]),human)

    def legacy_entry(self,row):
        old=copy.deepcopy(row);old.uid=legacy_rpg_id(row.file,row.tokens,row.path)
        self.assertIsNotNone(old.uid)
        return old

    def test_positional_cache_is_reused_without_rewriting_old_record(self):
        self.rpg(self.lines());scan=self.scan();row=next(e for e in self.rpg_entries(scan) if e.field=='text')
        old=self.legacy_entry(row);self.cache.put(old,'一家小店。','manual')
        reloaded=next(e for e in self.rpg_entries(self.scan()) if e.field=='text')
        self.assertEqual(reloaded.translation,'一家小店。')
        with self.cache.connect() as con:
            self.assertEqual(con.execute('SELECT uid FROM translations').fetchone()[0],old.uid)

    def test_positional_cache_rejected_when_reference_changes(self):
        self.rpg(self.lines());row=next(e for e in self.rpg_entries(self.scan()) if e.field=='text')
        self.cache.put(self.legacy_entry(row),'一家小店。','manual')
        self.rpg(self.lines('작은 가게.'),lang='kr')
        changed=next(e for e in self.rpg_entries(self.scan()) if e.field=='text')
        self.assertEqual(changed.status,'pending')

    def test_legacy_ignore_can_be_restored(self):
        self.rpg(self.lines());row=next(e for e in self.rpg_entries(self.scan()) if e.field=='text')
        self.cache.ignore(self.legacy_entry(row))
        row=next(e for e in self.rpg_entries(self.scan()) if e.field=='text');self.assertEqual(row.status,'ignored')
        self.cache.ignore(row,False)
        self.assertEqual(next(e.status for e in self.rpg_entries(self.scan()) if e.field=='text'),'pending')

    def test_saving_translation_resolves_legacy_ignore(self):
        self.rpg(self.lines());row=next(e for e in self.rpg_entries(self.scan()) if e.field=='text')
        self.cache.ignore(self.legacy_entry(row));self.cache.put(row,'一家小店。','manual')
        row=next(e for e in self.rpg_entries(self.scan()) if e.field=='text')
        self.assertEqual(row.status,'cached')

    def test_feature_upgrade_not_reported_as_game_update(self):
        self.rpg(self.lines());scan=self.scan()
        scope=digest(str(scan.game).casefold()+'|'+scan.source_lang)
        row=next(e for e in self.rpg_entries(scan) if e.field=='text')
        with self.cache.connect() as con:
            con.execute('INSERT INTO observed VALUES (?,?,?,?)',(scope,digest(legacy_rpg_id(row.file,row.tokens,row.path)),digest(row.source),0))
        self.cache.observe(scan)
        self.assertTrue(all(not e.newly_seen and e.needs_translation for e in self.rpg_entries(scan)))
        again=self.scan();self.cache.observe(again)
        self.assertTrue(all(not e.newly_seen for e in self.rpg_entries(again)))
        self.rpg(self.lines('The shop has changed.'))
        changed=self.scan();self.cache.observe(changed)
        self.assertTrue(next(e.recommended for e in self.rpg_entries(changed) if e.field=='text'))

    def test_cached_and_ignored_rows_leave_pending_view(self):
        self.rpg(self.lines());scan=self.scan();rows=self.rpg_entries(scan)
        self.cache.put(next(e for e in rows if e.field=='text'),'一家小店。','manual')
        self.cache.ignore(next(e for e in rows if e.field=='speaker'))
        self.assertFalse(any(e.needs_translation for e in rows))

    def test_known_speaker_reuses_human_name_with_reference_evidence(self):
        self.write_source('ScenarioModelCodes.json',{'dataList':[{'id':'guide','name':'Dante'}]})
        self.write_source('ScenarioModelCodes.json',{'dataList':[{'id':'guide','name':'단테'}]},'kr')
        self.write_zh('ScenarioModelCodes.json',{'dataList':[{'id':'guide','name':'但丁'}]})
        self.rpg(self.lines());self.rpg(self.lines('가게.',speaker='단테'),lang='kr')
        row=next(e for e in self.rpg_entries(self.scan()) if e.field=='speaker')
        self.assertEqual(row.status,'cached');self.assertEqual(row.translation,'但丁')

    def test_same_english_npc_names_with_different_references_stay_separate(self):
        file='RPGSystem/rpg-loc-npc-floor-1.json'
        self.rpg([{'key':'N1','displayName':'Mercury'},{'key':'N2','displayName':'Mercury'}],file)
        self.rpg([{'key':'N1','displayName':'수은'},{'key':'N2','displayName':'머큐리'}],file,'kr')
        scan=self.scan();rows=self.rpg_entries(scan,file)
        self.cache.put(rows[0],'水银','manual')
        from bridge.consistency import align_translations
        align_translations(scan)
        self.assertEqual(rows[1].status,'pending')

    def test_identical_dialogue_in_other_blocks_not_forced_to_same_translation(self):
        self.rpg([{'key':'D1','texts':[{'index':0,'text':'Fine.'}]},{'key':'D2','texts':[{'index':0,'text':'Fine.'}]}])
        scan=self.scan();rows=self.rpg_entries(scan);self.cache.put(rows[0],'好吧。','manual')
        from bridge.consistency import align_translations
        align_translations(scan)
        self.assertEqual(rows[1].status,'pending')

    def test_output_preserves_directory_keys_markup_and_dante_brackets(self):
        self.rpg(self.lines('<This place... looks like some kind of store...>'))
        scan=self.scan();row=next(e for e in self.rpg_entries(scan) if e.field=='text')
        self.cache.put(row,'<这里……看起来像是什么商店……>','manual')
        output,_=payload(scan)
        data=json.loads(output[DIALOGUE]);self.assertEqual(data['dataList'][0]['key'],'D1')
        self.assertEqual(data['dataList'][0]['texts'][0]['index'],0)
        self.assertEqual(data['dataList'][0]['texts'][0]['text'],'<这里……看起来像是什么商店……>')
        self.assertNotIn('RPGSystem/EN_rpg-loc-dialogue-floor-1.json',output)

    def test_report_separates_coverage_gap_from_new_update(self):
        self.rpg(self.lines());scan=self.scan();self.cache.observe(scan)
        directory=export_report(scan,self.data)
        report=json.loads((directory/'scan.json').read_text(encoding='utf-8'))
        self.assertEqual(report['summary']['coverage_missing'],2)
        self.assertEqual(report['summary']['recommended'],0)
        self.assertEqual(report['summary']['pending'],2)
        self.assertTrue(all(e['coverage_gap'] for e in report['entries'] if e['file']==DIALOGUE))
