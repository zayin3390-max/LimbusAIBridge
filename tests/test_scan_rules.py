import json
from test_bridge import Fixture
from bridge.core import classify,Entry,stable_id,flatten,payload,export_report
from bridge.scan_rules import resource_groups

class ScanRuleTests(Fixture):
    def manifest(self,groups):
        self.write(self.loc/'RemoteLocalizeFileList.json',groups)

    def test_native_hana_in_human_chinese_is_preserved(self):
        self.assertIsNone(classify('Hana Association','하나协会',True))
        self.write_source('StoryData/S1.json',{'dataList':[{'id':0,'content':'The Hana Association handles this.'}]})
        human={'dataList':[{'id':0,'content':'由하나协会处理。'}]}
        self.write_zh('StoryData/S1.json',human)
        s=self.scan()
        self.assertFalse([e for e in s.entries if e.file=='StoryData/S1.json'])
        output,count=payload(s)
        self.assertEqual(json.loads(output['StoryData/S1.json']),human)

    def test_chinese_mixed_with_unknown_korean_needs_review(self):
        self.write_source('StoryData/S1.json',{'dataList':[{'id':0,'content':'A name appears.'}]})
        self.write_zh('StoryData/S1.json',{'dataList':[{'id':0,'content':'名字是홍길동。'}]})
        s=self.scan();e=next(e for e in s.entries if e.file=='StoryData/S1.json')
        self.assertEqual(e.reason,'mixed');self.assertFalse(e.candidate)

    def test_initial_snapshot_does_not_claim_new_missing_content(self):
        s=self.scan();self.cache.observe(s)
        self.assertTrue(s.entries)
        self.assertEqual(s.summary()['recommended'],0)
        self.assertTrue(all(not e.newly_seen for e in s.entries))
        s2=self.scan();self.cache.observe(s2)
        self.assertEqual(s2.summary()['recommended'],0)

    def test_later_new_content_still_recommended_and_persistent(self):
        s=self.scan();self.cache.observe(s)
        self.write_source('Egos.json',{'dataList':[{'id':20101,'name':'New EGO'}]})
        new=self.scan();self.cache.observe(new)
        self.assertEqual([e.source for e in new.entries if e.recommended],['New EGO'])
        again=self.scan();self.cache.observe(again)
        self.assertEqual([e.source for e in again.entries if e.recommended],['New EGO'])
        self.write_zh('Egos.json',{'dataList':[{'id':20101,'name':'人工新异想体'}]})
        translated=self.scan();self.cache.observe(translated)
        self.assertEqual(translated.summary()['recommended'],0)

    def test_new_korean_developer_label_is_not_auto_recommended(self):
        s=self.scan();self.cache.observe(s)
        self.write_source('Items.json',{'dataList':[{'id':10,'desc':'미사용 설명'}]})
        self.write_zh('Items.json',{'dataList':[{'id':10,'desc':'미사용 설명'}]})
        new=self.scan();self.cache.observe(new)
        e=next(e for e in new.entries if e.file=='Items.json')
        self.assertTrue(e.newly_seen);self.assertEqual(e.reason,'same')
        self.assertFalse(e.recommended)

    def test_bubble_descriptions_excluded_but_spoken_lines_kept(self):
        self.write_source('BattleSpeechBubbleDlg.json',{'dataList':[{'id':'speech','desc':'사용시 설명','dlg':'New dialogue'}]})
        s=self.scan();self.cache.observe(s)
        rows=[e for e in s.entries if e.file=='BattleSpeechBubbleDlg.json']
        self.assertEqual([e.field for e in rows],['dlg'])
        self.assertTrue(any(x['reason']=='engine_note' for x in s.exclusions))

    def test_explicit_no_display_marker_excluded(self):
        self.write_source('StoryData/S1.json',{'dataList':[{'id':0,'content':'[DEVELOPER COMMENT NOT TO DISPLAY]'},
            {'id':1,'content':'//효과연출1'},{'id':2,'content':'Actual dialogue'}]})
        rows=[e.source for e in self.scan().entries if e.file=='StoryData/S1.json']
        self.assertEqual(rows,['Actual dialogue'])

    def test_identical_split_table_covered_by_translated_main_table(self):
        self.manifest({'userBanner':['UserBanner','UserBanner-season']})
        source={'dataList':[{'id':60,'name':'Season 6 Banner','desc':'Level 1'}]}
        self.write_source('UserBanner.json',source);self.write_source('UserBanner-season.json',source)
        self.write_zh('UserBanner.json',{'dataList':[{'id':60,'name':'第6赛季横幅','desc':'等级1'}]})
        s=self.scan()
        self.assertFalse([e for e in s.entries if e.file.startswith('UserBanner')])
        self.assertEqual(len([x for x in s.exclusions if x['reason']=='merged_table']),2)
        self.assertEqual({tuple(x['covered_by']) for x in s.exclusions if x['reason']=='merged_table'},{('UserBanner.json',)})

    def test_same_id_with_different_source_not_considered_covered(self):
        self.manifest({'userBanner':['UserBanner','UserBanner-season']})
        self.write_source('UserBanner.json',{'dataList':[{'id':60,'name':'Old banner'}]})
        self.write_zh('UserBanner.json',{'dataList':[{'id':60,'name':'旧横幅'}]})
        self.write_source('UserBanner-season.json',{'dataList':[{'id':60,'name':'Changed banner'}]})
        self.assertEqual([e.source for e in self.scan().entries if e.file=='UserBanner-season.json'],['Changed banner'])

    def test_cross_family_same_id_and_text_cannot_cover(self):
        self.manifest({'userBanner':['UserBanner'],'personality':['Personalities']})
        source={'dataList':[{'id':1,'name':'Same name'}]}
        self.write_source('UserBanner.json',source);self.write_source('Personalities.json',source)
        self.write_zh('UserBanner.json',{'dataList':[{'id':1,'name':'横幅名称'}]})
        self.assertTrue(any(e.file=='Personalities.json' for e in self.scan().entries))

    def test_conflicting_translations_do_not_suppress_difference(self):
        self.manifest({'userBanner':['UserBanner','UserBanner-other','UserBanner-season']})
        source={'dataList':[{'id':1,'name':'Same name'}]}
        for name in ('UserBanner','UserBanner-other','UserBanner-season'):
            self.write_source(name+'.json',source)
        self.write_zh('UserBanner.json',{'dataList':[{'id':1,'name':'译名甲'}]})
        self.write_zh('UserBanner-other.json',{'dataList':[{'id':1,'name':'译名乙'}]})
        self.assertTrue(any(e.file=='UserBanner-season.json' for e in self.scan().entries))

    def test_voice_directory_is_resolved_without_duplicate_root_warning(self):
        self.manifest({'announcerVoice':['Announcer_Test']})
        source={'dataList':[{'id':'a','dlg':'A spoken line'}]}
        self.write_source('Announcer_Test.json',source)
        self.write_source('BattleAnnouncerDlg/Announcer_Test.json',source)
        self.write_zh('BattleAnnouncerDlg/Announcer_Test.json',{'dataList':[{'id':'a','dlg':'一句台词'}]})
        s=self.scan()
        self.assertFalse([e for e in s.entries if 'Announcer_Test' in e.file])
        self.assertEqual(len([x for x in s.exclusions if x['reason']=='duplicate_resource']),1)
        self.assertEqual(resource_groups({'announcerVoice':['Announcer_Test']}),{'battleannouncerdlg/announcer_test.json':'announcerVoice'})

    def test_ui_copy_under_story_directory_covered(self):
        self.manifest({'ui':['ProjectGS']})
        source={'dataList':[{'id':'button','content':'Begin Class'}]}
        self.write_source('ProjectGS.json',source)
        self.write_source('StoryData/ProjectGS.json',source)
        self.write_zh('ProjectGS.json',{'dataList':[{'id':'button','content':'开始上课'}]})
        self.assertFalse([e for e in self.scan().entries if 'ProjectGS' in e.file])

    def test_old_unproven_story_remains_reviewable(self):
        self.write_source('StoryData/Old.json',{'dataList':[{'id':0,'content':'Old alternate scene'}]})
        s=self.scan();self.cache.observe(s)
        e=next(e for e in s.entries if e.file=='StoryData/Old.json')
        self.assertTrue(e.candidate);self.assertFalse(e.recommended)
        self.assertEqual(e.reason,'missing')

    def test_old_cached_developer_note_cannot_enter_new_pack(self):
        rel='BattleSpeechBubbleDlg.json'
        source={'dataList':[{'id':'a','desc':'开发用说明','dlg':'Hello'}]}
        self.write_source(rel,source)
        self.write_zh(rel,{'dataList':[{'id':'a','desc':'개발자 설명','dlg':'你好'}]})
        tokens,path,field,text=next(x for x in flatten(source) if x[2]=='desc')
        e=Entry(stable_id(rel,tokens),rel,tokens,path,field,text,'개발자 설명','foreign',True)
        self.cache.put(e,'旧AI误译','test')
        s=self.scan()
        output,count=payload(s)
        self.assertEqual(count,0)
        self.assertEqual(json.loads(output[rel])['dataList'][0]['desc'],'개발자 설명')
        with self.cache.connect() as con:
            self.assertEqual(con.execute('SELECT COUNT(*) FROM translations').fetchone()[0],1)

    def test_report_includes_exclusion_evidence(self):
        self.write_source('BattleSpeechBubbleDlg.json',{'dataList':[{'id':'a','desc':'internal','dlg':'Hello'}]})
        s=self.scan();self.cache.observe(s)
        report=json.loads((export_report(s,self.data)/'scan.json').read_text(encoding='utf-8'))
        self.assertEqual(report['summary']['recommended'],0)
        self.assertTrue(report['exclusions'])

    def test_stale_wrong_directory_ui_copy_is_not_a_new_story(self):
        self.manifest({'ui':['ProjectGS']})
        self.write_source('ProjectGS.json',{'dataList':[{'id':'ui_button','content':'Current button'}]})
        self.write_zh('ProjectGS.json',{'dataList':[{'id':'ui_button','content':'当前按钮'}]})
        s=self.scan();self.cache.observe(s)
        self.write_source('StoryData/ProjectGS.json',{'dataList':[{'id':'ui_button','content':'Stale button'}]})
        new=self.scan();self.cache.observe(new)
        self.assertFalse([e for e in new.entries if e.file=='StoryData/ProjectGS.json'])
        self.assertTrue(any(x['reason']=='outside_manifest_path' for x in new.exclusions))

    def test_genuinely_new_story_without_manifest_entry_is_detected(self):
        self.manifest({'gachaTitle':['GachaTitle']})
        s=self.scan();self.cache.observe(s)
        self.write_source('StoryData/S999B.json',{'dataList':[{'id':0,'content':'A real new story'}]})
        new=self.scan();self.cache.observe(new)
        e=next(e for e in new.entries if e.file=='StoryData/S999B.json')
        self.assertTrue(e.recommended)
