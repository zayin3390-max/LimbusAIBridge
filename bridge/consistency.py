"""Consistency across resources, named labels, and explicit term references."""
import collections
import json
import pathlib
import re
from .core import (BridgeError,TOKENS,HAN,flatten,stable_id,validate_translation,
                   classify,language_files,read_json)
from .proper_names import names as protected_names
from .resource_schema import rpg_kind
from .lexicon import reserved
from .status_terms import align_status_terms,status_slot,rank_file

PRIMARY={'character','personality','enemy','ego','skill','passive','announcer',
         'buf','keyword','model','unitkeyword','panic','chapter','stage','theater','gacha'}
FALLBACK=(('battlekeywords','keyword'),('bufs','buf'),('skills','skill'),('passives','passive'),
          ('personalities','personality'),('characters','character'),('enemies','enemy'),
          ('egos','ego'),('announcer','announcer'),('scenariomodelcodes','model'),
          ('unitkeyword','unitkeyword'),('panicinfo','panic'),('stagechapter','chapter'),
          ('stagenode','stage'),('storytheatermain','theater'),('gachatitle','gacha'))
NAME_FIELDS={'name','abName','nickName','nameWithTitle','teller','title','place','chaptertitle','panicName','speaker','displayName'}
QUOTE=re.compile(r'["“「『]([^"”」』\r\n]+)["”」』]')
WORDS=re.compile(r'[A-Za-zÀ-ÖØ-öø-ÿ0-9_]+')


def family(scan,rel):
    if rpg_kind(rel):return 'rpg-'+rpg_kind(rel)+':'+rel.casefold()
    if rel.lower().startswith('storydata/'):return 'story:'+rel.casefold()
    name=pathlib.PurePosixPath(rel).name.casefold()
    for prefix,kind in FALLBACK:
        if name.startswith(prefix):return kind
    group=scan.resource_groups.get(rel.casefold())
    return group if group and group!='ui' else 'file:'+rel.casefold()


def role(kind,field):
    if field in ('teller','speaker'):return 'actor'
    if kind.startswith('rpg-npc:') and field=='displayName':return 'actor'
    if kind in ('character','model') and field in ('name','abName'):return 'actor'
    if kind=='enemy' and field in ('name','abName'):return 'enemy'
    if kind=='personality' and field in ('name','nameWithTitle'):return 'actor'
    if field=='name' and kind in ('buf','keyword'):return 'status'
    if kind=='panic' and field=='panicName':return 'status'
    if kind in ('skill','passive','ego') and field=='name':return kind
    if kind=='unitkeyword' and field=='content':return 'affiliation'
    if kind in ('chapter','theater') and field in ('chaptertitle','title'):return 'chapter'
    if field in NAME_FIELDS:return 'label'
    if kind=='gacha' and field=='content':return 'gacha'
    return None


def _tail(tokens,kind):
    result=[];i=2
    while i<len(tokens):
        if (kind=='skill' and tokens[i]==('key','levelList') and i+1<len(tokens)
            and tokens[i+1][:2]==('row','level')):
            i+=2;continue
        result.append(tokens[i]);i+=1
    return tuple(result)


def _rank(slot):
    kind=slot['family'];e=slot['entry']
    authoritative=0 if kind in PRIMARY else 10
    level=next((int(t[2]) for t in slot['tokens'] if t[:2]==('row','level') and str(t[2]).isdigit()),0)
    return authoritative,rank_file(slot['file']) if kind in ('buf','keyword') else (2,slot['file'].casefold()),-level,slot['uid']


def _make_index(scan):
    entries={e.uid:e for e in scan.entries}
    paths={}
    for lang in ('kr','en','jp'):
        root=scan.game/'LimbusCompany_Data/Assets/Resources_moved/Localize'/lang
        if lang!=scan.source_lang and root.is_dir():paths[lang]=language_files(root,lang)
    ref_cache={}
    def references(key,tokens):
        refs={}
        for lang,files in paths.items():
            pair=(lang,key)
            if key not in files:continue
            if pair not in ref_cache:
                try:ref_cache[pair]={t:v for t,_,_,v in flatten(read_json(files[key][1]))}
                except (BridgeError,OSError):ref_cache[pair]={}
            value=ref_cache[pair].get(tokens)
            if isinstance(value,str) and value.strip():refs[lang]=value.strip()
        return tuple(sorted(refs.items()))
    index={'identity':collections.defaultdict(list),'labels':collections.defaultdict(list),'slots':[]}
    wanted={e.source for e in scan.entries if role(family(scan,e.file),e.field)}
    for key,source in scan.sources.items():
        rel=scan.source_paths[key][0];kind=family(scan,rel)
        base={t:v for t,_,_,v in flatten(scan.bases[key])} if key in scan.bases else {}
        for tokens,path,field,text in flatten(source):
            if not isinstance(text,str) or not text.strip() or len(tokens)<3 or tokens[0]!=('key','dataList') or (tokens[1][:2]!=('row','id') and not (rpg_kind(rel) and tokens[1][:2]==('row','key'))):continue
            uid=stable_id(rel,tokens);e=entries.get(uid);label=role(kind,field)
            if field not in NAME_FIELDS and e is None and kind not in PRIMARY:continue
            target=base.get(tokens)
            human=target if isinstance(target,str) and target.strip() and classify(text,target,tokens in base) is None else None
            slot={'uid':uid,'file':rel,'family':kind,'tokens':tokens,'path':path,'field':field,
                  'source':text,'human':human,'entry':e,'role':label}
            # All stable resource fields are eligible; narrative rows retain their
            # file and row identity, and coin indexes are never discarded.
            identity=(kind,str(tokens[1][2]),_tail(tokens,kind),text)
            index['identity'][identity].append(slot)
            if label and (e is not None or kind in PRIMARY or text in wanted):
                refs=references(key,tokens)
                # Cross-ID aliases require matching reference-language evidence.
                # Without it, keep different IDs separate, except repeated story labels.
                scope=('refs',refs) if refs else ('story',rel.casefold()) if kind.startswith('story:') else ('entity',kind,str(tokens[1][2]))
                index['labels'][(label,text,scope)].append(slot)
                slot['refs']=refs
                index['slots'].append(slot)
    return index


def _choose(slots,custom,issues,kind):
    source=slots[0]['source']
    humans=[s for s in slots if s['human'] is not None]
    candidates=[]
    for s in slots:
        e=s['entry']
        if e is not None and e.status=='cached' and e.translation:
            try:validate_translation(source,e.translation)
            except BridgeError:continue
            candidates.append(s)
    editable=any(s['entry'] is not None and (s['entry'].status=='cached' or s['entry'].candidate) for s in slots)
    chosen=None;value='';model='';created=0.0
    if humans:
        priority=min(_rank(s)[0] for s in humans)
        best=[s for s in humans if _rank(s)[0]==priority]
        values={s['human'] for s in best}
        if len(values)>1:
            if editable:issues.append({'kind':kind,'source':source,'reason':'人工译名存在多个候选','values':sorted(values),'files':sorted({s['file'] for s in slots}),'uids':[s['uid'] for s in slots if s['entry'] is not None]})
            return None
        chosen=min(best,key=_rank);value=chosen['human'];model='human-reference'
    elif source in custom:
        chosen=min(slots,key=_rank);value=custom[source];model='manual-glossary'
    elif candidates:
        manual=[s for s in candidates if s['entry'].translation_model in ('manual','manual-glossary')]
        revised=[s for s in candidates if s['entry'].translation_model.startswith('retranslate:')]
        if manual:chosen=min(manual,key=lambda s:(-s['entry'].translation_created,_rank(s)))
        elif revised:chosen=min(revised,key=lambda s:(-s['entry'].translation_created,_rank(s)))
        else:
            priority=min(_rank(s)[0] for s in candidates)
            best=[s for s in candidates if _rank(s)[0]==priority]
            counts=collections.Counter(s['entry'].translation for s in best)
            chosen=min(best,key=lambda s:(-counts[s['entry'].translation],_rank(s)))
        e=chosen['entry'];value=e.translation;model=e.translation_model;created=e.translation_created
    if chosen is None:return None
    try:validate_translation(source,value)
    except BridgeError:return None
    return {'source':source,'translation':value,'model':model,'created':created,'from_file':chosen['file'],'role':chosen['role']}


def _apply(scan,slots,term,kind):
    if term is None:return
    for s in slots:
        e=s['entry']
        if e is None or e.uid in scan.consistency_blocked or e.status=='ignored' or not (e.status=='cached' or e.candidate):continue
        if e.uid in scan.force_translation_ids and e.status!='cached':continue
        if e.translation==term['translation'] and e.status=='cached':continue
        change={'kind':kind,'uid':e.uid,'file':e.file,'path':list(e.path),'field':e.field,
                'source':e.source,'previous':e.translation,'translation':term['translation'],
                'from_file':term['from_file'],'reused':e.status!='cached'}
        scan.consistency_changes.append(change)
        e.translation=term['translation'];e.status='cached';e.error=''
        e.translation_model=term['model'];e.translation_created=term['created']


def _matches(text,term):
    before=r'(?<![A-Za-zÀ-ÖØ-öø-ÿ0-9_])' if term and term[0].isalnum() else ''
    after=r'(?![A-Za-zÀ-ÖØ-öø-ÿ0-9_])' if term and term[-1].isalnum() else ''
    return list(re.finditer(before+re.escape(term)+after,text))


def _plain(text):
    return TOKENS.sub(lambda m:'\x00'*len(m.group()),text)


def _term_index(terms):
    result=collections.defaultdict(set)
    for term in terms:
        word=WORDS.match(term)
        result[word.group() if word else ''].add(term)
    return result


def _relevant(text,index):
    result=set(index.get('',()))
    for word in set(WORDS.findall(text)):result.update(index.get(word,()))
    return result


def _reference_allowed(entry,source,term):
    if reserved(source):return False
    if source==entry.source and entry.field in NAME_FIELDS:return True
    quoted=any(m.group(1).strip()==source for m in QUOTE.finditer(_plain(entry.source)))
    narrative=(entry.file.lower().startswith(('storydata/','rpgsystem/','personalityvoicedlg/','battleannouncerdlg/'))
               or entry.field=='flavor')
    # A skill called "No." is not evidence that ordinary quoted dialogue
    # invokes it. Short enemy/part labels likewise cannot define prose nouns.
    if quoted and not (narrative and term['role'] in ('skill','passive','status','enemy')
                       and len(WORDS.findall(source))<2):return True
    if term['role'] in ('actor','affiliation','chapter'):return True
    return term['role'] in ('label','enemy') and len(WORDS.findall(source))>=2 and not source.endswith(('.', '!', '?'))


def _references(entry,terms,term_index,*,include_components=False):
    text=_plain(entry.source);covered=[];result=[]
    for source in sorted(_relevant(text,term_index),key=lambda v:(-len(v),v)):
        if len(source)<3 or not _reference_allowed(entry,source,terms[source]):continue
        matches=_matches(text,source)
        if matches and (include_components or any(not any(a<=m.start() and m.end()<=b for a,b in covered) for m in matches)):
            result.append(source)
        covered.extend((m.start(),m.end()) for m in matches)
    return result


def _replace_prose(entry,terms,reverse,issues,term_index=None):
    source=_plain(entry.source);text=entry.translation;replacements=[]
    exact=terms.get(entry.source)
    if exact and exact['model']=='human-reference' and text==exact['translation']:return text
    # A longer, already canonical name shields its interior from shorter
    # aliases, including deliberate wording in an existing human name.
    protected=[]
    for original in _references(entry,terms,term_index or _term_index(terms)):
        term=terms[original]
        if original!=entry.source or term['model']=='human-reference':
            protected.extend((m.start(),m.end(),len(original)) for m in re.finditer(re.escape(term['translation']),_plain(text)))
    # Multiline identity labels retain layout while matching an entire named
    # component by position (e.g. faction on a separate title line).
    if entry.field in NAME_FIELDS:
        left=list(re.finditer(r'[^\r\n]+',entry.source));right=list(re.finditer(r'[^\r\n]+',text))
        if len(left)==len(right) and len(left)>1:
            for a,b in zip(left,right):
                term=terms.get(a.group().strip())
                if term and not reserved(a.group().strip()) and b.group().strip()!=term['translation'] and not TOKENS.search(b.group()):
                    leading=len(b.group())-len(b.group().lstrip())
                    trailing=len(b.group())-len(b.group().rstrip())
                    replacements.append((b.start()+leading,b.end()-trailing,term['translation']))
    source_quotes=list(QUOTE.finditer(source));target_quotes=list(QUOTE.finditer(_plain(text)))
    if len(source_quotes)==len(target_quotes):
        for a,b in zip(source_quotes,target_quotes):
            term=terms.get(a.group(1).strip())
            if (term and _reference_allowed(entry,a.group(1).strip(),term) and b.group(1)!=term['translation']
                and not (reverse.get(b.group(1).strip(),set()) - {a.group(1).strip()})
                and not any(size>=len(a.group(1).strip()) and start<b.end(1) and b.start(1)<end for start,end,size in protected)):
                replacements.append((b.start(1),b.end(1),term['translation']))
    # Unquoted replacement is limited to a known unambiguous alias whose
    # original term is actually present in this source field.
    for original in _references(entry,terms,term_index or _term_index(terms),include_components=True):
        term=terms[original]
        for variant in sorted(term['variants'],key=lambda v:(-len(v),v)):
            if variant==term['translation'] or (len(variant)<3 and variant not in term.get('reviewed_aliases',())) or len(reverse.get(variant,set()))!=1:continue
            for match in _matches(_plain(text),variant) if variant.isascii() else re.finditer(re.escape(variant),_plain(text)):
                if (not any(start<match.end() and match.start()<end for start,end,_ in replacements)
                    and not any(size>=len(original) and start<match.end() and match.start()<end for start,end,size in protected)):
                    replacements.append((match.start(),match.end(),term['translation']))
    if not replacements:return text
    for start,end,value in sorted(replacements,reverse=True):text=text[:start]+value+text[end:]
    try:validate_translation(entry.source,text)
    except BridgeError:
        issues.append({'kind':'reference','uid':entry.uid,'file':entry.file,'source':entry.source,
                       'reason':'术语替换未通过数字或格式校验，保留原译文'})
        return entry.translation
    return text


def _contains_name(target,source,term_source,canonical):
    if canonical in target:return True
    # A display-only bracket qualifier may be moved inside a Chinese name.
    # Ignore it for diagnostics only; never remove it from the translation.
    qualifier=re.escape(term_source)+r'\s+\[[^\]\r\n]*\s[^\]\r\n]*\]'
    if re.search(qualifier,source):
        strip=lambda v:re.sub(r'\[[^\]\r\n]+\]','',v)
        return strip(canonical) in strip(target)
    return False


def align_translations(scan):
    initial=align_status_terms(scan)
    blocked={(r['id'],r['field'],r['source']) for r in scan.status_alignment_conflicts}
    scan.consistency_blocked={e.uid for e in scan.entries if status_slot(e.file,e.tokens)
                              and status_slot(e.file,e.tokens)+(e.source,) in blocked}
    if scan.consistency_index is None:scan.consistency_index=_make_index(scan)
    index=scan.consistency_index;issues=[];custom={}
    if scan.consistency_glossary_path:
        path=pathlib.Path(scan.consistency_glossary_path)
        if path.exists():
            try:custom=json.loads(path.read_text(encoding='utf-8-sig'))
            except (ValueError,OSError):custom={}
            if not isinstance(custom,dict):custom={}
            custom={k:v for k,v in custom.items() if isinstance(k,str) and isinstance(v,str) and k and v}
    before=len(scan.consistency_changes)
    for identity,slots in index['identity'].items():
        if len(slots)>1:_apply(scan,slots,_choose(slots,custom,issues,'entity'),'entity')
    # Merge definition and dialogue labels only when both their source and
    # reference-language names agree. A source-only homonym is not sufficient.
    by_signature=collections.defaultdict(list)
    for (label,source,scope),slots in index['labels'].items():
        by_signature[(source,scope)].extend(slots)
    for (source,scope),slots in by_signature.items():
        labels={s['role'] for s in slots}
        compatible=(len(labels)==1 or labels<={'actor','enemy','label'} or labels<={'affiliation','label'} or labels<={'chapter','label'})
        if compatible:
            _apply(scan,slots,_choose(slots,custom,issues,'label'),'label')
        else:
            for label in labels:
                subset=[s for s in slots if s['role']==label]
                _apply(scan,subset,_choose(subset,custom,issues,'label'),'label')
    # Build a global reference bank only for names that resolve to one wording
    # across all known senses. Ambiguous homonyms remain scoped to their fields.
    bank=collections.defaultdict(list)
    for key,slots in index['labels'].items():
        term=_choose(slots,custom,issues,'label')
        if term:
            term['variants']={s['human'] for s in slots if s['human']}
            term['variants'].update(s['entry'].translation for s in slots if s['entry'] is not None and s['entry'].translation)
            term['variants'].add(term['source'])
            bank[term['source']].append(term)
    terms={}
    for source,rows in bank.items():
        if any(r[2]==source for r in blocked) or len({r['translation'] for r in rows})!=1:continue
        term=dict(rows[0]);term['variants']=set().union(*(r['variants'] for r in rows))
        if any(r['role']=='actor' for r in rows):term['role']='actor'
        # Raw historical AI spellings remain available as aliases after the
        # in-memory label rows have already been harmonized.
        for change in scan.consistency_changes+scan.status_alignment_changes:
            if change['source']==source and change['previous']:term['variants'].add(change['previous'])
        if not protected_names(source) and len(source)<=240 and not TOKENS.search(source):
            terms[source]=term
    # These are reviewed aliases, not preferred translations. The canonical
    # name still comes from the current local human pack or reviewed term.
    from .reviewed_aliases import ALIASES
    for source,term in terms.items():
        term['reviewed_aliases']=set(ALIASES.get(source,()))
        term['variants'].update(term['reviewed_aliases'])
    reverse=collections.defaultdict(set)
    for source,t in terms.items():
        for v in t['variants']:reverse[v].add(source)
    term_index=_term_index(terms)
    from types import SimpleNamespace
    for source in sorted(terms,key=lambda v:(len(v),v)):
        term=terms[source]
        if term['model']=='human-reference':continue
        probe=SimpleNamespace(source=source,translation=term['translation'],field='title',uid='',file='')
        revised=_replace_prose(probe,terms,reverse,issues,term_index)
        if revised!=term['translation']:
            term['variants'].add(term['translation']);term['translation']=revised
            slots=[s for s in index['slots'] if s['source']==source]
            _apply(scan,slots,term,'composite')
    reverse=collections.defaultdict(set)
    for source,t in terms.items():
        for v in t['variants']:reverse[v].add(source)
    for e in scan.entries:
        if e.status!='cached' or not e.translation or e.uid in scan.consistency_blocked:continue
        revised=_replace_prose(e,terms,reverse,issues,term_index)
        if revised!=e.translation:
            _apply(scan,[{'entry':e}],{'translation':revised,'model':e.translation_model,
                   'created':e.translation_created,'from_file':'统一术语表'},'reference')
    for e in scan.entries:
        if e.status!='cached' or not e.translation or e.uid in scan.consistency_blocked:continue
        source=_plain(e.source);target=_plain(e.translation)
        for term_source in _references(e,terms,term_index):
            term=terms[term_source]
            if not _contains_name(target,e.source,term_source,term['translation']):
                issues.append({'kind':'reference_review','uid':e.uid,'file':e.file,'field':e.field,
                    'path':list(e.path),'source':e.source,'translation':e.translation,'term':term_source,
                    'expected':term['translation'],'reason':'正文未找到统一译名，可能是新译法或语境省略，需核对'})
    # Recompute current canonical labels after composite labels were repaired.
    scan.consistency_terms={s:{'source':s,'translation':t['translation'],'role':t['role']} for s,t in terms.items()}
    scan.consistency_term_index=_term_index(scan.consistency_terms)
    from .language_knowledge import align_language
    align_language(scan,issues)
    seen=set();unique=[]
    for issue in issues:
        key=json.dumps(issue,sort_keys=True,ensure_ascii=False)
        if key not in seen:unique.append(issue);seen.add(key)
    scan.consistency_conflicts=unique
    by_uid={e.uid:e for e in scan.entries}
    for e in scan.entries:e.consistency_note=''
    for issue in unique:
        for uid in issue.get('uids',[]) + ([issue['uid']] if 'uid' in issue else []):
            if uid in by_uid:
                note=issue['reason']
                if issue.get('term'):note+='：'+issue['term']+' → '+issue['expected']
                by_uid[uid].consistency_note=note
    return {'changed':initial['changed']+len(scan.consistency_changes)-before,
            'reused':initial['reused']+sum(r['reused'] for r in scan.consistency_changes[before:]),
            'conflicts':initial['conflicts']+len(unique)}


def locked_terms(scan,entry):
    result={}
    text=_plain(entry.source)
    for source in _references(entry,scan.consistency_terms,scan.consistency_term_index):
        term=scan.consistency_terms[source]
        result[source]=term['translation']
    from .language_knowledge import knowledge
    reviewed=knowledge(scan).locks(entry)
    # A complete, identified human name wins over a generic concept inside it.
    # Keep the concept if another occurrence lies outside that full name.
    for source,value in reviewed.items():
        matches=_matches(_plain(entry.source),source)
        enclosing=[(m.start(),m.end()) for outer in result if len(outer)>len(source)
                   for m in _matches(_plain(entry.source),outer)]
        if matches and all(any(a<=m.start() and m.end()<=b for a,b in enclosing) for m in matches):
            continue
        result[source]=value
    return result

def export_consistency_report(scan,directory):
    import csv
    import io
    from .core import atomic_write
    changes=scan.status_alignment_changes+scan.consistency_changes
    body=['# 译名一致性检查','',
          '覆盖技能等级、人格、E.G.O、敌人、被动、状态、剧情人名/称谓/地点、章节和正文引用。',
          '只统一有实体标识或参考语种对应证据的术语；普通对白的语境差异保留。','',
          f'已处理 {len({r["uid"] for r in changes})} 个字段；需核对 {len(scan.consistency_conflicts)} 个问题。','',
          '## 需要核对','']
    for i,r in enumerate(scan.consistency_conflicts,1):
        body.extend([f'{i}. {r["reason"]}',f'   文件：{r.get("file",", ".join(r.get("files",[])))}',
                     f'   原文：{r.get("source","")}'])
        if r.get('term'):body.append(f'   统一术语：{r["term"]} → {r["expected"]}')
        if r.get('translation'):body.append(f'   当前译文：{r["translation"]}')
        if r.get('values'):body.append('   候选译名：'+' / '.join(r['values']))
        body.append('')
    if not scan.consistency_conflicts:body.append('未发现需要人工核对的术语冲突。')
    body.extend(['','详细变更见同目录“译名对齐清单.csv”。',
                 '译名一致性检查不等于完整语义审校；不改变原汉化或原始缓存。'])
    atomic_write(pathlib.Path(directory)/'译名一致性.md',('\n'.join(body)+'\n').encode('utf-8'))
    buf=io.StringIO(newline='');writer=csv.writer(buf)
    writer.writerow(['文件','字段','原文','原译文','统一译文','依据/来源'])
    def safe(v):
        text=str(v or '')
        return "'"+text if text.startswith(('=','+','-','@')) else text
    for r in changes:writer.writerow([safe(r.get(k,'')) for k in ['file','field','source','previous','translation','from_file']])
    atomic_write(pathlib.Path(directory)/'译名对齐清单.csv',buf.getvalue().encode('utf-8-sig'))


def name_dependencies(entries,scan):
    """Only move user-selected, referenced definitions ahead of their bodies."""
    pending={e.uid:e for e in entries if e.status not in ('cached','ignored')}
    definitions={}
    terms={}
    for slot in scan.consistency_index['slots']:
        e=slot['entry'];source=slot['source']
        if e is not None and e.uid in pending and len(source)<=240 and not TOKENS.search(source):
            definitions[e.uid]=e
            terms[source]={'role':slot['role']}
    if not definitions:return []
    index=_term_index(terms);needed=set()
    for e in pending.values():
        if e.uid not in definitions:needed.update(_references(e,terms,index))
    # Labels with equal source and reference-language identity will be reused
    # by align_translations after the first phase. Pay for one representative.
    slots={slot['uid']:slot for slot in scan.consistency_index['slots']}
    result=[];seen=set()
    for e in definitions.values():
        if e.source not in needed:continue
        slot=slots[e.uid];refs=slot.get('refs')
        identity=(slot['role'],e.source,refs) if refs else ('uid',e.uid)
        if identity not in seen:
            result.append(e);seen.add(identity)
    return result
