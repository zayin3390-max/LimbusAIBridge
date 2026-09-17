import unittest
import copy
import json
from unittest.mock import patch
from test_bridge import Fixture
from test_validation_retries import SimulatedClient,reply
from bridge.core import payload,protect,restore,validate_translation,BridgeError,TOKENS
from bridge.consistency import align_translations,locked_terms


class ConsistencyTests(Fixture):
    def source(self,file,rows,kr=None):
        self.write_source(file,{'dataList':rows})
        if kr is not None:self.write_source(file,{'dataList':kr},lang='kr')

    def pick(self,scan,file,field='name',row=None,level=None):
        return next(e for e in scan.entries if e.file==file and e.field==field
                    and (row is None or ('row','id',str(row)) in e.tokens)
                    and (level is None or ('row','level',str(level)) in e.tokens))

    def save(self,e,text,model='simulation'):
        self.cache.put(e,text,model);return e

    def test_skill_names_across_levels_align_but_different_numbers_stay(self):
        self.source('Skills_extra.json',[{'id':88,'levelList':[
            {'level':1,'name':'Triple Stamped Stitching','desc':'Gain 3 [Binding].'},
            {'level':4,'name':'Triple Stamped Stitching','desc':'Gain 4 [Binding].'}]}])
        s=self.scan()
        self.save(self.pick(s,'Skills_extra.json',level=1),'三重踏印缝合')
        self.save(self.pick(s,'Skills_extra.json',level=4),'三重压印缝线')
        self.save(self.pick(s,'Skills_extra.json','desc',level=1),'获得3层[Binding]。')
        self.save(self.pick(s,'Skills_extra.json','desc',level=4),'获得4层[Binding]。')
        output,_=payload(s)
        levels=json.loads(output['Skills_extra.json'])['dataList'][0]['levelList']
        self.assertEqual(levels[0]['name'],levels[1]['name'])
        self.assertNotEqual(levels[0]['desc'],levels[1]['desc'])

    def test_identical_same_skill_descriptions_align_without_merging_coin_indexes(self):
        self.source('Skills_extra.json',[{'id':88,'levelList':[
            {'level':1,'name':'Test','desc':'Gain 3 [Binding].','coinlist':[{'coindescs':[{'desc':'Strike.'}]},{'coindescs':[{'desc':'Strike.'}]}]},
            {'level':4,'name':'Test','desc':'Gain 3 [Binding].'}]}])
        s=self.scan()
        self.save(self.pick(s,'Skills_extra.json','desc',level=1),'获得3层[Binding]。')
        self.save(self.pick(s,'Skills_extra.json','desc',level=4),'得到3层[Binding]。')
        coins=[e for e in s.entries if e.file=='Skills_extra.json' and e.source=='Strike.']
        self.save(coins[0],'敲击。');self.save(coins[1],'打击。')
        align_translations(s)
        desc=[e for e in s.entries if e.file=='Skills_extra.json' and e.source=='Gain 3 [Binding].']
        self.assertEqual(len({e.translation for e in desc}),1)
        self.assertEqual([e.translation for e in coins],['敲击。','打击。'])

    def test_passive_and_ego_split_tables_reuse_same_ids(self):
        for root in ('Passives','Egos','Personalities','Enemies','Announcer'):
            for file in (root+'.json',root+'-new.json'):
                self.source(file,[{'id':88,'name':'Proper Name'}])
        s=self.scan()
        for root in ('Passives','Egos','Personalities','Enemies','Announcer'):
            self.save(self.pick(s,root+'.json'),'统一名称')
        align_translations(s)
        self.assertTrue(all(self.pick(s,root+'-new.json').translation=='统一名称'
                            for root in ('Passives','Egos','Personalities','Enemies','Announcer')))

    def test_same_numeric_id_in_unrelated_families_is_not_joined(self):
        self.source('Enemies.json',[{'id':88,'name':'Proper Name'}])
        self.source('Skills_extra.json',[{'id':88,'name':'Proper Name'}])
        s=self.scan();self.save(self.pick(s,'Enemies.json'),'敌人名称')
        self.save(self.pick(s,'Skills_extra.json'),'技能名称')
        align_translations(s)
        self.assertEqual(self.pick(s,'Enemies.json').translation,'敌人名称')
        self.assertEqual(self.pick(s,'Skills_extra.json').translation,'技能名称')

    def test_repeated_story_speaker_names_share_reference_evidence(self):
        for file in ('StoryData/S1.json','StoryData/S2.json'):
            self.source(file,[{'id':1,'teller':'Dubois','content':'Hello.'}],
                        [{'id':1,'teller':'뒤부아','content':'안녕.'}])
        s=self.scan()
        self.save(self.pick(s,'StoryData/S1.json','teller'),'杜布瓦')
        self.save(self.pick(s,'StoryData/S2.json','teller'),'迪布瓦')
        align_translations(s)
        self.assertEqual(self.pick(s,'StoryData/S1.json','teller').translation,
                         self.pick(s,'StoryData/S2.json','teller').translation)

    def test_same_english_but_different_korean_names_stay_separate(self):
        self.source('Enemies.json',[{'id':1,'name':'Mercury'},{'id':2,'name':'Mercury'}],
                    [{'id':1,'name':'수은'},{'id':2,'name':'머큐리'}])
        s=self.scan();self.save(self.pick(s,'Enemies.json',row=1),'水银')
        self.save(self.pick(s,'Enemies.json',row=2),'墨丘利')
        align_translations(s)
        self.assertEqual(self.pick(s,'Enemies.json',row=1).translation,'水银')
        self.assertEqual(self.pick(s,'Enemies.json',row=2).translation,'墨丘利')
        self.assertNotIn('Mercury',s.consistency_terms)

    def test_without_references_cross_file_homonyms_stay_separate(self):
        for file in ('StoryData/S1.json','StoryData/S2.json'):
            self.source(file,[{'id':1,'teller':'Watch'}])
        s=self.scan();self.save(self.pick(s,'StoryData/S1.json','teller'),'守望者')
        self.save(self.pick(s,'StoryData/S2.json','teller'),'手表')
        align_translations(s)
        self.assertEqual(self.pick(s,'StoryData/S1.json','teller').translation,'守望者')
        self.assertEqual(self.pick(s,'StoryData/S2.json','teller').translation,'手表')

    def test_human_definition_name_is_used_by_new_dialogue(self):
        self.source('ScenarioModelCodes.json',[{'id':'gubo','name':'Gubo'}],[{'id':'gubo','name':'구보'}])
        self.write_zh('ScenarioModelCodes.json',{'dataList':[{'id':'gubo','name':'仇甫'}]})
        self.source('StoryData/S1.json',[{'id':1,'teller':'Gubo'}],[{'id':1,'teller':'구보'}])
        s=self.scan()
        self.assertEqual(self.pick(s,'StoryData/S1.json','teller').translation,'仇甫')
        self.assertEqual(json.loads(payload(s)[0]['ScenarioModelCodes.json'])['dataList'][0]['name'],'仇甫')

    def test_normal_dialogue_variation_is_not_harmonized(self):
        self.source('StoryData/S1.json',[{'id':1,'content':'No.'},{'id':2,'content':'No.'}])
        s=self.scan();self.save(self.pick(s,'StoryData/S1.json','content',1),'不行。')
        self.save(self.pick(s,'StoryData/S1.json','content',2),'没有。')
        align_translations(s)
        self.assertEqual(self.pick(s,'StoryData/S1.json','content',1).translation,'不行。')
        self.assertEqual(self.pick(s,'StoryData/S1.json','content',2).translation,'没有。')

    def test_quoted_skill_reference_matches_name_even_if_old_variant_not_in_name_cache(self):
        self.source('Skills_extra.json',[{'id':88,'name':'Triple Stamped Stitching'}])
        self.source('Passives_extra.json',[{'id':99,'desc':'Use "Triple Stamped Stitching" to gain +3 [Binding].'}])
        s=self.scan();self.save(self.pick(s,'Skills_extra.json'),'三重压印缝线')
        e=self.pick(s,'Passives_extra.json','desc');self.save(e,'使用“三重压印缝合”来获得+3[Binding]。')
        align_translations(s)
        self.assertEqual(e.translation,'使用“三重压印缝线”来获得+3[Binding]。')

    def test_tags_and_attribute_quotes_are_never_changed(self):
        self.source('Skills_extra.json',[{'id':88,'name':'Stitching'}])
        self.source('Passives_extra.json',[{'id':99,'desc':'<style="Stitching">Use "Stitching".</style>'}])
        s=self.scan();self.save(self.pick(s,'Skills_extra.json'),'缝线')
        e=self.pick(s,'Passives_extra.json','desc');self.save(e,'<style="Stitching">使用“缝合”。</style>')
        align_translations(s)
        self.assertEqual(e.translation,'<style="Stitching">使用“缝线”。</style>')

    def test_unquoted_actor_alias_repaired_only_when_source_mentions_actor(self):
        self.source('StoryData/S1.json',[{'id':1,'teller':'Dubois'},{'id':2,'teller':'Dubois'},
                    {'id':3,'content':'Dubois is here.'},{'id':4,'content':'Someone is here.'}])
        s=self.scan();self.save(self.pick(s,'StoryData/S1.json','teller',1),'杜布瓦')
        self.save(self.pick(s,'StoryData/S1.json','teller',2),'迪布瓦')
        self.save(self.pick(s,'StoryData/S1.json','content',3),'迪布瓦在这里。')
        self.save(self.pick(s,'StoryData/S1.json','content',4),'迪布瓦在这里。')
        align_translations(s)
        self.assertEqual(self.pick(s,'StoryData/S1.json','content',3).translation,'杜布瓦在这里。')
        self.assertEqual(self.pick(s,'StoryData/S1.json','content',4).translation,'迪布瓦在这里。')

    def test_compound_location_uses_affiliation_name_and_is_idempotent(self):
        self.source('UnitKeyword.json',[{'id':'noir','content':'Le Noir'}],[{'id':'noir','content':'르누아르'}])
        self.source('StoryData/S1.json',[{'id':1,'title':'Le Noir Footwear Hall'},
                    {'id':2,'content':'Welcome to Le Noir Footwear Hall.'}])
        s=self.scan();self.save(self.pick(s,'UnitKeyword.json','content'),'勒努瓦')
        self.save(self.pick(s,'StoryData/S1.json','title'),'Le Noir鞋履馆')
        self.save(self.pick(s,'StoryData/S1.json','content'),'欢迎来到Le Noir鞋履馆。')
        align_translations(s)
        self.assertEqual(self.pick(s,'StoryData/S1.json','title').translation,'勒努瓦鞋履馆')
        self.assertEqual(self.pick(s,'StoryData/S1.json','content').translation,'欢迎来到勒努瓦鞋履馆。')
        before=[(e.uid,e.translation) for e in s.entries]
        align_translations(s)
        self.assertEqual([(e.uid,e.translation) for e in s.entries],before)

    def test_locked_terms_restore_canonical_name_and_preserve_numeric_tags(self):
        source='Use "Triple Stamped Stitching" for +3 [Binding].'
        masked,tokens=protect(source,numbers=True,terms={'Triple Stamped Stitching':'三重压印缝线'})
        self.assertNotIn('Triple Stamped Stitching',masked)
        output=restore(masked.replace('Use ','使用').replace(' for ','获得'),tokens)
        validate_translation(source,output)
        self.assertIn('三重压印缝线',output);self.assertIn('+3',output);self.assertIn('[Binding]',output)

    def test_literal_names_inside_engine_tokens_are_not_replaced(self):
        source='<link="Dubois">Dubois</link>'
        masked,tokens=protect(source,numbers=True,terms={'Dubois':'杜布瓦'})
        restored=restore(masked,tokens)
        self.assertEqual(restored,'<link="Dubois">杜布瓦</link>')

    def test_provider_sends_protected_canonical_skill_reference(self):
        self.source('Skills_extra.json',[{'id':88,'name':'Stitching'}])
        self.source('Passives_extra.json',[{'id':99,'desc':'Use "Stitching".'}])
        s=self.scan();self.save(self.pick(s,'Skills_extra.json'),'缝线')
        e=self.pick(s,'Passives_extra.json','desc')
        def handler(data,n):
            row=data['entries'][0]
            self.assertNotIn('Stitching',row['source'])
            self.assertIn('缝线',row['protected_values'].values())
            return reply([{'id':row['id'],'text':row['source'].replace('Use ','使用')}])
        from bridge.provider import translate
        result=translate([e],s,self.cache,SimulatedClient(handler),{'interval':0})
        self.assertEqual(result['success'],1);self.assertIn('缝线',e.translation)

    def test_ignored_names_and_original_cache_are_preserved(self):
        self.source('StoryData/S1.json',[{'id':1,'teller':'Dubois'},{'id':2,'teller':'Dubois'}])
        s=self.scan();self.save(self.pick(s,'StoryData/S1.json','teller',1),'杜布瓦')
        second=self.pick(s,'StoryData/S1.json','teller',2);self.cache.ignore(second,True)
        raw=self.cache.path.read_bytes();align_translations(s)
        self.assertEqual(second.status,'ignored');self.assertEqual(raw,self.cache.path.read_bytes())

    def test_latest_manual_name_wins_without_modifying_human_pack(self):
        self.source('StoryData/S1.json',[{'id':1,'teller':'Dubois'},{'id':2,'teller':'Dubois'}])
        s=self.scan();self.save(self.pick(s,'StoryData/S1.json','teller',1),'杜布瓦')
        self.save(self.pick(s,'StoryData/S1.json','teller',2),'手动定名','manual')
        align_translations(s)
        self.assertEqual(self.pick(s,'StoryData/S1.json','teller',1).translation,'手动定名')

    def test_association_foreign_names_are_not_semantically_locked(self):
        self.source('UnitKeyword.json',[{'id':'hana','content':'Hana Association'}])
        s=self.scan();e=self.pick(s,'UnitKeyword.json','content')
        self.save(e,'Hana协会');align_translations(s)
        self.assertNotIn('Hana Association',s.consistency_terms)
        self.assertEqual(locked_terms(s,e),{})

    def test_skill_named_no_does_not_change_normal_dialogue(self):
        self.source('Skills_extra.json',[{'id':88,'name':'No.'}])
        self.source('StoryData/S1.json',[{'id':1,'content':'No.'}])
        s=self.scan();self.save(self.pick(s,'Skills_extra.json'),'拒绝之击')
        e=self.pick(s,'StoryData/S1.json','content');self.save(e,'不行。')
        align_translations(s)
        self.assertEqual(e.translation,'不行。');self.assertEqual(locked_terms(s,e),{})


    def test_enemy_parts_do_not_become_actor_names_in_prose_or_glossary(self):
        self.source('Enemies.json',[{'id':1,'name':'Face'},{'id':2,'name':'Bud'},{'id':3,'name':'Head'}])
        self.source('StoryData/S1.json',[{'id':1,'content':'Face drained pale, Sinclair asked Manager Bud about Head Office.'}])
        s=self.scan()
        for row,zh in [(1,'面部'),(2,'花蕾'),(3,'头部')]:
            self.save(self.pick(s,'Enemies.json',row=row),zh)
        e=self.pick(s,'StoryData/S1.json','content')
        self.save(e,'辛克莱面色惨白，向经理老哥询问总部。')
        align_translations(s)
        self.assertEqual(locked_terms(s,e),{'Sinclair':'辛克莱'})
        self.assertFalse(e.consistency_note)
        from bridge.provider import build_glossary,relevant_glossary
        self.assertEqual(relevant_glossary(build_glossary(s),[e],s),{})

    def test_short_quoted_skill_name_is_not_an_ordinary_dialogue_reference(self):
        self.source('Skills_extra.json',[{'id':1,'name':'No.'}])
        self.source('StoryData/S1.json',[{'id':1,'content':'She said "No."'}])
        s=self.scan();self.save(self.pick(s,'Skills_extra.json'),'拒绝之击')
        e=self.pick(s,'StoryData/S1.json','content');self.save(e,'她说“不行。”')
        align_translations(s)
        self.assertEqual(e.translation,'她说“不行。”')
        self.assertEqual(locked_terms(s,e),{})

    def test_long_enemy_name_can_be_referenced_in_unquoted_hint(self):
        self.source('Enemies.json',[{'id':1,'name':'King of Needleworks'}])
        self.source('BattleResultHint.json',[{'id':1,'content':'Defeat the King of Needleworks.'}])
        s=self.scan();self.save(self.pick(s,'Enemies.json'),'裁缝之王')
        e=self.pick(s,'BattleResultHint.json','content');self.save(e,'击败针线活之王。')
        align_translations(s)
        self.assertEqual(e.translation,'击败裁缝之王。')
        self.assertEqual(locked_terms(s,e),{'King of Needleworks':'裁缝之王'})

    def test_reviewed_alias_does_not_change_unrelated_text(self):
        self.source('ScenarioModelCodes.json',[{'id':1,'name':'Ezra'}])
        self.source('StoryData/S1.json',[{'id':1,'content':'Ezra has arrived.'},{'id':2,'content':'Someone has arrived.'}])
        s=self.scan();self.save(self.pick(s,'ScenarioModelCodes.json'),'以斯拉')
        self.save(self.pick(s,'StoryData/S1.json','content',1),'埃兹拉来了。')
        self.save(self.pick(s,'StoryData/S1.json','content',2),'埃兹拉来了。')
        align_translations(s)
        self.assertEqual(self.pick(s,'StoryData/S1.json','content',1).translation,'以斯拉来了。')
        self.assertEqual(self.pick(s,'StoryData/S1.json','content',2).translation,'埃兹拉来了。')

    def test_longest_reference_avoids_false_subterm_review(self):
        self.source('Enemies.json',[{'id':1,'name':'Crimson God'},{'id':2,'name':'Flesh of the Crimson God [New Form]'}])
        self.source('BattleResultHint.json',[{'id':1,'content':'Defeat Flesh of the Crimson God [New Form].'}])
        s=self.scan();self.save(self.pick(s,'Enemies.json',row=1),'猩红之神')
        self.save(self.pick(s,'Enemies.json',row=2),'猩红之神[新形态]的血肉')
        e=self.pick(s,'BattleResultHint.json','content');self.save(e,'击败猩红之神[新形态]的血肉。')
        align_translations(s)
        self.assertFalse(e.consistency_note)
        self.assertEqual(list(locked_terms(s,e)),['Flesh of the Crimson God [New Form]'])

    def test_multiline_name_components_preserve_layout(self):
        self.source('UnitKeyword.json',[{'id':1,'content':'Le Noir'}])
        self.source('Personalities.json',[{'id':1,'title':'Haute Couture::\nLe Noir\nFootwear Hall'}])
        s=self.scan();self.save(self.pick(s,'UnitKeyword.json','content'),'勒努瓦')
        e=self.pick(s,'Personalities.json','title');self.save(e,'高级定制::\n黑色\n鞋履馆')
        align_translations(s)
        self.assertEqual(e.translation,'高级定制::\n勒努瓦\n鞋履馆')
        validate_translation(e.source,e.translation)

    def test_unknown_body_alias_is_flagged_and_exported_for_review(self):
        self.source('ScenarioModelCodes.json',[{'id':1,'name':'Dubois'}])
        self.source('StoryData/S1.json',[{'id':1,'content':'Dubois has arrived.'}])
        s=self.scan();self.save(self.pick(s,'ScenarioModelCodes.json'),'杜布瓦')
        e=self.pick(s,'StoryData/S1.json','content');self.save(e,'杜博伊斯来了。')
        align_translations(s)
        self.assertIn('Dubois',e.consistency_note)
        self.assertEqual(e.translation,'杜博伊斯来了。')
        from bridge.core import export_report
        directory=export_report(s,self.data)
        report=(directory/'译名一致性.md').read_text(encoding='utf-8')
        self.assertIn('Dubois → 杜布瓦',report)
        self.assertGreater(len(report.splitlines()),10)
        self.assertTrue((directory/'译名对齐清单.csv').is_file())


    def test_new_name_is_translated_before_referencing_body(self):
        self.source('Skills_extra.json',[{'id':1,'name':'Scarlet Stitch'}])
        self.source('Passives_extra.json',[{'id':1,'desc':'Use "Scarlet Stitch".'}])
        s=self.scan();name=self.pick(s,'Skills_extra.json')
        body=self.pick(s,'Passives_extra.json','desc')
        def handler(data,n):
            row=data['entries'][0]
            if n==1:
                self.assertEqual(row['source'],'Scarlet Stitch')
                return reply([{'id':row['id'],'text':'猩红缝针'}])
            self.assertEqual(n,2)
            self.assertIn('猩红缝针',row['protected_values'].values())
            self.assertNotIn('Scarlet Stitch',row['source'])
            return reply([{'id':row['id'],'text':row['source'].replace('Use ','使用')}])
        from bridge.provider import translate
        result=translate([body,name],s,self.cache,SimulatedClient(handler),{'interval':0,'concurrency':2})
        self.assertEqual(result['success'],2)
        self.assertEqual(body.translation,'使用"猩红缝针".')

    def test_names_outside_selection_are_not_added_to_paid_requests(self):
        self.source('Skills_extra.json',[{'id':1,'name':'Scarlet Stitch'}])
        self.source('Passives_extra.json',[{'id':1,'desc':'Use "Scarlet Stitch".'}])
        s=self.scan();name=self.pick(s,'Skills_extra.json')
        body=self.pick(s,'Passives_extra.json','desc')
        def handler(data,n):
            self.assertEqual(len(data['entries']),1)
            self.assertEqual(data['entries'][0]['source'],'Use "Scarlet Stitch".')
            return reply([{'id':data['entries'][0]['id'],'text':'使用“猩红缝针”。'}])
        from bridge.provider import translate
        result=translate([body],s,self.cache,SimulatedClient(handler),{'interval':0})
        self.assertEqual(result['success'],1);self.assertEqual(name.status,'pending')


    def test_human_full_name_is_not_rewritten_from_shorter_component(self):
        self.source('ScenarioModelCodes.json',[{'id':1,'name':'Dubois'},{'id':2,'name':'Captain Dubois'}])
        self.write_zh('ScenarioModelCodes.json',{'dataList':[{'id':1,'name':'杜布瓦'},{'id':2,'name':'迪布瓦上尉'}]})
        self.source('StoryData/S1.json',[{'id':1,'content':'Captain Dubois has arrived.'}])
        s=self.scan();e=self.pick(s,'StoryData/S1.json','content');self.save(e,'迪布瓦上尉来了。')
        align_translations(s)
        self.assertEqual(e.translation,'迪布瓦上尉来了。')
        self.assertEqual(s.consistency_terms['Captain Dubois']['translation'],'迪布瓦上尉')
        self.assertFalse(e.consistency_note)

    def test_reordered_known_quoted_names_keep_their_meanings(self):
        self.source('Skills_extra.json',[{'id':1,'name':'Scarlet Stitch'},{'id':2,'name':'Black Thread'}])
        self.source('Passives_extra.json',[{'id':1,'desc':'After "Scarlet Stitch", use "Black Thread".'}])
        s=self.scan();self.save(self.pick(s,'Skills_extra.json',row=1),'猩红缝针')
        self.save(self.pick(s,'Skills_extra.json',row=2),'黑色丝线')
        e=self.pick(s,'Passives_extra.json','desc');self.save(e,'“黑色丝线”要在“猩红缝针”之后使用。')
        align_translations(s)
        self.assertEqual(e.translation,'“黑色丝线”要在“猩红缝针”之后使用。')

    def test_bracket_qualifier_moved_inside_chinese_name_is_not_a_conflict(self):
        self.source('Enemies.json',[{'id':1,'name':'Flesh of the Crimson God'}])
        self.source('BattleResultHint.json',[{'id':1,'content':'Defeat Flesh of the Crimson God [New Form].'}])
        s=self.scan();self.save(self.pick(s,'Enemies.json'),'猩红之神的血肉')
        e=self.pick(s,'BattleResultHint.json','content');self.save(e,'击败猩红之神[新形态]的血肉。')
        align_translations(s)
        self.assertFalse(e.consistency_note)
        self.assertEqual(e.translation,'击败猩红之神[新形态]的血肉。')
        from bridge.language_knowledge import validate_terms
        validate_terms(s,e,e.translation)


    def test_short_correct_name_does_not_block_a_longer_name_correction(self):
        self.source('ScenarioModelCodes.json',[{'id':1,'name':'Sisyphe'}])
        self.write_zh('ScenarioModelCodes.json',{'dataList':[{'id':1,'name':'西西弗'}]})
        self.source('StoryData/S1.json',[{'id':1,'place':'Grand Magasin Sisyphe'},
                    {'id':2,'content':'Grand Magasin Sisyphe grants the Sisyphe Penalty.'}])
        s=self.scan();self.save(self.pick(s,'StoryData/S1.json','place'),'西西弗百货商店')
        e=self.pick(s,'StoryData/S1.json','content');self.save(e,'西西弗大百货授予西西弗之刑。')
        align_translations(s)
        self.assertEqual(e.translation,'西西弗百货商店授予西西弗之刑。')
        self.assertFalse(e.consistency_note)


    def test_repeated_pending_names_pay_for_one_reference_identity(self):
        self.source('ScenarioModelCodes.json',[{'id':1,'name':'Dubois'},{'id':2,'name':'Dubois'}],
                    kr=[{'id':1,'name':'뒤부아'},{'id':2,'name':'뒤부아'}])
        self.source('StoryData/S1.json',[{'id':1,'content':'Dubois arrived.'}])
        s=self.scan()
        from bridge.consistency import name_dependencies
        names=name_dependencies(s.entries,s)
        self.assertEqual(len(names),1)
        self.save(names[0],'杜布瓦')
        align_translations(s)
        self.assertTrue(all(e.status=='cached' for e in s.entries if e.source=='Dubois'))


    def test_partial_reference_name_joins_unique_complete_signature(self):
        self.source('ScenarioModelCodes_auto.json',[{'id':1,'name':'Dorian'}],kr=[{'id':1,'name':'도리안'}])
        self.source('Enemies_new.json',[{'id':2,'name':'Dorian'}],kr=[{'id':2,'name':'도리안'}])
        self.write_source('Enemies_new.json',{'dataList':[{'id':2,'name':'ドリアン'}]},lang='jp')
        self.source('StoryData/S1.json',[{'id':1,'content':'Dorian arrived.'}])
        s=self.scan();first=self.pick(s,'ScenarioModelCodes_auto.json');second=self.pick(s,'Enemies_new.json')
        self.save(first,'多利安');self.save(second,'道林')
        align_translations(s)
        self.assertEqual(first.translation,second.translation)
        self.assertIn('Dorian',s.consistency_terms)
        self.assertEqual(locked_terms(s,self.pick(s,'StoryData/S1.json','content')),{'Dorian':second.translation})

    def test_partial_reference_does_not_bridge_conflicting_supersets(self):
        self.source('ScenarioModelCodes_auto.json',[{'id':1,'name':'Dorian'}],kr=[{'id':1,'name':'도리안'}])
        self.source('Enemies_new.json',[{'id':2,'name':'Dorian'},{'id':3,'name':'Dorian'}],kr=[{'id':2,'name':'도리안'},{'id':3,'name':'도리안'}])
        self.write_source('Enemies_new.json',{'dataList':[{'id':2,'name':'ドリアン甲'},{'id':3,'name':'ドリアン乙'}]},lang='jp')
        s=self.scan()
        self.save(self.pick(s,'ScenarioModelCodes_auto.json'),'待确认人名')
        self.save(self.pick(s,'Enemies_new.json',row=2),'多利安甲')
        self.save(self.pick(s,'Enemies_new.json',row=3),'多利安乙')
        align_translations(s)
        self.assertNotIn('Dorian',s.consistency_terms)
        self.assertEqual(self.pick(s,'ScenarioModelCodes_auto.json').translation,'待确认人名')


    def test_exploration_location_label_is_reused_in_prose(self):
        file='RPGSystem/rpg-loc-location-test.json'
        self.source(file,[{'key':'L1','text':'Maison du Noir'}],kr=[{'key':'L1','text':'르누아르 메종'}])
        self.source('StoryData/S1.json',[{'id':1,'content':'Return to Maison du Noir.'}])
        s=self.scan();place=next(e for e in s.entries if e.file==file)
        self.save(place,'黑之宅邸');align_translations(s)
        body=self.pick(s,'StoryData/S1.json','content')
        self.assertEqual(locked_terms(s,body),{'Maison du Noir':'黑之宅邸'})

class UnquotedStatusReferenceTests(unittest.TestCase):
    def test_multiword_status_in_mechanics_but_not_ordinary_dialogue(self):
        from types import SimpleNamespace
        from bridge.consistency import _reference_allowed
        term={'role':'status'}
        combat=SimpleNamespace(source='Convert into Awakened Armor next turn.',field='desc',file='BattleKeywords.json')
        self.assertTrue(_reference_allowed(combat,'Awakened Armor',term))
        story=SimpleNamespace(source='I had Sweet Dreams.',field='content',file='StoryData/test.json')
        self.assertFalse(_reference_allowed(story,'Sweet Dreams',term))
        self.assertFalse(_reference_allowed(combat,'Binding',term))

    def test_shorter_status_does_not_capture_inside_core_concept(self):
        from types import SimpleNamespace
        from bridge.consistency import _references,_term_index
        terms={'Power Up':{'role':'status'}}
        e=SimpleNamespace(source='Gain Attack Power Up.',field='desc',file='Skills_test.json')
        self.assertEqual(_references(e,terms,_term_index(terms)),[])
        e.source='Gain Attack Power Up and Power Up.'
        self.assertEqual(_references(e,terms,_term_index(terms)),['Power Up'])
