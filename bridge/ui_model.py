"""Small view helpers: filters, selection and recoverable editor drafts."""
import json
import pathlib
from .core import atomic_write, dumps, TOKENS, BridgeError

MODES=('待补译','缺漏补查','本次更新','已有译文','失败项','译名待核对','所有条目','已忽略')
FIELD_LABELS={'name':'名称','abName':'简称','title':'标题','desc':'说明','content':'正文',
              'flavor':'背景','dlg':'台词','teller':'说话人','summary':'摘要',
              'nameWithTitle':'称谓','place':'地点','chaptertitle':'章节','text':'正文','speaker':'说话人','displayName':'显示名称','statText':'属性说明'}

def matches(entry,mode,categories,query=''):
    if entry.category not in categories:return False
    if mode=='待补译' and not entry.needs_translation:return False
    if mode=='缺漏补查' and not (entry.coverage_gap and entry.status not in ('cached','ignored')):return False
    if mode=='本次更新' and not (entry.recommended and entry.status not in ('cached','ignored')):return False
    if mode=='已有译文' and entry.status!='cached':return False
    if mode=='失败项' and entry.status!='failed':return False
    if mode=='译名待核对' and not entry.consistency_note:return False
    if mode=='已忽略' and entry.status!='ignored':return False
    query=query.strip().casefold()
    return not query or query in '\n'.join((entry.file,entry.source,entry.target or '',entry.translation)).casefold()

def selected(entries,checked):
    return [e for e in entries if e.uid in checked and e.status not in ('cached','ignored')]

def preview(entry,limit=95):
    text=' '.join(TOKENS.sub(lambda m:'' if m.group(0).startswith('<') else m.group(0),entry.source).replace('\\n',' ').replace('\\r',' ').split())
    return text if len(text)<=limit else text[:limit-1]+'…'

class DraftStore:
    """Drafts are separate from validated translations and bound to source hashes."""
    def __init__(self,directory):
        self.path=pathlib.Path(directory)/'editor-drafts.json'
        self.rows={};self.error=''
        if self.path.exists():
            try:
                data=json.loads(self.path.read_text(encoding='utf-8-sig'))
                if not isinstance(data,dict) or data.get('version')!=1 or not isinstance(data.get('drafts'),dict):
                    raise ValueError()
                self.rows={k:v for k,v in data['drafts'].items()
                           if isinstance(k,str) and isinstance(v,dict) and isinstance(v.get('text'),str)
                           and isinstance(v.get('source_hash'),str)}
            except (ValueError,OSError):
                self.error='草稿文件无法读取，原文件已保留。'

    def get(self,entry):
        row=self.rows.get(entry.uid,{})
        return row.get('text') if row.get('source_hash')==entry.cache_hash else None

    def remember(self,entry,text):
        if text==entry.translation:self.discard(entry)
        else:self.rows[entry.uid]={'source_hash':entry.cache_hash,'text':text}

    def discard(self,entry):
        self.rows.pop(entry.uid,None)

    def save(self):
        if self.error:raise BridgeError(self.error)
        atomic_write(self.path,dumps({'version':1,'drafts':self.rows}))
