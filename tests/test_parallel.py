import collections
import json
import threading
import time
import unittest
from unittest.mock import patch
from test_bridge import Fixture
from test_retries import Opener,http_error
from test_validation_retries import SimulatedClient,translated,reply,envelope
from bridge.core import Cancelled,MASK
from bridge.provider import Client,APIError,translate,RequestCooldown,TranslationStop,wait_for_retry
from bridge import settings


class ParallelTests(Fixture):
    def options(self,**extra):
        return dict({'interval':0,'concurrency':2,'batch_size':1,'retries':10},**extra)

    def good(self,data):
        return reply([{'id':e['id'],'text':translated(e)} for e in data['entries']])

    def test_requests_overlap_with_bounded_concurrency_and_cache_resume(self):
        self.write_source('GachaTitle.json',{'dataList':[
            {'id':'pool_'+str(i),'content':'New Target Extraction'} for i in range(14)]})
        scan=self.scan()
        lock=threading.Lock();gate=threading.Barrier(2,timeout=3)
        active=0;peak=0;started=0
        def handler(data,n):
            nonlocal active,peak,started
            with lock:
                active+=1;peak=max(peak,active);started+=1;order=started
            if order<=2: gate.wait()
            time.sleep(0.008)
            with lock:active-=1
            return self.good(data)
        client=SimulatedClient(handler)
        result=translate(scan.entries+scan.entries,scan,self.cache,client,self.options())
        self.assertEqual(peak,2)
        self.assertEqual(result,{'success':16,'failed':0,'total':16})
        self.assertEqual(len(client.calls),16)
        self.assertEqual(sum(e.status=='cached' for e in self.scan().entries),16)
        again=self.scan()
        self.assertEqual(translate(again.entries,again,self.cache,client,self.options())['total'],0)
        self.assertEqual(len(client.calls),16)

    def test_one_channel_remains_serial(self):
        scan=self.scan();threads=set()
        def handler(data,n):
            threads.add(threading.get_ident())
            return self.good(data)
        client=SimulatedClient(handler)
        result=translate(scan.entries,scan,self.cache,client,self.options(concurrency=1))
        self.assertEqual(result['success'],3)
        self.assertEqual(threads,{threading.get_ident()})

    def test_four_channels_are_supported_and_fifth_is_rejected(self):
        self.write_source('GachaTitle.json',{'dataList':[
            {'id':'pool_'+str(i),'content':'New Target Extraction'} for i in range(4)]})
        scan=self.scan();gate=threading.Barrier(4,timeout=3)
        client=SimulatedClient(lambda data,n:(gate.wait(),self.good(data))[1])
        chosen=[e for e in scan.entries if e.file=='GachaTitle.json']
        result=translate(chosen,scan,self.cache,client,self.options(concurrency=4))
        self.assertEqual(result['success'],4)
        for value in (0,5):
            with self.assertRaisesRegex(Exception,'1–4'):
                translate([],scan,self.cache,client,self.options(concurrency=value))

    def test_slow_batch_does_not_block_later_batches(self):
        scan=self.scan()
        chosen=sorted(scan.entries,key=lambda e:e.source!='New skill')
        later_done=threading.Event()
        def handler(data,n):
            if data['entries'][0]['source']=='New skill':
                self.assertTrue(later_done.wait(3),'other channel stopped behind slow batch')
            elif data['entries'][0]['source'].startswith('Gain '):
                later_done.set()
            return self.good(data)
        client=SimulatedClient(handler)
        result=translate(chosen,scan,self.cache,client,self.options())
        self.assertEqual(result['success'],3)

    def test_parallel_corrections_keep_limits_and_diagnostics_intact(self):
        scan=self.scan();seen=collections.Counter();lock=threading.Lock()
        def handler(data,n):
            row=data['entries'][0]
            with lock:seen[row['source']]+=1
            return reply([{'id':row['id'],'text':row['source'] if row['source']=='New skill' else translated(row)}])
        client=SimulatedClient(handler)
        with patch('bridge.provider.wait_for_retry'):
            result=translate(scan.entries,scan,self.cache,client,self.options())
        self.assertEqual(result,{'success':2,'failed':1,'total':3})
        self.assertEqual(seen['New skill'],11)
        self.assertEqual(sorted(seen.values()),[1,1,11])
        rows=[json.loads(s) for s in (self.data/'validation-failures.jsonl').read_text(encoding='utf-8').splitlines()]
        self.assertEqual(sum(r['final'] for r in rows),1)
        self.assertEqual(rows[-1]['attempts'],11)
        self.assertNotIn(client.key,json.dumps(rows))

    def test_correction_delay_is_short_even_on_tenth_retry(self):
        scan=self.scan();entry=next(e for e in scan.entries if e.source=='New skill')
        client=SimulatedClient(lambda data,n:reply([{'id':'0','text':entry.source}]))
        with patch('bridge.provider.wait_for_retry') as pause:
            result=translate([entry],scan,self.cache,client,self.options(concurrency=1))
        self.assertEqual(result['failed'],1)
        positive=[call.args[0] for call in pause.call_args_list if call.args[0]>0]
        self.assertEqual(positive,[1.0]*10)

    def test_cancel_stops_dispatch_and_saves_valid_inflight_responses(self):
        scan=self.scan();stop=threading.Event();barrier=threading.Barrier(2,timeout=3)
        def handler(data,n):
            barrier.wait()
            stop.set()
            return self.good(data)
        client=SimulatedClient(handler)
        with self.assertRaises(Cancelled):
            translate(scan.entries,scan,self.cache,client,self.options(),stop)
        self.assertEqual(len(client.calls),2)
        self.assertEqual(sum(e.status=='cached' for e in self.scan().entries),2)

    def test_fatal_error_wins_over_sibling_cancellation_and_preserves_cache(self):
        scan=self.scan();barrier=threading.Barrier(2,timeout=3)
        failed=threading.Event()
        def handler(data,n):
            barrier.wait()
            if data['entries'][0]['file']=='GachaTitle.json':
                failed.set()
                raise APIError('鉴权失败',fatal=True)
            self.assertTrue(failed.wait(3))
            return self.good(data)
        client=SimulatedClient(handler)
        with self.assertRaises(APIError) as raised:
            translate(scan.entries,scan,self.cache,client,self.options())
        self.assertTrue(raised.exception.fatal)
        self.assertEqual(len(client.calls),2)
        self.assertEqual(sum(e.status=='cached' for e in self.scan().entries),1)

    def test_real_client_workers_have_independent_openers(self):
        scan=self.scan();barrier=threading.Barrier(2,timeout=3)
        openers=[];lock=threading.Lock();started=0
        def handler(request,n):
            nonlocal started
            with lock:started+=1;order=started
            if order<=2:barrier.wait()
            data=json.loads(json.loads(request.data)['messages'][-1]['content'])
            return envelope(self.good(data))
        def factory(*args,**kwargs):
            opener=Opener(handler);openers.append(opener);return opener
        with patch('bridge.provider.urllib.request.build_opener',side_effect=factory):
            client=Client({'api_base':'http://localhost/v1','model':'simulation'},'')
            result=translate(scan.entries,scan,self.cache,client,self.options())
        self.assertEqual(result['success'],3)
        self.assertEqual(len(openers),3)
        self.assertEqual(len(openers[0].calls),0)
        self.assertTrue(all(o.calls for o in openers[1:]))

    def test_parallel_network_and_validation_share_request_budget(self):
        scan=self.scan();lock=threading.Lock();seen=collections.Counter()
        def handler(request,n):
            data=json.loads(json.loads(request.data)['messages'][-1]['content'])
            row=data['entries'][0];source=row['source']
            with lock:seen[source]+=1;used=seen[source]
            if source=='New skill' and used not in (5,11):return http_error(503)
            text=source if source=='New skill' else translated(row)
            return envelope(reply([{'id':row['id'],'text':text}]))
        with patch('bridge.provider.urllib.request.build_opener',side_effect=lambda *a,**k:Opener(handler)):
            client=Client({'api_base':'http://localhost/v1','model':'simulation'},'')
            with patch('bridge.provider.wait_for_retry'):
                result=translate(scan.entries,scan,self.cache,client,self.options())
        self.assertEqual(result,{'success':2,'failed':1,'total':3})
        self.assertEqual(seen['New skill'],11)

    def test_parallel_json_failures_split_without_resetting_budgets(self):
        scan=self.scan();seen=collections.Counter();lock=threading.Lock()
        def handler(data,n):
            with lock:seen.update(e['source'] for e in data['entries'])
            return '{"translations":[]}'
        client=SimulatedClient(handler)
        with patch('bridge.provider.wait_for_retry'):
            result=translate(scan.entries,scan,self.cache,client,self.options(batch_size=20,retries=2))
        self.assertEqual(result,{'success':0,'failed':3,'total':3})
        self.assertEqual(set(seen.values()),{3})
        records=[json.loads(s) for s in (self.data/'validation-failures.jsonl').read_text(encoding='utf-8').splitlines()]
        self.assertEqual(sum(r['final'] for r in records),3)

    def test_saved_and_legacy_concurrency_settings(self):
        path=self.data/'settings.json'
        self.write(path,{'game_path':'fixture','retries':10,'retry_policy_version':1})
        before=path.read_bytes();config,_=settings.load(self.data)
        self.assertEqual(config['concurrency'],2);self.assertEqual(path.read_bytes(),before)
        config['concurrency']=4;settings.save(self.data,config,'')
        self.assertEqual(settings.load(self.data)[0]['concurrency'],4)


class CooldownTests(unittest.TestCase):
    def test_server_limit_blocks_other_clients_and_honors_longer_wait(self):
        clock=[100.0];waits=[]
        def fake_wait(seconds,stop):
            waits.append(seconds);clock[0]+=seconds
        config={'api_base':'http://localhost/v1','model':'simulation','retries':0}
        parent=Client(config,'')
        gate=RequestCooldown();stop=TranslationStop()
        a=parent.fork(stop,lambda _:None,gate)
        b=parent.fork(stop,lambda _:None,gate)
        a.opener=Opener(lambda request,n:http_error(429,{'Retry-After':'90'}))
        b.opener=Opener(lambda request,n:{'ok':True})
        with patch('bridge.provider.time.monotonic',side_effect=lambda:clock[0]):
            with patch('bridge.provider.wait_for_retry',side_effect=fake_wait):
                with self.assertRaises(APIError):a.request({})
                self.assertEqual(b.request({}),{'ok':True})
        self.assertEqual(waits,[90.0])
        self.assertEqual(len(b.opener.calls),1)

    def test_cooldown_extends_and_does_not_shorten(self):
        gate=RequestCooldown();clock=[10.0];waits=[]
        def advance(seconds,stop):
            waits.append(seconds);clock[0]+=seconds
            if len(waits)==1:gate.defer(3)
        with patch('bridge.provider.time.monotonic',side_effect=lambda:clock[0]):
            gate.defer(9);gate.defer(2)
            with patch('bridge.provider.wait_for_retry',side_effect=advance):gate.wait(None)
        self.assertEqual(waits,[9,3])

    def test_user_cancels_shared_cooldown_without_dispatch(self):
        event=threading.Event();stop=TranslationStop(event);gate=RequestCooldown()
        client=Client({'api_base':'http://localhost/v1','model':'simulation'},'').fork(stop,lambda _:None,gate)
        client.opener=Opener(lambda request,n:{'ok':True})
        gate.defer(90)
        def cancel(delay,token):
            event.set()
            wait_for_retry(delay,token)
        with patch('bridge.provider.wait_for_retry',side_effect=cancel):
            with self.assertRaises(Cancelled):client.request({})
        self.assertEqual(client.opener.calls,[])
        self.assertTrue(stop.wait(60))

    def test_new_run_does_not_inherit_internal_failure_stop(self):
        user=threading.Event();old=TranslationStop(user);old.set()
        self.assertTrue(old.is_set());self.assertFalse(user.is_set())
        self.assertFalse(TranslationStop(user).is_set())
