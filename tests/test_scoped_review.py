import unittest
from types import SimpleNamespace
from bridge.core import Entry
from bridge.scoped_review import context_hash,locks,short_name_locks

class ScopedReviewTests(unittest.TestCase):
    def setUp(self):
        self.e=Entry('scene-a','StoryData/S1.json',(),(),'content','Need a G.B.?',None,'missing',True,refs={'jp':'黄金'})
        self.neighbors=[{'source':'I mean golden hide.'}]
        self.records={self.e.uid:dict(source_hash=self.e.cache_hash,context_hash=context_hash(self.e,self.neighbors),evidence='Same scene correction in KR and JP',locks={'G.B.':'黄·金'})}

    def test_review_only_matches_same_source_references_and_scene(self):
        self.assertEqual(locks(self.records,self.e,self.neighbors,['G.B.']),{'G.B.':'黄·金'})
        self.assertEqual(locks(self.records,self.e,[{'source':'A different meaning.'}],['G.B.']),{})
        self.e.refs['jp']='Different source'
        self.assertEqual(locks(self.records,self.e,self.neighbors,['G.B.']),{})

    def test_review_is_not_global_for_same_letters(self):
        self.e.uid='scene-b'
        self.assertEqual(locks(self.records,self.e,self.neighbors,['G.B.']),{})

    def test_review_requires_evidence_and_existing_code(self):
        self.assertEqual(locks(self.records,self.e,self.neighbors,['A.B.']),{})
        self.records[self.e.uid]['evidence']=''
        self.assertEqual(locks(self.records,self.e,self.neighbors,['G.B.']),{})

    def test_faction_short_name_requires_reference_identity(self):
        scan=SimpleNamespace(consistency_terms={'Le Rouge':{'translation':'勒鲁日'}})
        self.e.source='Those Rouges.';self.e.refs={'kr':'르루주'}
        self.assertEqual(short_name_locks(scan,self.e),{'Rouges':'勒鲁日'})
        self.e.refs={'kr':'빨강'}
        self.assertEqual(short_name_locks(scan,self.e),{})
        self.e.source='Le Rouge';self.e.refs={'kr':'르루주'}
        self.assertEqual(short_name_locks(scan,self.e),{})
