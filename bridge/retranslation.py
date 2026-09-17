"""Explicit retranslations: keep the previous result until a validated replacement exists."""
import dataclasses
import json
import pathlib
import time
import uuid
from .core import (BridgeError,Cancelled,check_cancel,atomic_write,dumps,ensure_plain_path,
                   legacy_rpg_id)
from .consistency import align_translations
from .provider import translate

def eligible(entry):
    return entry.status=='cached' and bool(entry.translation) and entry.translation_model!='human-reference'

def backup_selected(cache,entries):
    saved=[]
    with cache.connect() as con:
        for e in entries:
            legacy=legacy_rpg_id(e.file,e.tokens,e.path)
            rows=con.execute('SELECT uid,source_hash,source,translated,model,created FROM translations WHERE source_hash=? AND uid IN (?,?)',
                             (e.cache_hash,e.uid,legacy or e.uid)).fetchall()
            saved.append({'uid':e.uid,'source_hash':e.cache_hash,'file':e.file,'path':list(e.path),
                          'visible_translation':e.translation,'visible_model':e.translation_model,
                          'cache_rows':[dict(zip(('uid','source_hash','source','translated','model','created'),r)) for r in rows]})
    destination=ensure_plain_path(cache.directory/'retranslation-history'/
        (time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:12]+'.json'))
    atomic_write(destination,dumps({'version':1,'created':time.time(),'entries':saved}))
    return destination

def retranslate(entries,scan,cache,client,settings,stop=None,progress=lambda _:None):
    check_cancel(stop)
    current={e.uid:e for e in scan.entries}
    chosen={e.uid:current[e.uid] for e in entries
            if e.uid in current and e.cache_hash==current[e.uid].cache_hash and eligible(current[e.uid])}
    if not chosen:
        return {'success':0,'failed':0,'total':0,'backup':None}
    backup=backup_selected(cache,chosen.values())
    progress(f'已备份 {len(chosen)} 条旧译文；现在重新调用 API。备份：{backup}')
    # Isolate the run from stale AI canonical names, including unselected duplicates.
    # Original scan rows and raw caches remain available throughout cancellation.
    copies=[]
    for e in scan.entries:
        clone=dataclasses.replace(e,refs=dict(e.refs))
        if clone.status!='ignored' and (clone.uid in chosen or clone.translation_model not in ('manual','manual-glossary','human-reference')):
            clone.translation='';clone.translation_model='';clone.translation_created=0
            clone.status='pending';clone.error='';clone.retranslation_error=''
        copies.append(clone)
    work=dataclasses.replace(scan,entries=copies,status_terms={},status_alignment_changes=[],
        status_alignment_conflicts=[],consistency_index=None,consistency_terms={},
        consistency_term_index={},consistency_changes=[],consistency_conflicts=[],
        consistency_blocked=set(),language_knowledge=None,force_translation_ids=set(chosen))
    targets=[e for e in copies if e.uid in chosen]
    successful={}

    class Writer:
        directory=cache.directory
        def put(self,entry,value,model):
            if entry.uid not in chosen or entry.cache_hash!=chosen[entry.uid].cache_hash:
                raise BridgeError('重译结果与所选条目不匹配，保留旧译文')
            cache.put(entry,value,'retranslate:'+model)
            # The provider calls this under its worker-state lock, after validation.
            successful[entry.uid]=dataclasses.replace(entry)

    failure='重译未完成；旧译文已保留'
    try:
        stats=translate(targets,work,Writer(),client,settings,stop,progress)
        return {**stats,'backup':str(backup)}
    except Cancelled:
        failure='重译已停止；旧译文已保留'
        raise
    except Exception as exc:
        reason=str(exc)
        if getattr(client,'key',''):reason=reason.replace(client.key,'[密钥已隐藏]')
        failure='重译未完成；旧译文已保留：'+reason
        raise
    finally:
        for item in targets:
            original=chosen[item.uid]
            if item.uid in successful:
                replacement=successful[item.uid]
                for field in ('translation','translation_model','translation_created','status','error','retranslation_error'):
                    setattr(original,field,getattr(replacement,field))
            else:
                reason=('重译失败；旧译文已保留：'+item.error) if item.error else failure
                if getattr(client,'key',''):reason=reason.replace(client.key,'[密钥已隐藏]')
                cache.record_retranslation_failure(original,reason)
        align_translations(scan)
