import json
import threading
from unittest.mock import patch
from test_bridge import Fixture
from test_validation_retries import SimulatedClient,reply,translated
from bridge.core import BridgeError,Cancelled,payload
from bridge.provider import APIError
from bridge.retranslation import retranslate,eligible
from bridge.ui_model import matches

class RetranslationTests(Fixture):
    def seed(self):
        scan=self.scan()
        for e in scan.entries:
            value={'New skill':'旧技能','Gain 3 [Binding].':'获得3层[Binding]。','New Target Extraction':'旧卡池'}[e.source]
            self.cache.put(e,value,'old-model')
        return self.scan()

    def run_retranslation(self,scan,chosen,client,**options):
        settings={'retries':1,'interval':0,'concurrency':1,**options}
        with patch('bridge.provider.wait_for_retry'):
            return retranslate(chosen,scan,self.cache,client,settings)

    def raw(self):
        with self.cache.connect() as con:
            return {u:(z,m) for u,z,m in con.execute('select uid,translated,model from translations')}

    def good(self,data,n):
        return reply([{'id':r['id'],'text':translated(r)} for r in data['entries']])

    def test_only_selected_existing_text_is_sent_and_old_result_backed_up(self):
        scan=self.seed();target=next(e for e in scan.entries if e.source=='New skill')
        before=self.raw()
        def response(data,n):
            backups=list((self.data/'retranslation-history').glob('*.json'))
            self.assertEqual(len(backups),1)
            self.assertEqual(json.loads(backups[0].read_text(encoding='utf-8'))['entries'][0]['cache_rows'][0]['translated'],'旧技能')
            self.assertEqual(self.raw(),before)
            self.assertEqual(len(data['entries']),1)
            self.assertEqual(data['entries'][0]['source'],'New skill')
            self.assertNotIn('旧技能',json.dumps(data,ensure_ascii=False))
            return self.good(data,n)
        client=SimulatedClient(response)
        result=self.run_retranslation(scan,[target,target],client)
        self.assertEqual((result['total'],result['success'],result['failed']),(1,1,0))
        self.assertEqual(target.translation,'新增技能')
        self.assertEqual(target.translation_model,'retranslate:simulation')
        self.assertEqual(len(client.calls),1)
        self.assertEqual({k:v for k,v in self.raw().items() if k!=target.uid},{k:v for k,v in before.items() if k!=target.uid})

    def test_validation_exhaustion_retains_old_text_in_cache_pack_and_failure_filter(self):
        scan=self.seed();target=next(e for e in scan.entries if e.source=='New skill')
        before=self.raw()
        client=SimulatedClient(lambda d,n:reply([{'id':r['id'],'text':''} for r in d['entries']]))
        result=self.run_retranslation(scan,[target],client,retries=10)
        self.assertEqual(len(client.calls),11)
        self.assertEqual(result['failed'],1)
        self.assertEqual(self.raw(),before)
        self.assertEqual(target.status,'cached')
        self.assertEqual(target.translation,'旧技能')
        self.assertIn('旧译文已保留',target.retranslation_error)
        self.assertTrue(matches(target,'失败项',{target.category}))
        rebuilt=self.scan();again=next(e for e in rebuilt.entries if e.uid==target.uid)
        self.assertEqual(again.retranslation_error,target.retranslation_error)
        files,_=payload(rebuilt)
        self.assertIn('旧技能',files[target.file].decode('utf-8'))

    def test_failure_can_be_retried_and_success_clears_persistent_error(self):
        scan=self.seed();target=next(e for e in scan.entries if e.source=='New skill')
        bad=SimulatedClient(lambda d,n:reply([{'id':r['id'],'text':''} for r in d['entries']]))
        self.run_retranslation(scan,[target],bad,retries=0)
        result=self.run_retranslation(scan,[target],SimulatedClient(self.good))
        self.assertEqual(result['success'],1)
        self.assertEqual(target.retranslation_error,'')
        self.assertEqual(next(e for e in self.scan().entries if e.uid==target.uid).retranslation_error,'')
        self.assertEqual(len(list((self.data/'retranslation-history').glob('*.json'))),2)

    def test_fatal_error_keeps_completed_siblings_and_old_unfinished_rows(self):
        scan=self.seed();before=self.raw()
        def answer(data,n):
            if n==2:raise APIError('鉴权失败',fatal=True)
            return self.good(data,n)
        client=SimulatedClient(answer)
        with self.assertRaises(APIError):
            self.run_retranslation(scan,scan.entries,client,batch_size=1)
        completed=[e for e in scan.entries if e.translation_model=='retranslate:simulation']
        self.assertEqual(len(completed),1)
        for e in scan.entries:
            if e not in completed:
                self.assertEqual(self.raw()[e.uid],before[e.uid])
                self.assertIn('未完成',e.retranslation_error)

    def test_cancellation_restores_original_rows_but_keeps_valid_response(self):
        scan=self.seed();stop=threading.Event();before=self.raw()
        def answer(data,n):
            stop.set()
            return self.good(data,n)
        client=SimulatedClient(answer)
        with patch('bridge.provider.wait_for_retry'):
            with self.assertRaises(Cancelled):
                retranslate(scan.entries,scan,self.cache,client,{'interval':0,'batch_size':1},stop)
        self.assertEqual(sum(e.translation_model=='retranslate:simulation' for e in scan.entries),1)
        for e in scan.entries:
            if e.translation_model!='retranslate:simulation':
                self.assertEqual(self.raw()[e.uid],before[e.uid])
                self.assertIn('已停止',e.retranslation_error)

    def test_unselected_manually_reviewed_name_remains_a_reference(self):
        self.write_source('ScenarioModelCodes.json',{'dataList':[{'id':'test_actor','name':'True Name'}]})
        self.write_source('StoryData/new.json',{'dataList':[{'id':1,'model':'단테','content':'True Name, come here.'}]})
        scan=self.scan()
        name=next(e for e in scan.entries if e.file=='ScenarioModelCodes.json')
        line=next(e for e in scan.entries if e.file=='StoryData/new.json')
        self.cache.put(name,'人工定名','manual')
        self.cache.put(line,'旧名字，过来。','old-model')
        scan=self.scan();line=next(e for e in scan.entries if e.file=='StoryData/new.json')
        def answer(data,n):
            row=data['entries'][0]
            self.assertEqual(row['protected_values']['⟦P0000⟧'],'人工定名')
            return reply([{'id':row['id'],'text':'⟦P0000⟧，过来。'}])
        self.run_retranslation(scan,[line],SimulatedClient(answer))
        self.assertEqual(line.translation,'人工定名，过来。')
        self.assertEqual(self.raw()[name.uid],('人工定名','manual'))

    def test_no_request_when_backup_fails(self):
        scan=self.seed();before=self.raw()
        client=SimulatedClient(lambda d,n:self.fail('Should not call API'))
        with patch('bridge.retranslation.atomic_write',side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.run_retranslation(scan,scan.entries,client)
        self.assertEqual(self.raw(),before)

    def test_human_reference_and_ignored_entries_are_never_resent(self):
        scan=self.seed()
        scan.entries[0].translation_model='human-reference'
        scan.entries[1].status='ignored'
        client=SimulatedClient(self.good)
        result=self.run_retranslation(scan,scan.entries,client)
        self.assertEqual(result['total'],1)
        self.assertEqual(len(client.calls),1)

    def test_retranslated_name_wins_over_old_unselected_status_duplicate(self):
        for file in ('Bufs_new.json','BattleKeywords_new.json'):
            self.write_source(file,{'dataList':[{'id':'NewStatus','name':'Fresh Look'}]})
        scan=self.scan()
        for e in scan.entries:
            if e.source=='Fresh Look':self.cache.put(e,'旧状态名','old-model')
        scan=self.scan();target=next(e for e in scan.entries if e.file=='BattleKeywords_new.json')
        before=self.raw()
        def answer(data,n):
            self.assertEqual(data['entries'][0]['source'],'Fresh Look')
            self.assertNotIn('旧状态名',json.dumps(data,ensure_ascii=False))
            return reply([{'id':r['id'],'text':'新状态名'} for r in data['entries']])
        client=SimulatedClient(answer)
        self.run_retranslation(scan,[target],client)
        self.assertEqual(len(client.calls),1)
        self.assertEqual({e.translation for e in scan.entries if e.source=='Fresh Look'},{'新状态名'})
        self.assertEqual({e.translation for e in self.scan().entries if e.source=='Fresh Look'},{'新状态名'})
        other=next(e for e in scan.entries if e.file=='Bufs_new.json')
        self.assertEqual(self.raw()[other.uid],before[other.uid])

    def test_parallel_retranslation_keeps_per_entry_backup_and_result(self):
        scan=self.seed()
        client=SimulatedClient(self.good)
        result=self.run_retranslation(scan,scan.entries,client,concurrency=2,batch_size=1)
        self.assertEqual(result['success'],3)
        self.assertTrue(all(e.translation_model=='retranslate:simulation' for e in scan.entries))
        backup=json.loads(__import__('pathlib').Path(result['backup']).read_text(encoding='utf-8'))
        self.assertEqual(len(backup['entries']),3)

    def test_failure_reason_does_not_persist_api_secret(self):
        scan=self.seed()
        client=SimulatedClient(lambda d,n:(_ for _ in ()).throw(APIError('error secret-key-never-record',fatal=True)))
        with self.assertRaises(APIError):self.run_retranslation(scan,scan.entries,client)
        self.assertNotIn(client.key,' '.join(e.retranslation_error for e in scan.entries))
        with self.cache.connect() as con:
            reasons=str(con.execute('select reason from retranslation_failures').fetchall())
        self.assertNotIn(client.key,reasons)
