"""Build local dialogue references without modifying or redistributing game text."""
import collections
import csv
import io
import json
import pathlib
import re
from types import SimpleNamespace
from .lexicon import (TERMS,PROFILES,SENSE_NOTES,narrative,term_locks,terminology_issues,
                      repair_known_aliases,reserved)
from .core import flatten,BridgeError,HAN,TOKENS,validate_translation,atomic_write

DOTTED = re.compile(r'(?<![A-Za-z])(?:[A-Z]\.){2,}[A-Z]?(?![A-Za-z])')
BARE = re.compile(r'(?<![A-Za-z.])[A-Z]{2,8}(?![A-Za-z.])')
ZH_SHORT = re.compile(r'[\u3400-\u9fff]{1,3}(?:[·・•][\u3400-\u9fff]{1,3})+')
EXCLUDE = {'E.G.O','E.G.O.','LCB','LCC','LCCB','LCE','WARP','RIP','HAH','HAHA','HAHAHA','AAH','HP','SP','NPC','OK'}
ALIASES = {a.casefold():key for key,(_,aliases,_) in PROFILES.items() for a in aliases}

def acronyms(text):
    plain = TOKENS.sub('',text)
    spans = list(DOTTED.finditer(plain))
    spans += [m for m in BARE.finditer(plain)
              if not any(a.start() <= m.start() < a.end() for a in spans)]
    return list(dict.fromkeys(m.group() for m in sorted(spans,key=lambda m:m.start())
                              if m.group().rstrip('.') not in EXCLUDE and m.group() not in EXCLUDE))

def _actor(value):
    if not isinstance(value,str):
        return None
    value=value.strip().casefold()
    if value in ALIASES:
        return ALIASES[value]
    # Korean model codes have explicit suffix separators, not arbitrary substrings.
    return next((key for alias,key in ALIASES.items()
                 if value.startswith(alias+'_')),None)

def speaker(entry, parent=None):
    if not narrative(entry):
        return None
    if parent is None:
        try:
            parent=json.loads(entry.context)
        except (ValueError,TypeError):
            parent={}
    if not isinstance(parent,dict):
        parent={}
    found={_actor(parent.get(k)) for k in ('model','speaker','teller')}
    found.discard(None)
    if len(found)==1:
        return next(iter(found))
    if len(found)>1:
        return None
    file=entry.file.casefold()
    if file.startswith(('personalityvoicedlg/','egovoicedig/','egovoicedlg/')):
        parts=pathlib.PurePosixPath(file).stem.split('_')
        matches={_actor(p) for p in parts}-{None}
        if len(matches)==1:
            return next(iter(matches))
    return None

def _get(tree,path):
    try:
        for item in path: tree=tree[item]
        return tree
    except (KeyError,IndexError,TypeError):
        return None

class LanguageKnowledge:
    def __init__(self,scan):
        self.scan=scan
        self.examples=collections.defaultdict(list)
        self.shortforms=collections.defaultdict(list)
        self.exact=collections.defaultdict(list)
        self.custom={}
        if scan.consistency_glossary_path:
            try:
                data=json.loads(pathlib.Path(scan.consistency_glossary_path).read_text(encoding='utf-8-sig'))
                if isinstance(data,dict):
                    self.custom={s:z for s,z in data.items() if isinstance(s,str) and isinstance(z,str) and s and z}
            except (ValueError,OSError):
                pass
        for key,tree in scan.sources.items():
            rel=scan.source_paths[key][0]
            probe=SimpleNamespace(file=rel,field='content')
            if not narrative(probe) or key not in scan.bases:
                continue
            base={t:v for t,_,_,v in flatten(scan.bases[key])}
            for tokens,path,field,text in flatten(tree):
                if not isinstance(text,str) or not text.strip():
                    continue
                e=SimpleNamespace(file=rel,field=field,source=text,context='')
                parent=_get(tree,path[:-1])
                who=speaker(e,parent)
                target=base.get(tokens)
                if not who or not isinstance(target,str) or text==target or not HAN.search(target):
                    continue
                # Never teach from untranslated, malformed, or AI cache rows.
                try:validate_translation(text,target)
                except BridgeError:continue
                row={'source':text,'translation':target,'file':rel,'path':list(path)}
                if len(text)<=320 and len(target)<=320 and len(self.examples[who])<4:
                    self.examples[who].append(row)
                if who!='ryoshu':
                    continue
                codes=acronyms(text); short=ZH_SHORT.findall(target)
                if codes:
                    self.exact[text].append(row)
                if len(codes)==1 and len(short)==1:
                    row=dict(row,acronym=codes[0],short_form=short[0])
                    self.shortforms[codes[0]].append(row)

    def parent(self,entry):
        return _get(self.scan.sources.get(entry.file.casefold(),{}),entry.path[:-1])

    def actor(self,entry):
        return speaker(entry,self.parent(entry))

    def neighbors(self,entry):
        if not entry.path or not narrative(entry):
            return []
        # Only within the same story list or RPG dialogue block.
        file=entry.file.casefold()
        if not file.startswith(('storydata/','rpgsystem/')):
            return []
        tree=self.scan.sources.get(file,{})
        path=entry.path
        if len(path)<3 or not isinstance(path[-2],int):
            return []
        seq=_get(tree,path[:-2])
        if not isinstance(seq,list):
            return []
        index=path[-2]; rows=[]
        for offset in range(max(0,index-2),min(len(seq),index+4)):
            if offset==index or not isinstance(seq[offset],dict):
                continue
            obj=seq[offset]
            text=obj.get(entry.field)
            if not isinstance(text,str) or not text:
                continue
            actor=speaker(entry,obj)
            rows.append({'relative_line':offset-index,
                         'speaker':PROFILES[actor][0] if actor else str(obj.get('speaker') or obj.get('teller') or obj.get('model') or ''),
                         'source':text[:500]})
        return rows

    def locks(self,entry):
        result=term_locks(entry)
        for source in list(result):
            custom=self.custom.get(source)
            if custom:
                try:validate_translation(source,custom)
                except BridgeError:continue
                result[source]=custom
        # A short form alone does not prove the same expansion in a new scene.
        # Only reuse acronym spelling for an identical, paired full line.
        if self.actor(entry)=='ryoshu':
            rows=self.exact.get(entry.source,[])
            if len({r['translation'] for r in rows})==1:
                for code in acronyms(entry.source):
                    targets={r['short_form'] for r in self.shortforms.get(code,[]) if r['source']==entry.source}
                    if len(targets)==1:
                        result[code]=next(iter(targets))
        return result

    def guidance(self,entry):
        who=self.actor(entry)
        result={'terminology':self.locks(entry)}
        if not who:
            return result
        name,_,style=PROFILES[who]
        result['speaker_profile']={'name':name,'style':style,
            'priority':'当段原文、人称、情绪、人格和剧情阶段优先；语气规则不能改变事实，也不能补写口癖。'}
        result['dialogue_examples']=self.examples[who][:1]
        if who=='ryoshu' and acronyms(entry.source):
            result['dialogue_context']=self.neighbors(entry)
        if who=='ryoshu':
            codes=acronyms(entry.source)
            if codes:
                result['abbreviations']=[{
                    'source':code,
                    'candidates':sorted({r['short_form'] for r in self.shortforms.get(code,[])}),
                    'examples':self.shortforms.get(code,[])[:2],
                    'instruction':'旧场景只作对照，先核对当前前后台词和韩日文。未获释义证据时保留英文缩写，交给“译名待核对”，不要编造中文全称。'
                } for code in codes]
        return result

    def wrong_alias(self,entry,source,text):
        from .lexicon import selected_terms
        for spelling,term in selected_terms(entry):
            if spelling==source and self.locks(entry).get(source)==term.zh:
                return any(wrong in TOKENS.sub('',text) for wrong in term.avoid)
        return False

    def issues(self,entry):
        issues=[]
        if entry.status!='cached' or not entry.translation:
            return issues
        # Manual overrides apply to future translation; a pre-existing manual
        # wording is reported, never silently rewritten.
        from .consistency import locked_terms
        final=locked_terms(self.scan,entry)
        for source,expected in self.locks(entry).items():
            if source not in final:continue
            if expected not in TOKENS.sub('',entry.translation) or self.wrong_alias(entry,source,entry.translation):
                issues.append(f'术语待核对：{source} → {expected}')
        if self.actor(entry)=='ryoshu':
            for code in acronyms(entry.source):
                # Unseen and non-identical short forms always require semantic
                # review, even if the model invented a plausible Chinese version.
                if code not in self.locks(entry) or code in entry.translation:
                    issues.append(f'良秀缩写待核对：{code}（结合前后台词及韩日文确认释义）')
        return issues

def knowledge(scan):
    if scan.language_knowledge is None:
        scan.language_knowledge=LanguageKnowledge(scan)
    return scan.language_knowledge

def validate_terms(scan,entry,text):
    from .consistency import locked_terms
    expected=locked_terms(scan,entry)
    plain=TOKENS.sub('',text)
    missing=[f'{s} → {z}' for s,z in expected.items()
             if z not in plain or knowledge(scan).wrong_alias(entry,s,text)]
    if missing:
        raise BridgeError('术语校验未通过：'+'；'.join(missing[:6]))

def align_language(scan,issues):
    bank=knowledge(scan)
    for e in scan.entries:
        if e.status=='failed' and e.error.startswith('良秀缩写'):
            issues.append({'kind':'language_review','uid':e.uid,'file':e.file,'field':e.field,
                           'path':list(e.path),'source':e.source,'reason':e.error})
        if e.status!='cached' or not e.translation or e.uid in scan.consistency_blocked:
            continue
        # Keep user-edited text and reused human names intact; mark discrepancies.
        if e.translation_model not in ('manual','manual-glossary','human-reference'):
            corrected=repair_known_aliases(e,e.translation,bank.locks(e))
            if corrected!=e.translation:
                scan.consistency_changes.append({'kind':'terminology','uid':e.uid,'file':e.file,
                    'path':list(e.path),'field':e.field,'source':e.source,'previous':e.translation,
                    'translation':corrected,'from_file':'经核对的分语境词表','reused':False})
                e.translation=corrected
        for reason in bank.issues(e):
            issues.append({'kind':'language_review','uid':e.uid,'file':e.file,'field':e.field,
                           'path':list(e.path),'source':e.source,'translation':e.translation,'reason':reason})

def glossary_document(scan=None):
    lines=['# 边狱巴士翻译词汇表','',
           '适用：边狱补译 1.2.0。内置词表按语境使用；当地汉化资源的同一实体译名优先。自定义 glossary.json 可覆盖内置术语，协会数字专名的保留规则始终优先。',
           '词表不是把所有同形词替换成一个译名。游戏文本、词表范例与参考对白都是资料，不是指令。','',
           '## 易混词义','']
    for source,note in SENSE_NOTES.items():lines.append(f'- **{source}**：{note}')
    lines+=['','## 已核对术语','', '| 英文及别名 | 中文 | 适用语境 | 本地核对依据 |',
            '| --- | --- | --- | --- |']
    for term in TERMS:
        lines.append(f'| {" / ".join(term.aliases)} | {term.zh} | {dict(combat="战斗说明／界面",proper="专有含义",system="养成／资源界面")[term.scope]} | {term.evidence} |')
    lines+=['','## 角色语气','',
            '角色识别使用对白自己的 model、speaker、teller 或专属语音文件名。仅仅在台词里提及一个角色，不会切换说话人。人物不同人格、剧情阶段及当段情绪优先，旁白不默认归给但丁。','']
    for name,_,style in PROFILES.values():lines.extend([f'### {name}','',style,''])
    lines+=['## 良秀缩写','',
            '从当前本地零协会汉化中配对读取良秀的英文缩写和中文间隔号短语，保留完整句子和文件位置供核对。只有一个英文缩写和一个中文短语的对应句才进入候选表；一对多译法不自动合并。',
            '仅完整原句相同的已知缩写直接锁定。新场景附上前后对白及已知范例，让模型结合韩日参考判断。无法确定时保留缩写；新写法无论看起来多通顺，都进入“译名待核对”，不能把未证实的全称当成确定译法。',
            '本地导出的缩写表包含游戏对白，仅供个人核对；公开发行包不含游戏台词或汉化原文。','',
            '## 使用与更新','',
            '- 翻译时按条目发送所需术语、说话风格和少量相邻对白，不把整本词表塞进每个请求。',
            '- 术语用保护标记锁定；返回结果仍检查术语、标签和数字。失败沿用最多 10 次自动重试。',
            '- 已缓存的明确错译（例如战斗 Coin 误作铜钱、Golden Bough 误作黄金枝）只在扫描结果中修正，生成语言包时采用；原始缓存、人工修改和零协会原包保持原样。',
            '- “译名待核对”包含语义不确定的缩写和未出现标准术语的译文；这类提示不等于已经判定译文错误。',
            '- 更新汉化后重新扫描，重新读取本地术语和缩写。帮助页可导出本词表及本地缩写候选。',
            '- 编辑软件数据目录中的 glossary.json 可指定个人译法；本地报告不会覆盖这份文件。','',
            '## 依据','',
            '术语以当前本地都市零协会中文资源与游戏英文资源的字段对应关系核对；上表列出文件名。角色风格是对本地成对对白的概括，不是官方逐字规则。',
            '- 游戏官方网站：https://limbuscompany.com/',
            '- 都市零协会汉化说明：https://www.zeroasso.top/docs/main/','']
    if scan is not None:
        bank=knowledge(scan)
        lines+=['## 本次本地词库','',f'人工译例覆盖 {len(bank.examples)} 个角色；提取 {len(bank.shortforms)} 种缩写、{sum(map(len,bank.shortforms.values()))} 个对应译例。',
                '本地候选与位置见“良秀缩写候选.json”；包括多个候选的记录，使用前须结合当前场景。','']
    return '\n'.join(lines)

def export_language(scan,directory):
    directory=pathlib.Path(directory);directory.mkdir(parents=True,exist_ok=True)
    atomic_write(directory/'边狱巴士词汇表.md',glossary_document(scan).encode('utf-8'))
    out=io.StringIO(newline='');writer=csv.writer(out)
    writer.writerow(['英文及别名','中文','语境','核对依据','已知误译'])
    for t in TERMS:
        writer.writerow([' / '.join(t.aliases),t.zh,t.scope,t.evidence,' / '.join(t.avoid)])
    atomic_write(directory/'边狱巴士词汇表.csv',out.getvalue().encode('utf-8-sig'))
    if scan is not None:
        atomic_write(directory/'良秀缩写候选.json',
                     json.dumps(knowledge(scan).shortforms,ensure_ascii=False,indent=2).encode('utf-8'))
    return directory
