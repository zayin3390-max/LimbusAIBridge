import collections
import io
import json
import threading
import unittest
import urllib.error
import http.client
from datetime import datetime,timezone
from email.utils import format_datetime
from unittest.mock import patch
from test_bridge import Fixture
from bridge.core import Cancelled
from bridge.provider import Client,APIError,retry_delay,wait_for_retry,translate
from bridge import settings

class Opener:
    def __init__(self,handler):
        self.handler=handler
        self.calls=[]
    def open(self,request,timeout=None):
        self.calls.append(request)
        value=self.handler(request,len(self.calls))
        if isinstance(value,Exception): raise value
        return io.BytesIO(value if isinstance(value,bytes) else json.dumps(value).encode('utf-8'))

def http_error(code,headers=None):
    return urllib.error.HTTPError('https://example.invalid/v1',code,'must-not-log-secret',
                                  headers or {},io.BytesIO(b'must-not-log-secret'))

class RequestRetryTests(unittest.TestCase):
    def client(self,handler,retries=10,stop=None):
        self.logs=[]
        client=Client({'api_base':'http://localhost/v1','model':'test','retries':retries},
                      'must-not-log-secret',stop,progress=self.logs.append)
        client.opener=Opener(handler)
        return client

    def test_ten_retries_then_success_on_eleventh_request(self):
        client=self.client(lambda request,n:http_error(503) if n<=10 else {'ok':True})
        with patch('bridge.provider.wait_for_retry') as wait:
            self.assertEqual(client.request({'test':True}),{'ok':True})
        self.assertEqual(len(client.opener.calls),11)
        self.assertEqual(wait.call_count,10)
        self.assertIn('10/10',self.logs[-1])
        self.assertNotIn('must-not-log-secret',''.join(self.logs))

    def test_retry_limit_exhausted_is_nonfatal_and_not_more_than_eleven(self):
        client=self.client(lambda request,n:http_error(429),retries=999)
        with patch('bridge.provider.wait_for_retry') as wait:
            with self.assertRaises(APIError) as raised:
                client.request({})
        self.assertEqual(client.retries,10)
        self.assertEqual(len(client.opener.calls),11)
        self.assertEqual(wait.call_count,10)
        self.assertTrue(raised.exception.exhausted)
        self.assertFalse(raised.exception.fatal)
        self.assertNotIn('must-not-log-secret',str(raised.exception))

    def test_timeout_disconnect_and_incomplete_body_are_retried(self):
        failures=[TimeoutError(),ConnectionResetError(),http.client.IncompleteRead(b'partial')]
        client=self.client(lambda request,n:failures[n-1] if n<=3 else {'ok':1})
        with patch('bridge.provider.wait_for_retry'):
            self.assertEqual(client.request({}),{'ok':1})
        self.assertEqual(len(client.opener.calls),4)

    def test_temporary_http_statuses_retry(self):
        for code in (408,409,425,429,500,502,503,504,520,529):
            with self.subTest(code=code):
                client=self.client(lambda request,n:http_error(code) if n==1 else {'ok':1})
                with patch('bridge.provider.wait_for_retry'):
                    self.assertEqual(client.request({}),{'ok':1})
                self.assertEqual(len(client.opener.calls),2)

    def test_auth_and_config_errors_stop_without_blind_retries(self):
        for code in (400,401,402,403,404,405,413,415,422):
            with self.subTest(code=code):
                client=self.client(lambda request,n:http_error(code))
                with patch('bridge.provider.wait_for_retry') as wait:
                    with self.assertRaises(APIError) as raised: client.request({})
                self.assertTrue(raised.exception.fatal)
                self.assertEqual(len(client.opener.calls),1)
                wait.assert_not_called()

    def test_bad_json_and_invalid_encoding_retry(self):
        client=self.client(lambda request,n: [b'',b'<html>temporary proxy error</html>',b'\xff'][n-1]
                           if n<=3 else {'ok':True})
        with patch('bridge.provider.wait_for_retry'):
            self.assertEqual(client.request({}),{'ok':True})
        self.assertEqual(len(client.opener.calls),4)

    def test_retry_after_seconds_and_http_date(self):
        client=self.client(lambda request,n:http_error(429,{'Retry-After':'90'}) if n==1 else {'ok':1})
        with patch('bridge.provider.wait_for_retry') as wait:
            client.request({})
        self.assertEqual(wait.call_args.args[0],90)
        self.assertEqual([retry_delay(i) for i in range(10)],[2,4,8,16,32,60,60,60,60,60])
        with patch('bridge.provider.time.time',return_value=1000):
            date=format_datetime(datetime.fromtimestamp(1095,timezone.utc),usegmt=True)
            self.assertEqual(retry_delay(0,date),95)
        self.assertEqual(retry_delay(0,'invalid'),2)
        self.assertEqual(retry_delay(0,'9'*500),2)

    def test_zero_disables_retry(self):
        client=self.client(lambda request,n:TimeoutError(),retries=0)
        with patch('bridge.provider.wait_for_retry') as wait:
            with self.assertRaises(APIError) as raised:client.request({})
        self.assertTrue(raised.exception.exhausted)
        self.assertEqual(len(client.opener.calls),1)
        wait.assert_not_called()

    def test_cancel_during_wait_prevents_next_request(self):
        stop=threading.Event()
        client=self.client(lambda request,n:http_error(503),stop=stop)
        def cancel_and_wait(delay,event):
            event.set()
            wait_for_retry(delay,event)
        with patch('bridge.provider.wait_for_retry',side_effect=cancel_and_wait):
            with self.assertRaises(Cancelled):client.request({})
        self.assertEqual(len(client.opener.calls),1)

    def test_long_wait_is_interruptible(self):
        class Stop:
            def is_set(self): return False
            def wait(self,seconds):
                self.seconds=seconds
                return True
        event=Stop()
        with self.assertRaises(Cancelled):wait_for_retry(3600,event)
        self.assertLessEqual(event.seconds,30)


class TranslationRetryTests(Fixture):
    def request_handler(self,fail_file):
        def handler(request,n):
            body=json.loads(request.data)
            entries=json.loads(body['messages'][-1]['content'])['entries']
            if entries[0]['file']==fail_file:
                return http_error(503)
            mapping={'New skill':'新增技能','Gain ':'获得','New Target Extraction':'新目标抽取'}
            rows=[]
            for entry in entries:
                text=entry['source']
                for source,target in mapping.items():text=text.replace(source,target)
                rows.append({'id':entry['id'],'text':text})
            return {'choices':[{'finish_reason':'stop','message':{
                'content':json.dumps({'translations':rows},ensure_ascii=False)}}]}
        return handler

    def test_exhausted_batch_does_not_split_and_later_batch_continues(self):
        scan=self.scan()
        entries=sorted(scan.entries,key=lambda e:e.file=='GachaTitle.json')
        client=Client({'api_base':'http://localhost/v1','model':'mock','retries':10},'')
        client.opener=Opener(self.request_handler('Skills_personality-01.json'))
        with patch('bridge.provider.wait_for_retry'):
            result=translate(entries,scan,self.cache,client,{'interval':0})
        self.assertEqual(result,{'success':1,'failed':2,'total':3})
        files=[json.loads(json.loads(r.data)['messages'][-1]['content'])['entries'][0]['file']
               for r in client.opener.calls]
        self.assertEqual(collections.Counter(files),{'Skills_personality-01.json':11,'GachaTitle.json':1})
        again=self.scan()
        self.assertEqual(next(e for e in again.entries if e.file=='GachaTitle.json').status,'cached')
        client.opener=Opener(self.request_handler('no-file'))
        with patch('bridge.provider.wait_for_retry'):
            resumed=translate(again.entries,again,self.cache,client,{'interval':0})
        self.assertEqual(resumed,{'success':2,'failed':0,'total':2})
        self.assertEqual(len(client.opener.calls),1)

    def test_fatal_after_success_preserves_cache_and_stops_future_requests(self):
        scan=self.scan()
        client=Client({'api_base':'http://localhost/v1','model':'mock','retries':10},'')
        good=self.request_handler('no-file')
        client.opener=Opener(lambda request,n:good(request,n) if n==1 else http_error(401))
        with patch('bridge.provider.wait_for_retry'):
            with self.assertRaises(APIError) as raised:
                translate(scan.entries,scan,self.cache,client,{'interval':0})
        self.assertTrue(raised.exception.fatal)
        self.assertEqual(len(client.opener.calls),2)
        self.assertEqual(sum(e.status=='cached' for e in self.scan().entries),1)

    def test_legacy_hidden_default_migrates_in_memory_without_touching_file(self):
        original={'game_path':'fixture','api_base':'https://example.invalid/v1',
                  'model':'keep-model','retries':2,'remember_key':False}
        file=self.data/'settings.json';self.write(file,original)
        before=file.read_bytes()
        config,key=settings.load(self.data)
        self.assertEqual(config['retries'],10)
        self.assertEqual(config['api_base'],original['api_base'])
        self.assertEqual(config['model'],'keep-model')
        self.assertEqual(file.read_bytes(),before)
        self.assertEqual(key,'')

    def test_saved_retry_choice_is_respected_after_migration(self):
        self.write(self.data/'settings.json',{'retry_policy_version':1,'retries':3})
        config,key=settings.load(self.data)
        self.assertEqual(config['retries'],3)
        self.assertEqual(key,'')
