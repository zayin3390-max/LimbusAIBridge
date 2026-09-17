"""Versioned local scan snapshots. Loading never inspects the game directory."""
import dataclasses
import gzip
import hashlib
import sqlite3
import json
import pathlib
import time
from .core import Scan,Entry,BridgeError,atomic_write

FORMAT = 1
# Increment when scan classification changes, independently of UI/app versions.
SCAN_RULES = 1
NAME = 'scan-cache.json.gz'
FIELDS = ('source_lang','sources','bases','fingerprints','warnings','version','signature',
          'preserved','exclusions','resource_groups','status_alignment_changes','status_alignment_conflicts',
          'consistency_changes','consistency_conflicts')
MAX_BYTES = 512*1024*1024

def _path(value):
    return pathlib.Path(value).absolute()

def _scope(game,baseline,lang):
    game=_path(game)
    base=_path(baseline or game/'LimbusCompany_Data/Lang/LLC_zh-CN')
    return str(game).casefold(),str(base).casefold(),lang

def translation_stamp(directory):
    path=(pathlib.Path(directory)/'translations.sqlite3').absolute()
    if not path.exists():return ''
    digest=hashlib.sha256()
    connection=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)
    try:
        for row in connection.execute('SELECT uid,source_hash,translated,model,created FROM translations ORDER BY uid,source_hash'):
            digest.update(json.dumps(row,ensure_ascii=False,separators=(',',':')).encode('utf-8'))
            digest.update(b'\n')
    finally:connection.close()
    return digest.hexdigest()

def save_scan(scan,directory):
    content={key:getattr(scan,key) for key in FIELDS}
    content.update(format=FORMAT,rules=SCAN_RULES,saved_at=time.time(),translations_stamp=translation_stamp(directory),game=str(scan.game),
                   baseline=str(scan.baseline),entries=[dataclasses.asdict(e) for e in scan.entries])
    for key in ('source_paths','base_paths'):
        content[key]={k:[rel,str(p)] for k,(rel,p) in getattr(scan,key).items()}
    raw=json.dumps(content,ensure_ascii=False,separators=(',',':')).encode('utf-8')
    atomic_write(pathlib.Path(directory)/NAME,gzip.compress(raw,compresslevel=1,mtime=0))
    return content['saved_at']

def _paths(data,root):
    result={}
    for key,pair in data.items():
        rel,raw=pair
        name=pathlib.PurePosixPath(rel)
        if name.is_absolute() or '..' in name.parts or '\\' in rel or ':' in rel:
            raise ValueError('invalid relative resource path')
        path=_path(raw)
        if not path.is_relative_to(root) or key!=rel.casefold():
            raise ValueError('resource path outside snapshot scope')
        result[key]=(rel,path)
    return result

def load_scan(directory,game,baseline=None,lang='en',cache=None,*,prepare=False):
    path=pathlib.Path(directory)/NAME
    if not path.exists():return None
    try:
        # Bounded JSON, not executable object deserialization.
        with gzip.open(path,'rb') as stream:
            raw=stream.read(MAX_BYTES+1)
        if len(raw)>MAX_BYTES:raise ValueError('snapshot too large')
        data=json.loads(raw)
        if data['format']!=FORMAT or data['rules']!=SCAN_RULES:
            raise BridgeError('扫描缓存版本已变更，请点击“扫描更新”；原缓存已保留。')
        if _scope(game,baseline,lang)!=_scope(data['game'],data['baseline'],data['source_lang']):
            return None
        root=_path(game);base=_path(data['baseline'])
        srcroot=root/'LimbusCompany_Data/Assets/Resources_moved/Localize'/lang
        source_paths=_paths(data['source_paths'],srcroot)
        base_paths=_paths(data['base_paths'],base)
        if set(data['sources'])-source_paths.keys() or set(data['bases'])-base_paths.keys():
            raise ValueError('missing resource path')
        entries=[];saved_values={}
        allowed={f.name for f in dataclasses.fields(Entry)}
        for item in data['entries']:
            if set(item)-allowed:raise ValueError('unknown entry fields')
            item['tokens']=tuple(tuple(part) for part in item['tokens'])
            item['path']=tuple(item['path'])
            entry=Entry(**item)
            if entry.file.casefold() not in source_paths:raise ValueError('unknown entry file')
            saved_values[entry.uid]=(entry.translation,entry.translation_model,entry.translation_created,entry.consistency_note,entry.status,entry.error)
            # Translation DB is authoritative, including un-ignore since saving.
            entry.status='pending';entry.translation='';entry.translation_model=''
            entry.translation_created=0.0;entry.consistency_note='';entry.retranslation_error=''
            entries.append(entry)
        scan=Scan(game=root,baseline=base,entries=entries,source_paths=source_paths,
                  base_paths=base_paths,**{k:data[k] for k in FIELDS if k!='resource_groups'})
        scan.resource_groups=data['resource_groups']
        if cache is not None:
            cache.load(scan.entries)
            scan.consistency_glossary_path=cache.directory/'glossary.json'
        # Alignment can select a newer canonical row from a different entity ID.
        # Compare the complete translation table, not one row's timestamp.
        unchanged=cache is None or data.get('translations_stamp')==translation_stamp(cache.directory)
        if unchanged:
            for entry in scan.entries:
                text,model,created,note,status,error=saved_values[entry.uid]
                ignored=entry.status=='ignored' or (cache is None and status=='ignored')
                entry.translation=text;entry.translation_model=model;entry.translation_created=created
                entry.consistency_note=note;entry.error=error
                entry.status=('ignored' if ignored else ('cached' if text else 'pending') if status=='ignored' else status)
        # Changed translations need fresh cross-entity alignment from cached trees;
        # the normal unchanged startup restores already audited results directly.
        if prepare or not unchanged:
            from .consistency import align_translations
            align_translations(scan)
        return scan,float(data['saved_at'])
    except BridgeError:
        raise
    except (ValueError,TypeError,KeyError,OSError,EOFError,OverflowError) as exc:
        raise BridgeError('无法读取扫描缓存，请点击“扫描更新”；原缓存已保留。') from exc
