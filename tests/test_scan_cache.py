import gzip
import json
import pathlib
import unittest
from unittest.mock import patch
from test_bridge import Fixture
from bridge.core import BridgeError,assert_fresh
from bridge.scan_cache import save_scan,load_scan,NAME

class ScanCacheTests(Fixture):
    def test_round_trip_without_game_reads_or_rescan(self):
        scan=self.scan()
        for e in scan.entries:e.newly_seen=True
        when=save_scan(scan,self.data)
        original=pathlib.Path.open
        def guarded(path,*args,**kwargs):
            if path.is_relative_to(self.game):
                self.fail('Loading a snapshot must not read game files')
            return original(path,*args,**kwargs)
        with patch('bridge.core.scan_game',side_effect=AssertionError('No rescan')), \
             patch('bridge.core.signature',side_effect=AssertionError('No update polling')), \
             patch('bridge.consistency.align_translations',side_effect=AssertionError('No redundant full alignment')), \
             patch.object(pathlib.Path,'open',guarded):
            restored,saved=load_scan(self.data,self.game,cache=self.cache)
        self.assertEqual(saved,when)
        self.assertEqual([e.uid for e in restored.entries],[e.uid for e in scan.entries])
        self.assertTrue(all(e.newly_seen for e in restored.entries))
        self.assertEqual(restored.sources,scan.sources)
        self.assertEqual(restored.bases,scan.bases)
        self.assertEqual(restored.fingerprints,scan.fingerprints)
        self.assertEqual(restored.entries[0].tokens,scan.entries[0].tokens)

    def test_translation_database_takes_priority_after_snapshot(self):
        scan=self.scan();e=next(e for e in scan.entries if e.field=='desc')
        save_scan(scan,self.data)
        self.cache.put(e,'获得3层[Binding]。','manual')
        restored,_=load_scan(self.data,self.game,cache=self.cache)
        got=next(r for r in restored.entries if r.uid==e.uid)
        self.assertEqual(got.translation,'获得3层[Binding]。')
        self.assertEqual(got.status,'cached')
        self.assertEqual(got.translation_model,'manual')

    def test_unignore_is_not_lost_to_snapshot(self):
        scan=self.scan();e=scan.entries[0]
        self.cache.ignore(e)
        save_scan(scan,self.data)
        self.cache.ignore(e,False)
        restored,_=load_scan(self.data,self.game,cache=self.cache)
        self.assertEqual(next(r for r in restored.entries if r.uid==e.uid).status,'pending')

    def test_updated_game_can_be_viewed_but_cannot_be_used_for_translation(self):
        scan=self.scan();save_scan(scan,self.data)
        self.write_source('GachaTitle.json',{'dataList':[{'id':'pool_new','content':'Changed pool'}]})
        restored,_=load_scan(self.data,self.game,cache=self.cache)
        self.assertEqual(restored.signature,scan.signature)
        with self.assertRaises(BridgeError):assert_fresh(restored)

    def test_path_or_language_change_does_not_restore_other_game(self):
        save_scan(self.scan(),self.data)
        self.assertIsNone(load_scan(self.data,self.game.parent/'other'))
        self.assertIsNone(load_scan(self.data,self.game,self.zh.parent/'other'))
        self.assertIsNone(load_scan(self.data,self.game,lang='kr'))

    def test_corrupt_snapshot_is_preserved_and_does_not_trigger_rescan(self):
        path=self.data/NAME;path.write_bytes(b'broken cache')
        with patch('bridge.core.scan_game',side_effect=AssertionError('No rescan')):
            with self.assertRaisesRegex(BridgeError,'原缓存已保留'):
                load_scan(self.data,self.game)
        self.assertEqual(path.read_bytes(),b'broken cache')

    def test_snapshot_outside_scope_is_rejected(self):
        save_scan(self.scan(),self.data);path=self.data/NAME
        data=json.loads(gzip.decompress(path.read_bytes()))
        key=next(iter(data['source_paths']))
        data['source_paths'][key][1]=str(self.root/'unrelated.json')
        raw=gzip.compress(json.dumps(data).encode('utf-8'));path.write_bytes(raw)
        with self.assertRaises(BridgeError):load_scan(self.data,self.game)
        self.assertEqual(path.read_bytes(),raw)

    def test_missing_snapshot_returns_no_result(self):
        self.assertIsNone(load_scan(self.data,self.game))


class LocalKnowledgeStampTests(unittest.TestCase):
    def test_local_glossary_and_reviews_invalidate_only_derived_cache(self):
        import tempfile
        from pathlib import Path
        from bridge.core import Cache
        from bridge.scan_cache import translation_stamp
        with tempfile.TemporaryDirectory() as tmp:
            Cache(tmp)
            first=translation_stamp(tmp)
            Path(tmp,'glossary.json').write_text('{"new":"name"}',encoding='utf-8')
            second=translation_stamp(tmp)
            self.assertNotEqual(first,second)
            Path(tmp,'reviewed-abbreviations.json').write_text('{"version":1}',encoding='utf-8')
            self.assertNotEqual(second,translation_stamp(tmp))
