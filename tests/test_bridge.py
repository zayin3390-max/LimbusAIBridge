import copy
import json
import os
import pathlib
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from bridge.core import *
from bridge.provider import *
from bridge import settings

class Fixture(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='limbus-bridge-test-')
        self.root=pathlib.Path(self.temp.name)
        self.game=self.root/'game'; self.game.mkdir()
        (self.game/'LimbusCompany.exe').write_bytes(b'fixture')
        self.loc=self.game/'LimbusCompany_Data/Assets/Resources_moved/Localize'
        self.zh=self.game/'LimbusCompany_Data/Lang/LLC_zh-CN'
        (self.loc/'en').mkdir(parents=True); (self.loc/'kr').mkdir()
        (self.zh/'Font/Context').mkdir(parents=True)
        (self.zh/'Font/Context/ChineseFont.ttf').write_bytes(b'test font')
        (self.zh.parent/'config.json').write_bytes(b'original config bytes')
        self.data=self.root/'app'; self.cache=Cache(self.data)
        self.write_source('Skills_personality-01.json',{'dataList':[{'id':10101,'levelList':[{'level':1,'name':'Old skill','desc':'Gain 2 [Binding].'},{'level':2,'name':'New skill','desc':'Gain 3 [Binding].'}]}]})
        self.write_zh('Skills_personality-01.json',{'dataList':[{'id':10101,'levelList':[{'level':1,'name':'人工旧技能','desc':'获得2层[Binding]。'}]}]})
        self.write_source('GachaTitle.json',{'dataList':[{'id':'pool_new','content':'New Target Extraction'}]})
    def tearDown(self):
        target=pathlib.Path(self.temp.name).resolve()
        self.assertEqual(target.parent,pathlib.Path(tempfile.gettempdir()).resolve())
        self.assertTrue(target.name.startswith('limbus-bridge-test-'))
        self.temp.cleanup()
    def write(self,path,data):
        path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(dumps(data))
    def write_source(self,name,data,lang='en'):
        p=pathlib.Path(name); self.write(self.loc/lang/p.with_name(lang.upper()+'_'+p.name),data)
    def write_zh(self,name,data): self.write(self.zh/name,data)
    def scan(self): return scan_game(self.game,cache=self.cache)

class CoreTests(Fixture):
    def test_stable_ids_and_level_insertion(self):
        s=self.scan(); self.assertEqual(len(s.entries),3)
        old=copy.deepcopy(s.sources['skills_personality-01.json'])
        old['dataList'][0]['levelList'].reverse()
        self.write_source('Skills_personality-01.json',old)
        s2=self.scan()
        self.assertEqual({e.uid for e in s.entries},{e.uid for e in s2.entries})

    def test_independent_pack_human_priority_and_preservation(self):
        before={str(p):digest(p.read_bytes()) for p in self.game.rglob('*') if p.is_file()}
        s=self.scan()
        for e in s.entries:
            self.cache.put(e, {'New skill':'新增技能','Gain 3 [Binding].':'获得3层[Binding]。','New Target Extraction':'新目标抽取'}[e.source],'mock')
        result=install_pack(s,self.data,check_running=False)
        dest=pathlib.Path(result['output'])
        merged=read_json(dest/'Skills_personality-01.json')
        levels=merged['dataList'][0]['levelList']
        self.assertEqual(levels[0]['name'],'人工旧技能')
        self.assertEqual(levels[1]['name'],'新增技能')
        for p,expected in before.items(): self.assertEqual(digest(pathlib.Path(p).read_bytes()),expected,p)
        self.write_zh('GachaTitle.json',{'dataList':[{'id':'pool_new','content':'人工新卡池'}]})
        s2=self.scan(); install_pack(s2,self.data,check_running=False)
        self.assertEqual(read_json(dest/'GachaTitle.json')['dataList'][0]['content'],'人工新卡池')
        self.assertTrue(list((self.data/'history').rglob('GachaTitle.json')))
        with self.cache.connect() as con: self.assertEqual(con.execute('SELECT COUNT(*) FROM translations').fetchone()[0],3)

    def test_stale_source_and_reference_invalidate(self):
        s=self.scan(); entry=next(e for e in s.entries if e.file=='GachaTitle.json')
        self.cache.put(entry,'新目标抽取','mock')
        self.write_source('GachaTitle.json',{'dataList':[{'id':'pool_new','content':'A Changed Pool'}]})
        with self.assertRaises(BridgeError): install_pack(s,self.data,check_running=False)
        s2=self.scan(); self.assertEqual(next(e for e in s2.entries if e.file=='GachaTitle.json').status,'pending')
        self.cache.put(next(e for e in s2.entries if e.file=='GachaTitle.json'),'变动卡池','mock')
        self.write_source('GachaTitle.json',{'dataList':[{'id':'pool_new','content':'새 추출'}]},'kr')
        self.assertEqual(next(e for e in self.scan().entries if e.file=='GachaTitle.json').status,'pending')

    def test_existing_same_name_directory_never_overwritten(self):
        target=self.zh.parent/PACK_NAME; target.mkdir(); original=target/'important.txt'; original.write_text('keep')
        with self.assertRaises(BridgeError): install_pack(self.scan(),self.data,check_running=False)
        self.assertEqual(original.read_text(),'keep'); self.assertEqual(len(list(target.iterdir())),1)

    def test_user_edit_in_owned_pack_never_overwritten(self):
        s=self.scan(); install_pack(s,self.data,check_running=False)
        target=self.zh.parent/PACK_NAME/'Skills_personality-01.json'; target.write_text('user change')
        with self.assertRaises(BridgeError): install_pack(s,self.data,check_running=False)
        self.assertEqual(target.read_text(),'user change')

    def test_engine_fields_are_not_candidates(self):
        self.write_source('StoryData/P10101.json',{'dataList':[{'id':0,'model':'홍루','imgStr':'image_name','usage':'USE_THIS','name':'My Name','content':'Hello, Manager.'}]})
        s=self.scan(); entries=[e for e in s.entries if e.file.startswith('StoryData')]
        self.assertEqual({e.field for e in entries},{'name','content'})
        self.assertTrue(all(e.category=='人格' for e in entries))

    def test_identical_names_and_blank_need_review(self):
        self.write_zh('GachaTitle.json',{'dataList':[{'id':'pool_new','content':'New Target Extraction'}]})
        e=next(e for e in self.scan().entries if e.file=='GachaTitle.json')
        self.assertFalse(e.recommended); self.assertEqual(e.reason,'same')
        self.write_zh('GachaTitle.json',{'dataList':[{'id':'pool_new','content':''}]})
        e=next(e for e in self.scan().entries if e.file=='GachaTitle.json')
        self.assertFalse(e.recommended); self.assertEqual(e.reason,'empty')

    def test_empty_story_row_and_disambiguated_ids(self):
        source={'dataList':[{'id':4,'model':'A','content':'Hello A'},{'id':4,'model':'B','content':'Hello B'},{}]}
        base={'dataList':[{'id':4,'model':'B','content':'人工乙'},{'id':4,'model':'A','content':'人工甲'},{}]}
        self.write_source('StoryData/S001.json',source); self.write_zh('StoryData/S001.json',base)
        s=self.scan(); self.assertFalse([e for e in s.entries if e.file=='StoryData/S001.json'])
        source['dataList'].insert(2,{'id':5,'content':'New line'})
        self.write_source('StoryData/S001.json',source)
        s=self.scan(); e=next(e for e in s.entries if e.file=='StoryData/S001.json'); self.cache.put(e,'新增台词','mock')
        install_pack(s,self.data,check_running=False)
        rows=read_json(self.zh.parent/PACK_NAME/'StoryData/S001.json')['dataList']
        self.assertEqual([v['content'] for v in rows if v.get('id')==4],['人工乙','人工甲'])
        self.assertEqual(next(v['content'] for v in rows if v.get('id')==5),'新增台词')

    def test_unresolvable_duplicate_skipped_not_guessed(self):
        self.write_source('StoryData/S1.json',{'dataList':[{'id':0,'content':'a'},{'id':0,'content':'b'}]})
        s=self.scan(); self.assertTrue(s.warnings); self.assertFalse([e for e in s.entries if e.file=='StoryData/S1.json'])

    def test_newly_seen_baseline(self):
        s=self.scan(); self.cache.observe(s); self.assertFalse(any(e.newly_seen for e in s.entries))
        self.write_source('GachaTitle.json',{'dataList':[{'id':'pool_new','content':'New Target Extraction'},{'id':'pool_2','content':'Another Pool'}]})
        s=self.scan(); self.cache.observe(s)
        self.assertEqual([e.source for e in s.entries if e.newly_seen],['Another Pool'])
        s=self.scan(); self.cache.observe(s); self.assertEqual(len([e for e in s.entries if e.newly_seen]),1)

    def test_rollback_on_io_failure_preserves_preexisting(self):
        s=self.scan(); install_pack(s,self.data,check_running=False)
        target=self.zh.parent/PACK_NAME
        before={p.relative_to(target).as_posix():p.read_bytes() for p in target.rglob('*') if p.is_file()}
        e=next(e for e in s.entries if e.file=='GachaTitle.json'); self.cache.put(e,'新卡池','mock')
        import bridge.core as module
        real=module.atomic_write; failed=False
        def flaky(path,raw):
            nonlocal failed
            if pathlib.Path(path).name==MARKER and not failed:
                failed=True; raise OSError('simulated full disk')
            return real(path,raw)
        with patch('bridge.core.atomic_write',side_effect=flaky):
            with self.assertRaises(OSError): install_pack(s,self.data,check_running=False)
        after={p.relative_to(target).as_posix():p.read_bytes() for p in target.rglob('*') if p.is_file()}
        self.assertEqual(before,after)

    def test_game_running_blocks_before_writes(self):
        with patch('bridge.core.game_running',return_value=True):
            with self.assertRaises(BridgeError): install_pack(self.scan(),self.data)
        self.assertFalse((self.zh.parent/PACK_NAME).exists())

    def test_existing_omissions_and_untranslated_rows_stay_untouched(self):
        self.write_source('StoryData/P10101.json',{'dataList':[{'id':1,'model':'A','title':'Omitted title','content':'Old line'},{'id':2,'content':'New line'},{'id':3,'content':'Another untranslated line'}]})
        self.write_zh('StoryData/P10101.json',{'dataList':[{'id':1,'content':'原有译文'}]})
        s=self.scan(); e=next(e for e in s.entries if e.source=='New line'); self.cache.put(e,'新台词','mock')
        install_pack(s,self.data,check_running=False)
        rows=read_json(self.zh.parent/PACK_NAME/'StoryData/P10101.json')['dataList']
        self.assertEqual(rows,[{'id':1,'content':'原有译文'},{'id':2,'content':'新台词'}])

    def test_five_new_content_types_and_keyword_dependencies(self):
        files={'Personalities.json':{'dataList':[{'id':10117,'name':'New Identity'}]},
               'Egos.json':{'dataList':[{'id':201017,'name':'New EGO'}]},
               'StoryData/S1001A.json':{'dataList':[{'id':0,'content':'New chapter'}]},
               'Skills_Enemy-a1c10.json':{'dataList':[{'id':80101,'levelList':[{'level':1,'desc':'Gain 2 [NewBuff].'}]}]},
               'Bufs.json':{'dataList':[{'id':'NewBuff','name':'New buff','desc':'Power +2'}]}}
        first=self.scan(); self.cache.observe(first)
        for name,data in files.items(): self.write_source(name,data)
        s=self.scan(); self.cache.observe(s)
        new=[e for e in s.entries if e.newly_seen]
        self.assertEqual({e.category for e in new},{'人格','E.G.O','主线剧情','敌方','关联术语'})
        selected=[e for e in new if e.category=='敌方']
        expanded=include_dependencies(selected,s)
        self.assertEqual({e.file for e in expanded},{'Skills_Enemy-a1c10.json','Bufs.json'})

    def test_source_file_unsafe_rows_retained_when_absent_in_human_pack(self):
        data={'dataList':[{'id':0,'content':'Duplicate A'},{'id':0,'content':'Duplicate B'},{'id':1,'content':'New line'}]}
        self.write_source('StoryData/S2.json',data)
        s=self.scan(); e=next(e for e in s.entries if e.source=='New line'); self.cache.put(e,'新台词','mock')
        install_pack(s,self.data,check_running=False)
        actual=read_json(self.zh.parent/PACK_NAME/'StoryData/S2.json')
        self.assertEqual(actual['dataList'][:2],data['dataList'][:2]); self.assertEqual(actual['dataList'][2]['content'],'新台词')

class FormatTests(unittest.TestCase):
    def test_protect_restore(self):
        source='<color=#f00>Gain 2 [Binding]</color>\nDeal {0} damage to %{2} {1}/%.'
        masked,tokens=protect(source)
        output=masked.replace('Gain','获得').replace('Deal','造成').replace(' damage to ','伤害至')
        restored=restore(output,tokens); validate_translation(source,restored)
        self.assertIn('[Binding]',restored)
        with self.assertRaises(BridgeError): restore(output.replace('⟦P0000⟧',''),tokens)
        with self.assertRaises(BridgeError): validate_translation(source,restored.replace('2','3',1))
    def test_dante_dialogue_not_masked(self):
        masked,tokens=protect('<We must go.> [On Hit] Gain [Binding].')
        self.assertIn('<We must go.>',masked); self.assertIn('[On Hit]',masked)
        self.assertEqual(tokens,['[Binding]'])
    def test_korean_fallback_is_untranslated(self):
        self.assertEqual(classify('새로운 기술','새로운 기술',True),'same')
        self.assertEqual(classify('E.G.O','E.G.O',True),'same')
    def test_parser_rejects_duplicate_or_extra_ids(self):
        for text in ['{"translations":[{"id":"1","text":"甲"},{"id":"1","text":"乙"}]}','{"translations":[]}','{"translations":[{"id":"2","text":"乙"}]}']:
            with self.assertRaises(APIError): parse_response(text,{'1'})
        self.assertEqual(parse_response('```json\n{"translations":[{"id":"1","text":"甲"}]}\n```',{'1'}),{'1':'甲'})
    def test_endpoints_and_safety(self):
        self.assertEqual(endpoint('https://example.com'),'https://example.com/v1/chat/completions')
        self.assertEqual(endpoint('http://127.0.0.1:1234/v1'),'http://127.0.0.1:1234/v1/chat/completions')
        with self.assertRaises(BridgeError): endpoint('http://example.com/v1')
        with self.assertRaises(BridgeError): safe_child(pathlib.Path.cwd(),'../escape')
        with self.assertRaises(BridgeError): safe_child(pathlib.Path.cwd(),'a:C')
    def test_categories(self):
        categories={'StoryData/P10116.json':'人格','StoryData/S1001B.json':'主线剧情','Skills_personality-01.json':'人格','Skills_Ego_Personality-01.json':'E.G.O','Egos.json':'E.G.O','Skills_Abnormality-a1c10.json':'敌方','AbnormalityGuides-a1c10.json':'敌方','GachaTitle.json':'卡池'}
        for name,wanted in categories.items():
            e=Entry('id',name,(),(),'content','new',None,'missing',True)
            self.assertEqual(e.category,wanted,name)
    @unittest.skipUnless(os.name=='nt','DPAPI requires Windows')
    def test_dpapi_roundtrip(self):
        raw=b'not-a-real-key'; encrypted=settings.crypt(raw)
        self.assertNotIn(raw,encrypted); self.assertEqual(settings.crypt(encrypted,True),raw)

class MockAPITests(Fixture):
    def test_http_batch_roundtrip_and_resume(self):
        requests=[]
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*_): pass
            def do_POST(self):
                body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                requests.append(body)
                data=json.loads(body['messages'][-1]['content'])
                rows=[]
                for e in data['entries']:
                    text=e['source'].replace('New skill','新增技能').replace('Gain ','获得').replace('New Target Extraction','新目标抽取')
                    rows.append({'id':e['id'],'text':text})
                response={'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'translations':rows},ensure_ascii=False)}}]}
                raw=json.dumps(response,ensure_ascii=False).encode('utf8')
                self.send_response(200); self.send_header('Content-Type','application/json'); self.end_headers(); self.wfile.write(raw)
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        worker=threading.Thread(target=server.serve_forever,daemon=True); worker.start()
        try:
            conf={'api_base':f'http://127.0.0.1:{server.server_port}/v1','model':'mock','retries':0,'interval':0}
            client=Client(conf,'fixture-key'); client.opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
            s=self.scan(); result=translate(s.entries,s,self.cache,client,conf)
            self.assertEqual(result['success'],3); self.assertEqual(result['failed'],0)
            s2=self.scan(); self.assertTrue(all(e.status=='cached' for e in s2.entries))
            self.assertEqual(translate(s2.entries,s2,self.cache,client,conf)['total'],0)
            self.assertEqual(len(requests),2)
        finally: server.shutdown(); server.server_close()

    def test_wrong_numbers_not_saved(self):
        class BadClient:
            model='bad'
            def chat(self,messages):
                data=json.loads(messages[-1]['content'])
                return json.dumps({'translations':[{'id':e['id'],'text':e['source'].replace('Gain ','获得99').replace('New skill','新技能').replace('New Target Extraction','新卡池')} for e in data['entries']]})
        s=self.scan(); result=translate(s.entries,s,self.cache,BadClient(),{'interval':0,'retries':0})
        self.assertEqual(result['failed'],1)
        self.assertEqual(next(e for e in s.entries if 'Gain' in e.source).status,'failed')

if __name__=='__main__': unittest.main()
