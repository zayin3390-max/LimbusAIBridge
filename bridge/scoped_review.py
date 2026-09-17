"""Local, evidence-backed abbreviation decisions scoped to one unchanged scene."""
import hashlib
import json
import pathlib
from .core import BridgeError,validate_translation

NAME='reviewed-abbreviations.json'

def context_hash(entry,neighbors):
    raw=json.dumps([entry.uid,entry.source,entry.refs,neighbors],ensure_ascii=False,sort_keys=True)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()

def load(path):
    if not path:return {}
    try:
        obj=json.loads(pathlib.Path(path).with_name(NAME).read_text(encoding='utf-8-sig'))
        return obj.get('entries',{}) if obj.get('version')==1 and isinstance(obj.get('entries'),dict) else {}
    except (OSError,ValueError,AttributeError):return {}

def locks(records,entry,neighbors,codes):
    row=records.get(entry.uid,{})
    if not isinstance(row,dict) or row.get('source_hash')!=entry.cache_hash or row.get('context_hash')!=context_hash(entry,neighbors):
        return {}
    if not isinstance(row.get('evidence'),str) or not row['evidence'].strip():return {}
    values=row.get('locks',{})
    if not isinstance(values,dict):return {}
    result={}
    for code,value in values.items():
        if code not in codes or not isinstance(value,str):continue
        try:validate_translation(code,value)
        except BridgeError:continue
        result[code]=value
    return result

# Short faction names occur in chapter dialogue, but "Rouge" also denotes a
# color in unrelated combat resources. Reference-language identity is required.
SHORT_NAMES=(
    ('Le Noir',('Noir','Noirs'),('르누아르','ル・ノワール')),
    ('Le Rouge',('Rouge','Rouges'),('르루주','ル・ルージュ')),
    ('Grand Magasin Sisyphe',('Grand Magasin',),('시지프','シーシュポス')),
)

def short_name_locks(scan,entry):
    import re
    refs='\n'.join(str(x) for x in entry.refs.values())
    result={}
    for canonical,aliases,evidence in SHORT_NAMES:
        term=scan.consistency_terms.get(canonical)
        if not term or not any(cue in refs for cue in evidence):continue
        # The full name already has its own canonical reference mechanism.
        text=entry.source.replace(canonical,'')
        # French establishment names retain their own complete translation;
        # du Noir/du Rouge is not a freestanding faction abbreviation.
        text=re.sub(r'\bdu (?:Noir|Rouge)\b','',text)
        for alias in aliases:
            if re.search(r'(?<![A-Za-z])'+re.escape(alias)+r'(?![A-Za-z])',text):
                result[alias]=term['translation']
    return result
