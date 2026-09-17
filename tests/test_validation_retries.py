import collections
import json
import threading
from unittest.mock import patch
from test_bridge import Fixture
from test_retries import Opener,http_error
from bridge.core import protect,restore,validate_translation,Cancelled,MASK,BridgeError
from bridge.provider import Client,translate,AttemptBudget,SYSTEM_PROMPT

def translated(row):
    return row['source'].replace('New Target Extraction','新目标抽取').replace('New skill','新增技能').replace('Gain ','获得')

def reply(rows):
    return json.dumps({'translations':rows},ensure_ascii=False)

def envelope(text,finish='stop'):
    return {'choices':[{'finish_reason':finish,'message':{'content':text}}]}

class SimulatedClient:
    model='simulation'
    key='secret-key-never-record'
    def __init__(self,handler):
        self.handler=handler;self.calls=[]
    def chat(self,messages):
        data=json.loads(messages[-1]['content'])
        self.calls.append(data)
        return self.handler(data,len(self.calls))


class ValidationRetryTests(Fixture):
    def run_translation(self,client,entries=None,retries=10,stop=None):
        scan=self.scan()
        chosen=scan.entries if entries is None else entries(scan)
        with patch('bridge.provider.wait_for_retry'):
            result=translate(chosen,scan,self.cache,client,{'interval':0,'retries':retries},stop)
        return result

    def test_only_invalid_entry_is_resent_after_siblings_saved(self):
        seen=collections.Counter()
        def handler(data,n):
            rows=[]
            for row in data['entries']:
                source=row['source'];seen[source]+=1
                text=translated(row)
                if source.startswith('Gain ') and seen[source]==1:
                    text=text.replace(MASK.findall(text)[0],'')
                rows.append({'id':row['id'],'text':text})
            return reply(rows)
        client=SimulatedClient(handler)
        result=self.run_translation(client)
        self.assertEqual(result,{'success':3,'failed':0,'total':3})
        repair=[c for c in client.calls if any('repair_feedback' in e for e in c['entries'])]
        self.assertEqual(len(repair),1)
        self.assertEqual(len(repair[0]['entries']),1)
        self.assertEqual(repair[0]['entries'][0]['repair_feedback']['error_code'],'markers')
        self.assertEqual(sum(e['source']=='New skill' for c in client.calls for e in c['entries']),1)
        self.assertEqual(sum(e.status=='cached' for e in self.scan().entries),3)

    def test_no_chinese_gets_specific_feedback(self):
        def handler(data,n):
            return reply([{'id':row['id'],'text':row['source'] if n==1 else translated(row)}
                          for row in data['entries']])
        client=SimulatedClient(handler)
        result=self.run_translation(client,lambda s:[e for e in s.entries if e.source=='New skill'])
        self.assertEqual(result['success'],1)
        self.assertEqual(client.calls[1]['entries'][0]['repair_feedback']['error_code'],'no_chinese')

    def test_added_number_gets_number_feedback_and_corrected(self):
        def handler(data,n):
            return reply([{'id':row['id'],'text':translated(row)+('99' if n==1 else '')}
                          for row in data['entries']])
        client=SimulatedClient(handler)
        result=self.run_translation(client,lambda s:[e for e in s.entries if e.source.startswith('Gain ')])
        self.assertEqual(result['success'],1)
        self.assertEqual(client.calls[1]['entries'][0]['repair_feedback']['error_code'],'numbers')
        numbers=list(client.calls[0]['entries'][0]['protected_values'].values())
        self.assertIn('3',numbers)

    def test_tenth_correction_can_succeed(self):
        client=SimulatedClient(lambda data,n:reply([{'id':e['id'],'text':e['source'] if n<=10 else translated(e)}
                                                    for e in data['entries']]))
        result=self.run_translation(client,lambda s:[e for e in s.entries if e.source=='New skill'])
        self.assertEqual(result,{'success':1,'failed':0,'total':1})
        self.assertEqual(len(client.calls),11)

    def test_permanent_validation_failure_stops_at_ten_and_continues(self):
        def handler(data,n):
            return reply([{'id':row['id'],'text':row['source'] if row['source']=='New skill' else translated(row)}
                          for row in data['entries']])
        client=SimulatedClient(handler)
        result=self.run_translation(client)
        self.assertEqual(result,{'success':2,'failed':1,'total':3})
        counts=collections.Counter(e['source'] for c in client.calls for e in c['entries'])
        self.assertEqual(counts['New skill'],11)
        self.assertEqual(counts['New Target Extraction'],1)
        self.assertEqual(next(v for s,v in counts.items() if s.startswith('Gain ')),1)
        records=[json.loads(x) for x in (self.data/'validation-failures.jsonl').read_text(encoding='utf-8').splitlines()]
        self.assertTrue(any(x['final'] and x['attempts']==11 for x in records))
        self.assertNotIn(client.key,json.dumps(records))

    def test_network_and_validation_share_ten_retry_budget(self):
        client=Client({'api_base':'http://localhost/v1','model':'fake','retries':10},'')
        def handler(request,n):
            if n not in (5,11):return http_error(503)
            data=json.loads(json.loads(request.data)['messages'][-1]['content'])
            return envelope(reply([{'id':e['id'],'text':e['source']} for e in data['entries']]))
        client.opener=Opener(handler)
        result=self.run_translation(client,lambda s:[e for e in s.entries if e.source=='New skill'])
        self.assertEqual(result,{'success':0,'failed':1,'total':1})
        self.assertEqual(len(client.opener.calls),11)

    def test_json_error_splits_with_shared_attempt_accounting(self):
        def handler(data,n):
            if n==1:return '{"translations":[]}'
            return reply([{'id':e['id'],'text':translated(e)} for e in data['entries']])
        client=SimulatedClient(handler)
        result=self.run_translation(client,lambda s:[e for e in s.entries if e.file.startswith('Skills')])
        self.assertEqual(result,{'success':2,'failed':0,'total':2})
        self.assertEqual(len(client.calls),3)
        self.assertTrue(all(c['entries'][0]['repair_feedback']['error_code']=='json' for c in client.calls[1:]))

    def test_zero_retry_does_not_split_or_retry_bad_json(self):
        client=SimulatedClient(lambda data,n:'{"translations":[]}')
        result=self.run_translation(client,lambda s:[e for e in s.entries if e.file.startswith('Skills')],retries=0)
        self.assertEqual(result,{'success':0,'failed':2,'total':2})
        self.assertEqual(len(client.calls),1)

    def test_output_limit_splits_without_increasing_configured_token_cap(self):
        client=Client({'api_base':'http://localhost/v1','model':'fake','retries':10,'max_tokens':2048},'')
        def handler(request,n):
            body=json.loads(request.data);self.assertEqual(body['max_tokens'],2048)
            data=json.loads(body['messages'][-1]['content'])
            if n==1:return envelope('',finish='length')
            return envelope(reply([{'id':e['id'],'text':translated(e)} for e in data['entries']]))
        client.opener=Opener(handler)
        result=self.run_translation(client,lambda s:[e for e in s.entries if e.file.startswith('Skills')])
        self.assertEqual(result['success'],2)
        self.assertEqual(len(client.opener.calls),3)

    def test_cancel_during_correction_keeps_successful_sibling(self):
        client=SimulatedClient(lambda data,n:reply([{'id':e['id'],'text':e['source'] if e['source']=='New skill' else translated(e)}
                                                   for e in data['entries']]))
        scan=self.scan();chosen=[e for e in scan.entries if e.file.startswith('Skills')]
        stop=threading.Event()
        def cancel(delay,event):
            event.set()
            raise Cancelled('test cancellation')
        with patch('bridge.provider.wait_for_retry',side_effect=cancel):
            with self.assertRaises(Cancelled):
                translate(chosen,scan,self.cache,client,{'interval':0,'retries':10},stop)
        self.assertEqual(len(client.calls),1)
        self.assertEqual(sum(e.status=='cached' for e in self.scan().entries),1)

    def test_preexisting_failed_entry_can_be_explicitly_retried(self):
        client=SimulatedClient(lambda data,n:reply([{'id':e['id'],'text':translated(e)} for e in data['entries']]))
        scan=self.scan();entry=next(e for e in scan.entries if e.source=='New skill')
        entry.status='failed';entry.error='old error'
        with patch('bridge.provider.wait_for_retry'):
            result=translate([entry],scan,self.cache,client,{'interval':0})
        self.assertEqual(result['success'],1)
        self.assertEqual(entry.status,'cached');self.assertEqual(entry.error,'')

    def test_protected_values_keep_number_format(self):
        source='<color=#ff0000>Gain +3 [Binding]</color>\nLose -2 at 10% and 1.0.'
        masked,tokens=protect(source,numbers=True)
        self.assertTrue(all(value in tokens for value in ('+3','-2','10%','1.0')))
        text=masked.replace('Gain','获得').replace('Lose','失去').replace(' at ','在').replace(' and ','和')
        restored=restore(text,tokens)
        validate_translation(source,restored)
        self.assertIn('+3',restored);self.assertIn('1.0',restored)

    def test_diagnostics_do_not_store_rejected_reply_or_secret(self):
        client=SimulatedClient(lambda data,n:reply([{'id':e['id'],'text':'private rejected reply '+SimulatedClient.key}
                                                    for e in data['entries']]))
        self.run_translation(client,lambda s:[e for e in s.entries if e.source=='New skill'],retries=0)
        records=(self.data/'validation-failures.jsonl').read_text(encoding='utf-8')
        self.assertNotIn('private rejected reply',records)
        self.assertNotIn(client.key,records)
        data=json.loads(records.splitlines()[0])
        self.assertIn('uid',data);self.assertIn('source_hash',data);self.assertEqual(data['code'],'no_chinese')

    def test_final_numeric_failure_retains_expected_marker_count(self):
        client=SimulatedClient(lambda data,n:reply([{'id':e['id'],'text':translated(e).replace(MASK.findall(e['source'])[0],'')}
                                                    for e in data['entries']]))
        self.run_translation(client,lambda s:[e for e in s.entries if e.source.startswith('Gain ')],retries=0)
        records=[json.loads(x) for x in (self.data/'validation-failures.jsonl').read_text(encoding='utf-8').splitlines()]
        self.assertTrue(records[-1]['final'])
        self.assertEqual(records[-1]['expected_marker_count'],2)

    def test_prompt_appended_checks_explain_concrete_observed_failures(self):
        for wording in ('protected_values','+3 不改为 3','10% 不改为 10％','必须使用简体中文','repair_feedback'):
            self.assertIn(wording,SYSTEM_PROMPT)

    def test_malformed_envelope_is_retried(self):
        client=Client({'api_base':'http://localhost/v1','model':'fake','retries':10},'')
        def handler(request,n):
            if n==1:return {'choices':[None]}
            data=json.loads(json.loads(request.data)['messages'][-1]['content'])
            return envelope(reply([{'id':e['id'],'text':translated(e)} for e in data['entries']]))
        client.opener=Opener(handler)
        result=self.run_translation(client,lambda s:[e for e in s.entries if e.source=='New skill'])
        self.assertEqual(result['success'],1)
        self.assertEqual(len(client.opener.calls),2)

    def test_splitting_never_resets_each_entry_budget(self):
        client=SimulatedClient(lambda data,n:'{"translations":[]}')
        result=self.run_translation(client,lambda s:[e for e in s.entries if e.file.startswith('Skills')],retries=2)
        self.assertEqual(result,{'success':0,'failed':2,'total':2})
        counts=collections.Counter(e['source'] for c in client.calls for e in c['entries'])
        self.assertEqual(set(counts.values()),{3})
        self.assertEqual(len(client.calls),5)
