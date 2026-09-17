import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from test_bridge import Fixture
from test_validation_retries import SimulatedClient,reply
from bridge.core import Entry,protect,restore,payload,export_report,BridgeError
from bridge.lexicon import term_locks,repair_known_aliases,PROFILES
from bridge.language_knowledge import knowledge,speaker,acronyms,validate_terms
from bridge.consistency import locked_terms,align_translations
from bridge.provider import build_glossary,relevant_glossary,translate

def entry(source,file='Skills_test.json',field='desc',context=''):
    return Entry('test',file,(),(),field,source,None,'missing',True,context=context)

class VocabularyTests(unittest.TestCase):
    def test_coin_mechanic_cannot_inherit_gift_currency_sense(self):
        combat=entry('Convert Coins into Unbreakable Coins. Coin Power +2')
        self.assertEqual(term_locks(combat),{'Unbreakable Coins':'不可摧毁的硬币','Coin Power':'硬币威力','Coins':'硬币'})
        for e in (entry('Coin','EGOgift_a1c8p2.json','name'),
                  entry('Coins','StoryDungeonUI-a1c8p2.json','content'),
                  entry('She paid copper coins.','StoryData/new.json','content')):
            self.assertEqual(term_locks(e),{})
        self.assertEqual(repair_known_aliases(combat,'将铜钱转化为不可摧毁的硬币。铜钱威力+2'),
                         '将硬币转化为不可摧毁的硬币。硬币威力+2')

    def test_count_as_is_not_locked_to_status_stacks(self):
        e=entry('Gain [Breath] Count. This does not count as damage.')
        locks=term_locks(e)
        self.assertNotIn('count',locks)
        self.assertNotIn('Count',locks)
        self.assertEqual(term_locks(entry('Count','BattleKeywords.json','name')),{'Count':'层数'})

    def test_count_unit_can_precede_status_tag_in_chinese(self):
        e=entry('Gain 3 [Breath] Count.')
        masked,tokens=protect(e.source,numbers=True,terms=term_locks(e))
        text=restore('获得⟦P0000⟧层⟦P0001⟧。',tokens)
        self.assertEqual(text,'获得3层[Breath]。')

    def test_lowercase_golden_bough_is_recognized(self):
        e=entry('Bring the golden bough.','StoryData/new.json','content')
        self.assertEqual(term_locks(e),{'golden bough':'金枝'})
        self.assertEqual(repair_known_aliases(e,'带上黄金枝。'),'带上金枝。')

    def test_gold_bough_alias_corrected_only_with_source_evidence(self):
        e=entry('Bring the Golden Boughs.','StoryData/new.json','content')
        self.assertEqual(repair_known_aliases(e,'带上黄金枝。'),'带上金枝。')
        other=entry('The gold-colored branches gleamed.','StoryData/new.json','content')
        self.assertEqual(repair_known_aliases(other,'黄金枝闪着光。'),'黄金枝闪着光。')

    def test_thread_and_identity_have_system_senses_only(self):
        self.assertEqual(term_locks(entry('Thread','Items.json','name')),{'Thread':'纺锤'})
        e=entry('Thread the needle. Hide your Identity.','StoryData/new.json','content')
        self.assertEqual(term_locks(e),{})
        self.assertEqual(term_locks(entry('Identity','MainUIText.json','content')),{'Identity':'人格'})

    def test_anatomy_and_attribute_words_do_not_rewrite_dialogue(self):
        e=entry('Her Wings trembled with Pride and Wrath.','StoryData/new.json','content')
        self.assertEqual(term_locks(e),{})
        self.assertEqual(term_locks(entry('Slash','Skills_test.json','name')),{})

    def test_word_boundaries_case_and_longest_match(self):
        e=entry('Coincidence! COIN power +3. [CoinCode] <b>coins</b>')
        locks=term_locks(e)
        self.assertEqual(locks,{'COIN power':'硬币威力','coins':'硬币'})
        masked,tokens=protect(e.source,numbers=True,terms=locks)
        self.assertEqual(tokens,['硬币威力','+3','[CoinCode]','<b>','硬币','</b>'])
        text=restore(masked.replace('Coincidence!','巧合！'),tokens)
        self.assertIn('[CoinCode]',text)
        self.assertNotIn('铜钱',text)

    def test_alias_repair_does_not_touch_tags_or_wrong_numbers(self):
        e=entry('<link="铜钱">Coins</link> +2')
        self.assertEqual(repair_known_aliases(e,'<link="铜钱">铜钱</link> +2'),
                         '<link="铜钱">硬币</link> +2')
        self.assertEqual(repair_known_aliases(e,'<link="铜钱">铜钱</link> +9'),
                         '<link="铜钱">铜钱</link> +9')

    def test_actor_is_not_inferred_from_someone_mentioned(self):
        e=entry('Ryoshu, listen!','StoryData/new.json','content',json.dumps({'model':'싱클레어'}))
        self.assertEqual(speaker(e),'sinclair')
        e.context='{}';self.assertIsNone(speaker(e))
        e.context=json.dumps({'model':'료슈_frown'});self.assertEqual(speaker(e),'ryoshu')
        e.context=json.dumps({'model':'료슈','speaker':'Sinclair'});self.assertIsNone(speaker(e))

    def test_exclusive_voice_file_and_neutral_skill_description(self):
        self.assertEqual(speaker(entry('A voice.','PersonalityVoiceDlg/Voice_Ryoshu_Test_10401.json','dlg')),'ryoshu')
        self.assertEqual(speaker(entry('A voice.','EGOVoiceDig/Voice_EGO_Charon_14.json','dlg')),'charon')
        self.assertIsNone(speaker(entry('Attack.','Skills_Ryoshu.json','desc',json.dumps({'model':'료슈'}))))
        self.assertEqual(len(PROFILES),15)

    def test_engine_and_ego_codes_not_treated_as_ryoshu_shortforms(self):
        self.assertEqual(acronyms('E.G.O. LCB [ABC] B.A.R.F. BG HAH'),['B.A.R.F.','BG'])

class LanguageKnowledgeTests(Fixture):
    def seed_dialogue(self):
        file='StoryData/old.json'
        source={'dataList':[{'id':1,'model':'료슈','content':'Hey, B.G. Light it.'},
                            {'id':2,'model':'싱클레어','content':'She means bug guy.'},
                            {'id':3,'model':'파우스트','content':'Faust knows.'}]}
        human={'dataList':[{'id':1,'model':'료슈','content':'喂，虫·男。点火。'},
                           {'id':2,'model':'싱클레어','content':'她说的是虫男。'},
                           {'id':3,'model':'파우스트','content':'浮士德知道。'}]}
        self.write_source(file,source);self.write_zh(file,human)
        return source,human

    def target(self,text='B.G., come here.',who='료슈'):
        file='StoryData/new.json'
        self.write_source(file,{'dataList':[{'id':1,'model':who,'content':text},
            {'id':2,'model':'싱클레어','content':'She means bug guy.'}]})
        s=self.scan();return s,next(e for e in s.entries if e.file==file and e.field=='content')

    def test_local_human_examples_and_adjacent_explanation_are_sent(self):
        self.seed_dialogue();s,e=self.target()
        data=knowledge(s).guidance(e)
        self.assertEqual(data['speaker_profile']['name'],'良秀')
        self.assertEqual(data['abbreviations'][0]['candidates'],['虫·男'])
        self.assertEqual(data['dialogue_context'][0]['speaker'],'辛克莱')
        self.assertIn('bug guy',data['dialogue_context'][0]['source'])
        self.assertNotIn('B.G.',knowledge(s).locks(e))

    def test_identical_line_reuses_but_new_context_and_other_speaker_do_not(self):
        self.seed_dialogue()
        s,e=self.target('Hey, B.G. Light it.')
        self.assertEqual(locked_terms(s,e).get('B.G.'),'虫·男')
        s,e=self.target('Hey, B.G. Light it.','싱클레어')
        self.assertNotIn('B.G.',locked_terms(s,e))

    def test_reviewed_acronym_quote_applies_to_sinclair_only_in_its_scene(self):
        from bridge.scoped_review import context_hash
        s,e=self.target('She would call it D.R.A.B.','싱클레어')
        bank=knowledge(s)
        bank.reviewed_abbreviations[e.uid]=dict(
            source_hash=e.cache_hash,context_hash=context_hash(e,bank.neighbors(e)),
            evidence='The next line explicitly explains the four initials.',
            locks={'D.R.A.B.':'乏·善·可·陈'})
        self.assertEqual(bank.locks(e).get('D.R.A.B.'),'乏·善·可·陈')
        s.sources[e.file.casefold()]['dataList'][1]['content']='A different explanation.'
        self.assertNotIn('D.R.A.B.',bank.locks(e))

    def test_conflicting_local_acronym_candidates_stay_separate(self):
        source,human=self.seed_dialogue()
        source['dataList'].append({'id':4,'model':'료슈','content':'B.G. The gate.'})
        human['dataList'].append({'id':4,'model':'료슈','content':'大·门。那道门。'})
        self.write_source('StoryData/old.json',source);self.write_zh('StoryData/old.json',human)
        s,e=self.target()
        self.assertEqual(knowledge(s).guidance(e)['abbreviations'][0]['candidates'],['大·门','虫·男'])
        self.assertNotIn('B.G.',locked_terms(s,e))

    def test_ai_cache_is_never_learned_as_a_human_acronym(self):
        s,e=self.target()
        self.cache.put(e,'蠢·货，过来。','some-ai')
        s=self.scan()
        self.assertEqual(dict(knowledge(s).shortforms),{})
        self.assertTrue(next(e.consistency_note for e in s.entries if e.source=='B.G., come here.'))

    def test_new_chinese_acronym_is_still_flagged_for_semantic_review(self):
        self.seed_dialogue();s,e=self.target()
        self.cache.put(e,'虫·男，过来。','fake')
        align_translations(s)
        self.assertIn('良秀缩写待核对',e.consistency_note)

    def test_pure_unknown_acronym_does_not_spend_ten_requests_in_a_loop(self):
        s,e=self.target('Z.X.Q.')
        c=SimulatedClient(lambda d,n:self.fail('No paid request should be attempted'))
        with patch('bridge.provider.wait_for_retry'):
            stats=translate([e],s,self.cache,c,{'retries':10})
        self.assertEqual(stats,{'success':0,'failed':1,'total':1})
        self.assertIn('手动确认',e.error)
        self.assertEqual(c.calls,[])

    def test_current_glossary_cannot_promote_currency_or_wings_to_global_terms(self):
        self.write_source('EGOgift_test.json',{'dataList':[{'id':1,'name':'Coin'}]})
        self.write_zh('EGOgift_test.json',{'dataList':[{'id':1,'name':'铜钱'}]})
        self.write_source('Enemies_test.json',{'dataList':[{'id':1,'name':'Wings'}]})
        self.write_zh('Enemies_test.json',{'dataList':[{'id':1,'name':'翅膀'}]})
        s,e=self.target('The Wings flipped a Coin.')
        glossary=build_glossary(s)
        self.assertNotIn('Coin',glossary)
        self.assertNotIn('Wings',glossary)
        self.assertNotIn('Coin',relevant_glossary({'Coin':'铜钱'},[e],s))

    def test_unlisted_gift_homonym_stays_in_its_origin_resource(self):
        self.write_source('EGOgift_test.json',{'dataList':[{'id':1,'name':'Tomorrow'},
            {'id':2,'desc':'Use Tomorrow.'}]})
        self.write_zh('EGOgift_test.json',{'dataList':[{'id':1,'name':'明日之厄'}]})
        s,e=self.target('Tomorrow, we leave.','단테')
        glossary=build_glossary(s)
        self.assertEqual(glossary['Tomorrow'],'明日之厄')
        self.assertNotIn('Tomorrow',relevant_glossary(glossary,[e],s))
        gift=next(e for e in s.entries if e.file=='EGOgift_test.json')
        self.assertEqual(relevant_glossary(glossary,[gift],s)['Tomorrow'],'明日之厄')
        manual=build_glossary(s,{'Tomorrow':'个人专名'})
        self.assertEqual(relevant_glossary(manual,[e],s)['Tomorrow'],'个人专名')

    def test_corrections_are_in_memory_and_pack_only_not_cache_or_human(self):
        file='Skills_terms.json'
        self.write_source(file,{'dataList':[{'id':2,'desc':'Coin Power +2; find a Golden Bough.'}]})
        s=self.scan();e=next(e for e in s.entries if e.file==file)
        old='铜钱威力+2；找到黄金枝。';self.cache.put(e,old,'fake')
        before={p:p.read_bytes() for p in self.game.rglob('*') if p.is_file()}
        s=self.scan();e=next(e for e in s.entries if e.file==file)
        self.assertEqual(e.translation,'硬币威力+2；找到金枝。')
        with self.cache.connect() as con:
            self.assertEqual(con.execute('select translated from translations where uid=?',(e.uid,)).fetchone()[0],old)
        files,_=payload(s)
        self.assertIn('金枝',files[file].decode('utf-8'))
        self.assertEqual(before,{p:p.read_bytes() for p in before})

    def test_manual_wording_is_flagged_but_not_overwritten(self):
        self.write_source('Skills_terms.json',{'dataList':[{'id':2,'desc':'Coin Power +2'}]})
        s=self.scan();e=next(e for e in s.entries if e.file=='Skills_terms.json')
        self.cache.put(e,'铜钱威力+2','manual')
        s=self.scan();e=next(e for e in s.entries if e.file=='Skills_terms.json')
        self.assertEqual(e.translation,'铜钱威力+2')
        self.assertIn('术语待核对',e.consistency_note)

    def test_custom_reviewed_glossary_overrides_bundle_within_its_sense(self):
        self.write(self.data/'glossary.json',{'Golden Bough':'自定金枝'})
        s,e=self.target('Bring the Golden Bough.','단테')
        self.assertEqual(locked_terms(s,e)['Golden Bough'],'自定金枝')

    def test_terms_and_character_context_reach_provider_and_markers_retry(self):
        self.seed_dialogue();s,e=self.target('B.G., bring the Golden Bough.')
        def answer(data,n):
            row=data['entries'][0]
            self.assertEqual(row['terminology']['Golden Bough'],'金枝')
            self.assertEqual(row['speaker_profile']['name'],'良秀')
            text='B.G.，拿来'+row['source'].split('bring the ')[1]
            if n==1:text=text.replace('⟦P0000⟧','黄金枝')
            return reply([{'id':row['id'],'text':text}])
        c=SimulatedClient(answer)
        with patch('bridge.provider.wait_for_retry'):
            stats=translate([e],s,self.cache,c,{'retries':10,'interval':0})
        self.assertEqual(stats['success'],1)
        self.assertEqual(len(c.calls),2)
        self.assertIn('金枝',e.translation)
        self.assertIn('良秀缩写待核对',e.consistency_note)

    def test_complete_human_entity_name_shields_a_generic_component(self):
        self.write_source('ScenarioModelCodes.json',{'dataList':[{'id':1,'name':'The Golden Bough'}]})
        self.write_zh('ScenarioModelCodes.json',{'dataList':[{'id':1,'name':'金色之枝'}]})
        s,e=self.target('The Golden Bough arrived.','단테')
        self.assertEqual(locked_terms(s,e),{'The Golden Bough':'金色之枝'})
        validate_terms(s,e,'金色之枝来了。')
        s,e=self.target('The Golden Bough found a Golden Bough.','단테')
        self.assertEqual(locked_terms(s,e),{'The Golden Bough':'金色之枝','Golden Bough':'金枝'})

    def test_terminology_checker_catches_direct_wrong_value(self):
        s,e=self.target('The Golden Bough.','단테')
        with self.assertRaisesRegex(BridgeError,'术语校验'):
            validate_terms(s,e,'黄金枝。')

    def test_exports_are_readable_and_do_not_overwrite_personal_dictionary(self):
        self.seed_dialogue();s,e=self.target()
        self.write(self.data/'glossary.json',{'One':'一'})
        before=(self.data/'glossary.json').read_bytes()
        out=export_report(s,self.data)
        text=(out/'边狱巴士词汇表.md').read_text(encoding='utf-8')
        self.assertIn('维吉里乌斯',text)
        self.assertTrue((out/'边狱巴士词汇表.csv').exists())
        self.assertIn('B.G.',json.loads((out/'良秀缩写候选.json').read_text(encoding='utf-8')))
        self.assertEqual(before,(self.data/'glossary.json').read_bytes())
