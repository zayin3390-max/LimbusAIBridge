"""Align duplicate status resources by identity, field, and exact source text.

Only Bufs/BattleKeywords tables participate. Human files and raw cache rows are
never rewritten here; alignment applies to the in-memory scan and generated pack.
"""
import collections
import pathlib
import re
from .core import BridgeError, classify, flatten, stable_id, validate_translation

STATUS_FIELDS={'name','desc','summary','undefined','flavor'}
STATUS_FILE=re.compile(r'^(bufs|battlekeywords)(?:[-_].+)?\.json$',re.I)


def status_slot(rel,tokens):
    path=pathlib.PurePosixPath(rel)
    if len(path.parts)!=1 or not STATUS_FILE.fullmatch(path.name): return None
    if (len(tokens)!=3 or tokens[0]!=('key','dataList') or
        tokens[1][:2]!=('row','id') or tokens[2][0]!='key' or tokens[2][1] not in STATUS_FIELDS):
        return None
    return str(tokens[1][2]),tokens[2][1]


def rank_file(rel):
    name=rel.casefold()
    # Prefer the existing inline status wording, then a deterministic file order.
    return (0 if name=='bufs.json' else 1 if name.startswith('bufs') else
            2 if name=='battlekeywords.json' else 3,name)


def align_status_terms(scan):
    entries={e.uid:e for e in scan.entries}
    groups=collections.defaultdict(list)
    name_sources=collections.defaultdict(set)
    for key,source in scan.sources.items():
        rel=scan.source_paths[key][0]
        if not STATUS_FILE.fullmatch(rel): continue
        base={t:v for t,_,_,v in flatten(scan.bases[key])} if key in scan.bases else {}
        for tokens,path,field,text in flatten(source):
            slot=status_slot(rel,tokens)
            if not slot or not isinstance(text,str) or not text.strip(): continue
            if field=='name':name_sources[slot[0]].add(text)
            uid=stable_id(rel,tokens)
            target=base.get(tokens)
            human=(isinstance(target,str) and target.strip() and
                   classify(text,target,tokens in base) is None)
            groups[slot+(text,)].append({'file':rel,'uid':uid,'path':path,
                                        'human':target if human else None,'entry':entries.get(uid)})
    changed=[];conflicts=[];canonical=[];names=collections.defaultdict(list)
    for (identity,field,source),slots in sorted(groups.items()):
        human_values={s['human'] for s in slots if s['human'] is not None}
        editable=[s for s in slots if s['entry'] is not None and s['entry'].status!='ignored'
                  and (s['entry'].status=='cached' or s['entry'].candidate)]
        if len(human_values)>1:
            conflicts.append({'id':identity,'field':field,'source':source,
                              'reason':'human_conflict','values':sorted(human_values),
                              'needs_review':bool(editable)})
            continue
        origin='';value='';model='';created=0.0
        if human_values:
            value=next(iter(human_values));origin='human'
            model='human-reference'
            chosen=next(s for s in slots if s['human']==value)
        else:
            candidates=[]
            for s in slots:
                e=s['entry']
                if e is None or e.status!='cached' or not e.translation: continue
                try: validate_translation(source,e.translation)
                except BridgeError: continue
                candidates.append(s)
            if not candidates: continue
            manual=[s for s in candidates if s['entry'].translation_model=='manual']
            chosen=min(manual,key=lambda s:(-s['entry'].translation_created,rank_file(s['file']))) if manual else min(candidates,key=lambda s:rank_file(s['file']))
            e=chosen['entry'];value=e.translation
            model=e.translation_model;created=e.translation_created
            origin='manual' if manual else 'cache'
        try: validate_translation(source,value)
        except BridgeError:
            if editable and len(slots)>1:
                conflicts.append({'id':identity,'field':field,'source':source,
                                  'reason':'protected_format','values':[value]})
            continue
        item={'id':identity,'field':field,'source':source,'translation':value,
              'origin':origin,'from_file':chosen['file']}
        canonical.append(item)
        if field=='name': names[identity].append(item)
        # A single table's existing translation is useful context, but not a
        # reason to synthesize unrelated fields or overwrite ignored entries.
        if len({s['file'].casefold() for s in slots})<2: continue
        for s in editable:
            e=s['entry']
            if e.translation==value and e.status=='cached': continue
            change={**item,'file':e.file,'path':list(e.path),'uid':e.uid,
                    'previous':e.translation,'reused':e.status!='cached'}
            changed.append(change)
            e.translation=value;e.status='cached';e.error=''
            e.translation_model=model;e.translation_created=created
    # IDs with differing current source names are ambiguous; never expose one
    # arbitrary name as authoritative context for them.
    scan.status_terms={identity:items[0] for identity,items in names.items()
                       if len(name_sources[identity])==1 and len({(r['source'],r['translation']) for r in items})==1}
    scan.status_alignment_conflicts=conflicts
    known={(r['uid'],r['previous'],r['translation']) for r in scan.status_alignment_changes}
    for r in changed:
        key=(r['uid'],r['previous'],r['translation'])
        if key not in known:scan.status_alignment_changes.append(r);known.add(key)
    return {'changed':len(changed),'reused':sum(r['reused'] for r in changed),
            'conflicts':len(conflicts),'canonical':canonical}


def status_context(scan,entries):
    wanted=set()
    for e in entries:
        wanted.update(re.findall(r'\[([A-Za-z_][A-Za-z0-9_.:-]*)\]',e.source))
        slot=status_slot(e.file,e.tokens)
        if slot: wanted.add(slot[0])
    return {identity:scan.status_terms[identity]['translation']
            for identity in sorted(wanted) if identity in scan.status_terms}
