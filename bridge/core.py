from __future__ import annotations

import collections
import copy
import csv
import hashlib
import io
import json
import os
import pathlib
import re
import shutil
import sqlite3
import subprocess
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any
from .proper_names import NAME_PATTERN, strip_names, names_preserved
from .scan_rules import resource_groups, resource_group, canonical_resources, engine_note
from .resource_schema import rpg_kind, rpg_text_field, rpg_hidden_row

PACK_NAME = 'LimbusAI_zh-CN'
OWNER = 'limbus-ai-bridge-v1'
PACK_RULES_VERSION = 4
MARKER = '.limbus-ai-bridge.json'
TEXT_FIELDS = set('teller dialog title prevDesc eventDesc behaveDesc successDesc failureDesc content name clue story desc subDesc message messageDesc result dlg summary undefined flavor mainText subText text rawDesc description abnormalityName simpleDesc sentence add min specialName panicName lowMoraleDescription panicDescription nameWithTitle skinItemTitle skinItemDesc teacher longName shortName nickName abName company area chapter chaptertitle timeline place parttitle openCondition relatedChapterText askLevelUp openConditionNumber'.split())
TECH_FIELDS = set('id key usage codeName iconId iconID variation variation2 colorCode outlineColorCode mainTextColor mainTextGlowColor debugNodeId debugNodeID songWriter keywords chapterNumber imgStr model'.split())
IDENTITY_KEYS = ('id', 'ID', 'level', 'coinIndex', 'index', 'key')
HANGUL = re.compile('[\uac00-\ud7af]')
HAN = re.compile('[\u3400-\u9fff]')
LEXICAL = re.compile('[A-Za-z\u3400-\u9fff\u3040-\u30ff\uac00-\ud7af]')
# Match game tokens, not Dante's angle-bracket dialogue or human-readable [On Hit].
TOKENS = re.compile(r'</?(?:color|size|b|i|u|s|sprite|link|align|alpha|br|cspace|font|font-weight|indent|line-height|line-indent|margin|mark|mspace|nobr|noparse|page|pos|rotate|space|style|sub|sup|voffset|width)(?=[\s=>/])[^<>\r\n]*>|\{[^{}\r\n]+\}|\[[A-Za-z_][A-Za-z0-9_.:-]*\]|(?<=%)\{[^{}]+\}|/\%|%(?=\{)|\r\n|\n|\\n|\\r|\r', re.I)
PROTECTED_TEXT = re.compile(TOKENS.pattern+'|'+NAME_PATTERN, re.I)
MASK = re.compile(r'⟦P\d{4}⟧')
NUMBERS = re.compile(r'(?<![A-Za-z])[-+]?\d+(?:[.,]\d+)*(?:%|％)?')

class BridgeError(Exception):
    pass

class Cancelled(BridgeError):
    pass

def check_cancel(stop):
    if stop and stop.is_set():
        raise Cancelled('任务已停止；已完成的翻译已保存，可继续。')

def digest(value: bytes | str) -> str:
    return hashlib.sha256(value.encode('utf-8') if isinstance(value, str) else value).hexdigest()

def dumps(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')

def read_json(path):
    try:
        return json.loads(pathlib.Path(path).read_text(encoding='utf-8-sig'))
    except (ValueError, UnicodeError) as exc:
        raise BridgeError(f'JSON 无法读取：{pathlib.Path(path).name}（{exc}）') from exc

def ensure_plain_path(path):
    """Never follow junctions, symlinks or other reparse points in managed writes."""
    path = pathlib.Path(path).absolute()
    for p in (path, *path.parents):
        if p.exists() or p.is_symlink():
            stat = p.lstat()
            if p.is_symlink() or getattr(stat, 'st_file_attributes', 0) & 0x400:
                raise BridgeError(f'出于文件保护，拒绝处理链接/联接路径：{p}')
    return path

def safe_child(root, relative):
    rel = pathlib.PurePosixPath(str(relative).replace('\\', '/'))
    if rel.is_absolute() or any(p in ('..', '') or ':' in p for p in rel.parts):
        raise BridgeError(f'非法相对路径：{relative}')
    root = pathlib.Path(root).absolute()
    target = root.joinpath(*rel.parts)
    if not target.is_relative_to(root):
        raise BridgeError('路径越界')
    return ensure_plain_path(target)

def atomic_write(path, raw: bytes):
    path = ensure_plain_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    with temp.open('xb') as f:
        f.write(raw)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp, path)

def file_map(root, suffix=None):
    root = ensure_plain_path(root)
    result = {}
    if not root.is_dir():
        raise BridgeError(f'找不到目录：{root}')
    for folder, dirs, files in os.walk(root, followlinks=False):
        for name in dirs:
            ensure_plain_path(pathlib.Path(folder)/name)
        for name in files:
            p = ensure_plain_path(pathlib.Path(folder)/name)
            if suffix is not None and p.suffix.lower() != suffix:
                continue
            rel = p.relative_to(root).as_posix()
            key = rel.casefold()
            if key in result:
                raise BridgeError(f'大小写冲突的文件：{rel}')
            result[key] = (rel, p)
    return result

def language_files(root, lang):
    result = {}
    for _, (rel, p) in file_map(root, '.json').items():
        parts = pathlib.PurePosixPath(rel)
        name = parts.name
        if name.upper().startswith(lang.upper() + '_'):
            name = name[len(lang) + 1:]
        rel = str(parts.with_name(name))
        if rel.casefold() in result:
            raise BridgeError(f'移除语言前缀后文件名冲突：{rel}')
        result[rel.casefold()] = (rel, p)
    return result

def text_field(rel,name):
    return name in TEXT_FIELDS or rpg_text_field(rel,name)


def legacy_rpg_id(rel,tokens,path):
    if (rpg_kind(rel) and len(tokens)>1 and tokens[0]==('key','dataList')
            and tokens[1][:2]==('row','key') and len(path)>1):
        return stable_id(rel,(tokens[0],('index',path[1]),*tokens[2:]))
    return None


def list_key(items):
    if not items or not all(isinstance(v, dict) for v in items):
        return None
    items = [v for v in items if v]
    if not items: return None
    for key in IDENTITY_KEYS:
        if any(key in v for v in items):
            return key
    return None

def row_tokens(items):
    key = list_key(items)
    if not key: return [('index',i) for i in range(len(items))]
    counts = collections.Counter(str(v[key]) for v in items if key in v)
    result = []
    for i,v in enumerate(items):
        if not v:
            result.append(('empty',i)); continue
        if key not in v or not isinstance(v[key],(str,int,float)) or isinstance(v[key],bool):
            result.append(('unsafe',i)); continue
        token = ('row',key,str(v[key]))
        if counts[str(v[key])] > 1:
            # Story data can reuse line IDs for different actor models.
            model = v.get('model')
            if not isinstance(model,str):
                result.append(('unsafe',i)); continue
            token += ('model',model)
        result.append(token)
    duplicates=collections.Counter(result)
    result=[('unsafe',i) if duplicates[token]>1 else token for i,token in enumerate(result)]
    return result

def unsafe_rows(value, path=()):
    if isinstance(value,dict):
        for k,v in value.items(): yield from unsafe_rows(v,path+(k,))
    elif isinstance(value,list):
        for i,(v,token) in enumerate(zip(value,row_tokens(value))):
            if token[0]=='unsafe': yield path+(i,)
            else: yield from unsafe_rows(v,path+(i,))

def flatten(value, tokens=(), path=(), field_name=''):
    """Stable identities survive insertion/reordering of game rows and levels."""
    if isinstance(value, dict):
        for k, v in value.items():
            yield from flatten(v, tokens + (('key', k),), path + (k,), k)
    elif isinstance(value, list):
        for i, (v,token) in enumerate(zip(value,row_tokens(value))):
            if token[0]=='unsafe': continue
            yield from flatten(v, tokens + (token,), path + (i,), field_name)
    else:
        yield tokens, path, field_name, value

def stable_id(rel, tokens):
    return json.dumps([rel.casefold(), tokens], ensure_ascii=False, separators=(',', ':'))

def strip_tokens(text):
    return TOKENS.sub('', text)

def translatable(text):
    return bool(LEXICAL.search(strip_names(strip_tokens(text))))

def classify(source, target, present):
    if not translatable(source):
        return None
    if not present:
        return 'missing'
    if target is None or isinstance(target, str) and not target.strip():
        return 'empty'
    if not isinstance(target, str):
        return 'schema'
    if target.strip() in ('待翻译', '待汉化', '未翻译', '未汉化', 'TODO', '待译'):
        return 'placeholder'
    if target == source:
        # Unchanged Korean often denotes engine notes, retained by the human pack.
        return 'same'
    remaining = strip_names(strip_tokens(target))
    if HANGUL.search(remaining):
        # Chinese mixed with Korean is not sufficient evidence of missing text.
        return 'mixed' if HAN.search(remaining) else 'foreign'
    return None

def protect(text, *, numbers=False, terms=None):
    if MASK.search(text):
        raise BridgeError('原文含有保护标记，需手动处理此条')
    tokens = []
    terms=terms or {}
    def substitute(match):
        tokens.append(terms.get(match.group(0),match.group(0)))
        return f'⟦P{len(tokens)-1:04d}⟧'
    term_patterns=[]
    for source,value in sorted(terms.items(),key=lambda p:-len(p[0])):
        validate_translation(source,value)
        # Preserve numeric tokens and engine syntax; known semantic names use
        # the same ordered protection markers with their canonical translation.
        term_patterns.append((r'(?<![A-Za-zÀ-ÖØ-öø-ÿ0-9_])' if source[0].isalnum() else '')+re.escape(source)+(r'(?![A-Za-zÀ-ÖØ-öø-ÿ0-9_])' if source[-1].isalnum() else ''))
    pieces=[PROTECTED_TEXT.pattern]
    if term_patterns:pieces.append('(?-i:'+'|'.join(term_patterns)+')')
    if numbers:pieces.append(NUMBERS.pattern)
    pattern=re.compile('|'.join(pieces),re.I)
    return pattern.sub(substitute, text), tokens

def restore(text, tokens):
    wanted = [f'⟦P{i:04d}⟧' for i in range(len(tokens))]
    if MASK.findall(text) != wanted:
        raise BridgeError('AI 改动、遗漏或重排了保护标记，已拒绝此条')
    result = text
    for token, original in zip(wanted, tokens):
        result = result.replace(token, original)
    return result

def validate_translation(source, text):
    if not isinstance(text, str) or not text.strip():
        raise BridgeError('译文为空或不是字符串')
    if len(text) > max(600, len(source) * 8):
        raise BridgeError('译文异常过长')
    if TOKENS.findall(source) != TOKENS.findall(text):
        raise BridgeError('译文的标签、变量或换行与原文不一致')
    if not names_preserved(source,text):
        raise BridgeError('译文改动了协会专名；Hana、Zwei 等须保留原文拼写')
    if collections.Counter(NUMBERS.findall(strip_tokens(source))) != collections.Counter(NUMBERS.findall(strip_tokens(text))):
        raise BridgeError('译文改动了数字，已拒绝此条')
    if HANGUL.search(strip_names(strip_tokens(text))):
        raise BridgeError('译文仍含韩文，需重译或手动审校')
    if translatable(source) and not HAN.search(strip_tokens(text)):
        raise BridgeError('译文没有中文；若属于专有名称，请保留原文并忽略此条')
    if MASK.search(text):
        raise BridgeError('译文含未还原的保护标记')

@dataclass
class Entry:
    uid: str
    file: str
    tokens: tuple
    path: tuple
    field: str
    source: str
    target: str | None
    reason: str
    active: bool
    context: str = ''
    refs: dict = field(default_factory=dict)
    translation: str = ''
    status: str = 'pending'
    error: str = ''
    newly_seen: bool = False
    translation_model: str = ''
    translation_created: float = 0.0
    consistency_note: str = ''

    @property
    def cache_hash(self):
        # Changes to KR/JP references also invalidate old AI output.
        return digest(json.dumps([self.source, self.refs], ensure_ascii=False, sort_keys=True))

    @property
    def candidate(self):
        return self.active and self.reason in ('missing', 'placeholder', 'foreign')

    @property
    def recommended(self):
        # A structural difference alone does not establish a new game update.
        return self.candidate and self.newly_seen

    @property
    def coverage_gap(self):
        return self.candidate and bool(rpg_kind(self.file))

    @property
    def needs_translation(self):
        return (self.recommended or self.coverage_gap) and self.status not in ('cached','ignored')

    @property
    def category(self):
        name = pathlib.PurePosixPath(self.file).name.casefold()
        if rpg_kind(self.file): return '主线剧情'
        if 'gacha' in name: return '卡池'
        if name.startswith(('bufs','buffabilities','battlekeywords','keyword','skilltag','unitkeyword')): return '关联术语'
        if self.file.startswith('EGOVoiceDig/') or name.startswith(('ego.json','egos','ego-','egos-','ego_')) and not name.startswith(('egogift','ego_gift')) or ('ego' in name and ('skill' in name or 'passive' in name)):
            return 'E.G.O'
        if self.file.startswith('StoryData/'):
            if name == 'projectgs.json': return '其他'
            return '人格' if re.fullmatch(r'p\d+.*\.json', name) else '主线剧情'
        if self.file.startswith('PersonalityVoiceDlg/') or any(x in name for x in ('personalit','character','introducecharacter')) or name in ('skills.json','passives.json'):
            return '人格'
        if any(x in name for x in ('enemies','enemy','abnormality','abnormalities','panic','abguide')):
            return '敌方'
        if name.startswith(('story','stagechapter','stagepart','stagenode','abdlg')): return '主线剧情'
        return '其他'

    def public(self):
        return {'uid': self.uid, 'file': self.file, 'category': self.category, 'path': list(self.path), 'field': self.field,
                'source': self.source, 'target': self.target, 'reason': self.reason, 'active': self.active,
                'refs': self.refs, 'translation': self.translation, 'status': self.status, 'error': self.error,'newly_seen':self.newly_seen,'recommended':self.recommended,'candidate':self.candidate,'coverage_gap':self.coverage_gap,'needs_translation':self.needs_translation,'consistency_note':self.consistency_note}

@dataclass
class Scan:
    game: pathlib.Path
    baseline: pathlib.Path
    source_lang: str
    entries: list[Entry]
    sources: dict
    bases: dict
    source_paths: dict
    base_paths: dict
    fingerprints: dict
    warnings: list[str]
    version: str
    signature: str
    preserved: int = 0
    exclusions: list = field(default_factory=list)
    status_terms: dict = field(default_factory=dict)
    status_alignment_changes: list = field(default_factory=list)
    status_alignment_conflicts: list = field(default_factory=list)
    resource_groups: dict = field(default_factory=dict)
    consistency_index: Any = field(default=None,repr=False)
    consistency_terms: dict = field(default_factory=dict)
    consistency_term_index: dict = field(default_factory=dict)
    consistency_changes: list = field(default_factory=list)
    consistency_conflicts: list = field(default_factory=list)
    consistency_glossary_path: Any = None
    consistency_blocked: set = field(default_factory=set)
    language_knowledge: Any = field(default=None,repr=False)

    def summary(self):
        return {'source_files': len(self.sources), 'baseline_files': len(self.bases), 'version': self.version,
                'recommended': sum(e.recommended and e.status not in ('cached', 'ignored') for e in self.entries),
                'coverage_missing':sum(e.coverage_gap and e.status not in ('cached','ignored') for e in self.entries),
                'pending':sum(e.needs_translation for e in self.entries),
                'cached': sum(e.status == 'cached' for e in self.entries), 'preserved': self.preserved,
                'review': sum(not e.recommended for e in self.entries),
                'historical': sum(e.candidate and not e.newly_seen for e in self.entries),
                'excluded': dict(collections.Counter(x['reason'] for x in self.exclusions)),
                'status_aligned':len({r['uid'] for r in self.status_alignment_changes}),
                'status_conflicts':sum(r.get('needs_review',True) for r in self.status_alignment_conflicts),
                'terms_aligned':len({r['uid'] for r in self.consistency_changes}),
                'term_conflicts':len(self.consistency_conflicts),
                'warnings': self.warnings}

class Cache:
    def __init__(self, directory):
        self.directory = ensure_plain_path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / 'translations.sqlite3'
        ensure_plain_path(self.path)
        with self.connect() as con:
            con.execute('CREATE TABLE IF NOT EXISTS translations (uid TEXT, source_hash TEXT, source TEXT, translated TEXT, model TEXT, created REAL, PRIMARY KEY(uid,source_hash))')
            con.execute('CREATE TABLE IF NOT EXISTS ignored (uid TEXT, source_hash TEXT, PRIMARY KEY(uid,source_hash))')
            con.execute('CREATE TABLE IF NOT EXISTS observed (scope TEXT, uid TEXT, text_hash TEXT, is_new INTEGER, PRIMARY KEY(scope,uid))')
            con.execute('CREATE TABLE IF NOT EXISTS scan_features (scope TEXT, name TEXT, PRIMARY KEY(scope,name))')
    @contextmanager
    def connect(self):
        connection=sqlite3.connect(self.path,timeout=30)
        try:
            with connection:
                yield connection
        finally:
            connection.close()
    def load(self, entries):
        with self.connect() as con:
            rows = {(a,b):(c,m,t) for a,b,c,m,t in con.execute('SELECT uid,source_hash,translated,model,created FROM translations')}
            ignored = set(con.execute('SELECT uid,source_hash FROM ignored'))
        for entry in entries:
            ident=(entry.uid,entry.cache_hash)
            legacy=legacy_rpg_id(entry.file,entry.tokens,entry.path)
            old_ident=(legacy,entry.cache_hash)
            cache_ident=ident if ident in rows else old_ident
            if ident in ignored or old_ident in ignored:
                entry.status = 'ignored'
            elif cache_ident in rows:
                value,model,created = rows[cache_ident]
                try: validate_translation(entry.source, value)
                except BridgeError: continue
                entry.translation = value
                entry.translation_model=model;entry.translation_created=created or 0.0
                entry.status = 'cached'
    def put(self, entry, translation, model):
        validate_translation(entry.source, translation)
        created=time.time()
        with self.connect() as con:
            con.execute('INSERT OR REPLACE INTO translations VALUES (?,?,?,?,?,?)', (entry.uid,entry.cache_hash,entry.source,translation,model,created))
            con.execute('DELETE FROM ignored WHERE uid=? AND source_hash=?',(entry.uid,entry.cache_hash))
            legacy=legacy_rpg_id(entry.file,entry.tokens,entry.path)
            if legacy:con.execute('DELETE FROM ignored WHERE uid=? AND source_hash=?',(legacy,entry.cache_hash))
        entry.translation = translation
        entry.translation_model=model;entry.translation_created=created
        entry.status = 'cached'
        entry.error = ''
    def ignore(self, entry, value=True):
        with self.connect() as con:
            if value:
                con.execute('INSERT OR IGNORE INTO ignored VALUES (?,?)',(entry.uid,entry.cache_hash))
            else:
                con.execute('DELETE FROM ignored WHERE uid=? AND source_hash=?',(entry.uid,entry.cache_hash))
                legacy=legacy_rpg_id(entry.file,entry.tokens,entry.path)
                if legacy:con.execute('DELETE FROM ignored WHERE uid=? AND source_hash=?',(legacy,entry.cache_hash))
        entry.status = 'ignored' if value else 'pending'

    def observe(self, scan):
        scope=digest(str(scan.game).casefold()+'|'+scan.source_lang)
        with self.connect() as con:
            prior={a:(b,c) for a,b,c in con.execute('SELECT uid,text_hash,is_new FROM observed WHERE scope=?',(scope,))}
            rpg_seen=con.execute('SELECT 1 FROM scan_features WHERE scope=? AND name=?',(scope,'rpg-key-v1')).fetchone() is not None
            rows=[]; new_flags={}
            for key,source in scan.sources.items():
                rel=scan.source_paths[key][0]
                for tokens,path,name,text in flatten(source):
                    if not text_field(rel,name) or not isinstance(text,str): continue
                    uid=digest(stable_id(rel,tokens)); hash_value=digest(text)
                    previous=prior.get(uid)
                    if previous is None and not rpg_seen:
                        legacy=legacy_rpg_id(rel,tokens,path)
                        if legacy:previous=prior.get(digest(legacy))
                    is_new=bool(prior) and (previous is None or previous[0]!=hash_value or previous[1])
                    # First support for this schema is a coverage repair, not evidence of a game update.
                    if rpg_kind(rel) and not rpg_seen and previous is None:is_new=False
                    rows.append((scope,uid,hash_value,int(is_new))); new_flags[uid]=is_new
            con.executemany('INSERT OR REPLACE INTO observed VALUES (?,?,?,?)',rows)
            con.execute('INSERT OR IGNORE INTO scan_features VALUES (?,?)',(scope,'rpg-key-v1'))
        for e in scan.entries: e.newly_seen=new_flags.get(digest(e.uid),False)

def signature(game, baseline, lang='en'):
    loc = pathlib.Path(game)/'LimbusCompany_Data/Assets/Resources_moved/Localize'
    h = hashlib.sha256()
    for root in [loc, pathlib.Path(baseline)]:
        for key, (_, p) in sorted(file_map(root).items()):
            stat = p.stat()
            h.update(f'{root}|{key}|{stat.st_size}|{stat.st_mtime_ns}\n'.encode('utf-8'))
    return h.hexdigest()

def scan_game(game, baseline=None, lang='en', cache=None, stop=None, progress=lambda _:None):
    game = ensure_plain_path(game)
    if not (game/'LimbusCompany.exe').is_file():
        raise BridgeError('所选目录不是游戏根目录，应包含 LimbusCompany.exe')
    loc = game/'LimbusCompany_Data/Assets/Resources_moved/Localize'
    baseline = ensure_plain_path(baseline or game/'LimbusCompany_Data/Lang/LLC_zh-CN')
    if (baseline/MARKER).exists() or baseline.name.casefold() == PACK_NAME.casefold():
        raise BridgeError('基准必须是零协会原始语言包，不能选择本工具生成的语言包')
    initial_signature = signature(game, baseline, lang)
    source_paths = language_files(loc/lang, lang)
    base_paths = file_map(baseline, '.json')
    remote = loc/'RemoteLocalizeFileList.json'
    groups = {}
    warnings = []
    if remote.exists():
        groups = resource_groups(read_json(remote))
    else:
        warnings.append('缺少 RemoteLocalizeFileList.json，无法自动排除旧测试文件。')
    sources = {}; bases = {}; fingerprints = {}; entries = []; preserved = 0; exclusions = []
    ref_paths = {other: language_files(loc/other, other) for other in ('kr','en','jp') if other != lang and (loc/other).is_dir()}
    unknown = collections.Counter()
    for count, (key,(rel,p)) in enumerate(sorted(source_paths.items())):
        check_cancel(stop)
        if count % 100 == 0: progress(f'正在扫描 {count}/{len(source_paths)} 个原文文件…')
        source_raw = p.read_bytes(); fingerprints[str(p)] = digest(source_raw)
        try:
            source = json.loads(source_raw.decode('utf-8-sig'))
            if not isinstance(source, dict): raise BridgeError('顶层不是 JSON 对象')
            fields = list(flatten(source))
            bp = base_paths.get(key)
            base = None
            if bp:
                raw = bp[1].read_bytes(); fingerprints[str(bp[1])] = digest(raw)
                base = json.loads(raw.decode('utf-8-sig'))
                if not isinstance(base,dict): raise BridgeError('中文 JSON 顶层不是对象')
            bf = {t:s for t,_,_,s in flatten(base)} if base is not None else {}
        except BridgeError as exc:
            warnings.append(f'{rel}：{exc}；此文件保留零协会版本，不做 AI 修改')
            continue
        except (ValueError, UnicodeError) as exc:
            raise BridgeError(f'{rel}：{exc}') from exc
        sources[key] = source
        if base is not None: bases[key] = base
        unsafe=list(unsafe_rows(source))+list(unsafe_rows(base)) if base is not None else list(unsafe_rows(source))
        if unsafe:
            warnings.append(f'{rel}：有 {len(unsafe)} 处重复/缺失标识的记录，仅这些记录保留原状，不做 AI 修改')
        active_file = bool(bp) or not groups or key in groups or rel.startswith('StoryData/') or bool(rpg_kind(rel))
        # Orphaned duplicate root files are not presumed to be in use.
        file_entries = []
        for tokens,path,name,text in fields:
            if not isinstance(text,str): continue
            if not text_field(rel,name):
                if name.strip() not in TECH_FIELDS and translatable(text): unknown[name] += 1
                continue
            reason = classify(text, bf.get(tokens), tokens in bf)
            if reason is None:
                if tokens in bf and bf[tokens]: preserved += 1
                continue
            if engine_note(rel,name,text) or rpg_hidden_row(rel,source,path):
                exclusions.append({'file':rel,'path':list(path),'reason':'engine_note'})
                continue
            if reason == 'schema':
                warnings.append(f'{rel}: {name} 字段类型不一致，已跳过')
                continue
            if rel.startswith('StoryData/') and reason == 'missing' and name in ('title','teller','place'):
                related=bf.get(tokens[:-1]+(('key','content'),))
                if isinstance(related,str) and HAN.search(related): reason='metadata'
            context = ''
            obj = source
            for step in path[:-1]: obj = obj[step]
            if isinstance(obj, dict):
                context = json.dumps({k:v for k,v in obj.items() if k in ('id','key','model','teller','speaker','title','name','displayName','place') and isinstance(v,(str,int))},ensure_ascii=False)
            if rpg_kind(rel) and len(path)>1 and path[0]=='dataList':
                context_data=json.loads(context or '{}')
                context_data['block_key']=source['dataList'][path[1]].get('key','')
                context=json.dumps(context_data,ensure_ascii=False)
            file_entries.append(Entry(stable_id(rel,tokens),rel,tokens,path,name,text,bf.get(tokens),reason,active_file,context))
        # Reference languages are used only for candidate fields.
        if file_entries:
            for other, paths in ref_paths.items():
                if key not in paths: continue
                try:
                    rp = paths[key][1]; raw = rp.read_bytes(); fingerprints[str(rp)] = digest(raw)
                    rf = {t:s for t,_,_,s in flatten(json.loads(raw.decode('utf-8-sig')))}
                    for entry in file_entries:
                        if isinstance(rf.get(entry.tokens),str) and rf[entry.tokens]: entry.refs[other] = rf[entry.tokens]
                except (ValueError,UnicodeError,BridgeError):
                    warnings.append(f'{rel}: {other} 参考文本无法对齐，已省略')
        entries.extend(file_entries)
    # Some official per-season files duplicate rows already localized in a main
    # table. Only identical source fields in the same resource family can cover
    # one another; matching an ID alone is never sufficient.
    wanted={}
    for e in entries:
        group=resource_group(e.file,groups)
        if e.reason=='missing' and group:
            wanted[(group,e.tokens,e.source)]=True
    coverage=collections.defaultdict(list)
    for key,base in bases.items():
        group=resource_group(source_paths[key][0],groups)
        if not group: continue
        translated={t:s for t,_,_,s in flatten(base)}
        for tokens,_,name,source in flatten(sources[key]):
            if not isinstance(source,str): continue
            lookup=(group,tokens,source)
            target=translated.get(tokens)
            if lookup in wanted and isinstance(target,str) and target.strip() and classify(source,target,True) is None:
                coverage[lookup].append((base_paths[key][0],target))
    filtered=[]
    for e in entries:
        matches=coverage.get((resource_group(e.file,groups),e.tokens,e.source),[]) if e.reason=='missing' else []
        if matches and len({value for _,value in matches})==1:
            names=sorted({name for name,_ in matches})
            kind='duplicate_resource' if any(pathlib.PurePosixPath(name).name.casefold()==pathlib.PurePosixPath(e.file).name.casefold() for name in names) else 'merged_table'
            exclusions.append({'file':e.file,'path':list(e.path),'reason':kind,'covered_by':names})
            continue
        # Old exports may exist in a wrong directory with outdated text. Do not
        # call them untranslated when the manifest selects a localized canonical
        # path. This is a path exclusion, not a claim that the old text is equal.
        if e.file.casefold() not in groups and e.file.casefold() not in bases:
            canonical=[key for key in canonical_resources(e.file,groups) if key in sources and key in bases]
            if canonical and resource_group(e.file,groups):
                exclusions.append({'file':e.file,'path':list(e.path),'reason':'outside_manifest_path',
                                   'canonical_resources':[base_paths[key][0] for key in canonical]})
                continue
        filtered.append(e)
    entries=filtered
    for name,n in unknown.items(): warnings.append(f'未识别文本字段 {name} 共 {n} 项，未自动修改')
    version_file = baseline/'Info/version.json'
    version = str(read_json(version_file).get('version','未知')) if version_file.exists() else '未知'
    if initial_signature != signature(game, baseline, lang):
        raise BridgeError('游戏或零协会文件正在更新，请更新完成后重新扫描')
    if cache: cache.load(entries)
    result=Scan(game,baseline,lang,entries,sources,bases,source_paths,base_paths,fingerprints,warnings,version,initial_signature,preserved,exclusions)
    result.resource_groups=groups
    if cache and hasattr(cache,'directory'):result.consistency_glossary_path=cache.directory/'glossary.json'
    from .consistency import align_translations
    align_translations(result)
    return result

MISSING = object()

def merge_tree(source, baseline, translations, rel, tokens=(), patches=None):
    if patches is None:
        patches=set()
        for uid in translations:
            filename,path=json.loads(uid)
            if filename!=rel.casefold(): continue
            path=tuple(tuple(t) for t in path)
            patches.update(path[:i] for i in range(len(path)+1))
        if baseline is None: baseline=MISSING
    if tokens not in patches:
        return copy.deepcopy(source if baseline is MISSING else baseline)
    if isinstance(source, dict):
        if baseline is not MISSING and not isinstance(baseline,dict):
            raise BridgeError(f'{rel}：对象结构与零协会译文不兼容')
        result = copy.deepcopy(source if baseline is MISSING else baseline)
        for k,v in source.items():
            child=tokens+(('key',k),)
            if child in patches:
                result[k] = merge_tree(v, result.get(k,MISSING), translations, rel, child, patches)
        return result
    if isinstance(source, list):
        if baseline is not MISSING and not isinstance(baseline,list):
            raise BridgeError(f'{rel}：数组结构不兼容')
        result = copy.deepcopy(source if baseline is MISSING else baseline)
        key = list_key(source)
        if key:
            if result and list_key(result) != key:
                raise BridgeError(f'{rel}：数组对应字段不一致')
            lookup = {token:i for i,token in enumerate(row_tokens(result))}
            for row,token in zip(source,row_tokens(source)):
                if token[0]=='unsafe': continue
                if tokens+(token,) not in patches: continue
                index = lookup.get(token)
                merged = merge_tree(row,result[index] if index is not None else MISSING,translations,rel,tokens+(token,),patches)
                if index is None: result.append(merged)
                else: result[index] = merged
        else:
            if result and list_key(result): raise BridgeError(f'{rel}：原文数组缺少对应字段')
            for i,v in enumerate(source):
                child=tokens+(('index',i),)
                if child not in patches: continue
                # Positional arrays need their preceding elements to preserve indexes.
                while len(result)<i: result.append(copy.deepcopy(source[len(result)]))
                merged = merge_tree(v,result[i] if i < len(result) else MISSING,translations,rel,child,patches)
                if i < len(result): result[i] = merged
                else: result.append(merged)
        return result
    uid = stable_id(rel,tokens)
    if isinstance(source,str) and uid in translations:
        # Re-check at the final write boundary: a human translation always wins.
        if classify(source,None if baseline is MISSING else baseline,baseline is not MISSING) is not None:
            return translations[uid]
    return copy.deepcopy(source if baseline is MISSING else baseline)

def game_running():
    if os.name != 'nt': return False
    result = subprocess.run(['tasklist','/FI','IMAGENAME eq LimbusCompany.exe','/FO','CSV','/NH'],capture_output=True,creationflags=0x08000000)
    if result.returncode != 0:
        raise BridgeError('无法确认游戏是否已退出，请重试')
    return b'limbuscompany.exe' in result.stdout.lower()

def assert_fresh(scan):
    if signature(scan.game,scan.baseline,scan.source_lang) != scan.signature:
        raise BridgeError('源文件自扫描后已变化。请重新扫描，以优先采用最新的零协会译文。')
    for name,expected in scan.fingerprints.items():
        if digest(pathlib.Path(name).read_bytes()) != expected:
            raise BridgeError('源文件内容发生变化，请重新扫描')

def payload(scan):
    from .consistency import align_translations
    align_translations(scan)
    translations = {}
    for e in scan.entries:
        if e.status == 'cached' and e.translation:
            validate_translation(e.source,e.translation)
            translations[e.uid] = e.translation
    by_file = collections.Counter(e.file.casefold() for e in scan.entries if e.uid in translations)
    # Begin with the exact human pack, including its fonts and license.
    output = {}
    for _,(rel,p) in file_map(scan.baseline).items():
        if rel.startswith('BackupFont/') or pathlib.PurePosixPath(rel).suffix.lower() in ('.exe','.dll','.bat','.ps1'):
            continue
        output[rel] = p.read_bytes()
    for key,n in by_file.items():
        rel = scan.base_paths[key][0] if key in scan.base_paths else scan.source_paths[key][0]
        merged = merge_tree(scan.sources[key],scan.bases.get(key),translations,scan.source_paths[key][0])
        raw = dumps(merged)
        json.loads(raw)
        output[rel] = raw
    if not any(name.startswith('Font/') and pathlib.PurePosixPath(name).suffix.lower() in ('.ttf','.otf') for name in output):
        raise BridgeError('零协会语言包内未找到可用字体，请先用原工具箱安装字体')
    note = ('Limbus AI Bridge：个人临时补译包\n'
            '已有汉化来源：都市零协会 LocalizeLimbusCompany\n'
            'https://github.com/LocalizeLimbusCompany/LocalizeLimbusCompany\n'
            '已有汉化遵循 CC BY-NC-SA 4.0，字体遵循各自许可证。\n'
            'AI 文本由用户自行配置的 API 生成，不代表零协会或 Project Moon。\n'
            f'零协会版本：{scan.version}；采用补译/术语复用条目：{len(translations)}\n')
    output['AI_Bridge_说明.txt'] = note.encode('utf-8')
    return output,len(translations)

def install_pack(scan, data_dir, stop=None, progress=lambda _:None, check_running=True):
    if check_running and game_running():
        raise BridgeError('请退出游戏后再生成语言包，以免游戏读取到更新中的文本')
    assert_fresh(scan)
    output, count = payload(scan)
    data_dir = ensure_plain_path(data_dir)
    stage = data_dir/'builds'/time.strftime('%Y%m%d-%H%M%S')/uuid.uuid4().hex[:8]
    stage.mkdir(parents=True,exist_ok=False)
    for name,raw in output.items():
        check_cancel(stop)
        p = safe_child(stage,name); p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(raw)
    assert_fresh(scan)
    destination = ensure_plain_path(scan.game/'LimbusCompany_Data/Lang'/PACK_NAME)
    marker_path = destination/MARKER
    previous = {}
    if destination.exists():
        if not marker_path.is_file():
            raise BridgeError(f'目标目录已存在且不属于本工具，未改动：{destination}')
        metadata = read_json(marker_path)
        if metadata.get('owner') != OWNER or pathlib.Path(metadata.get('game','')).absolute() != scan.game:
            raise BridgeError('语言包所有权校验失败，未改动任何已有文件')
        previous = metadata.get('files',{})
        actual = file_map(destination)
        for key,(name,p) in actual.items():
            if name == MARKER: continue
            if name not in previous or digest(p.read_bytes()) != previous[name]:
                raise BridgeError(f'检测到额外或手动修改的文件，已保留并停止覆盖：{name}')
    hashes = {name:digest(raw) for name,raw in output.items()}
    # Check all collisions before any writes; a removed managed file may be restored.
    for name in output:
        p = safe_child(destination,name)
        if p.exists() and name not in previous:
            raise BridgeError(f'拒绝覆盖非本工具创建的文件：{name}')
    check_cancel(stop)
    if check_running and game_running(): raise BridgeError('游戏已经启动，请退出后重试')
    backup = data_dir/'history'/time.strftime('%Y%m%d-%H%M%S')/uuid.uuid4().hex[:8]
    changed = []
    destination.mkdir(parents=True,exist_ok=True)
    for name in ('Font/Context','Font/Title'):
        safe_child(destination,name).mkdir(parents=True,exist_ok=True)
    # Once committing, finish or roll back rather than stopping halfway on cancel.
    try:
        if marker_path.exists():
            backup.mkdir(parents=True,exist_ok=True)
            shutil.copy2(marker_path,backup/MARKER)
        for i,(name,raw) in enumerate(output.items()):
            p = safe_child(destination,name)
            if p.exists() and previous.get(name) == hashes[name]: continue
            existed = p.exists()
            if existed:
                saved = safe_child(backup,name); saved.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(p,saved)
            changed.append((name,existed))
            atomic_write(p,raw)
            if i % 100 == 0: progress(f'写入独立语言包 {i}/{len(output)}…')
        for name in previous.keys()-output.keys():
            p = safe_child(destination,name)
            if p.exists():
                saved=safe_child(backup,name); saved.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(p,saved)
                retired=safe_child(data_dir/'retired'/uuid.uuid4().hex,name)
                retired.parent.mkdir(parents=True,exist_ok=True)
                shutil.move(str(p),str(retired))
                changed.append((name,True))
        atomic_write(marker_path,dumps({'owner':OWNER,'game':str(scan.game),'files':hashes,'baseline_version':scan.version,'source_signature':scan.signature,'ai_entries':count,'pack_rules_version':PACK_RULES_VERSION,'created':time.time()}))
    except Exception:
        for name,existed in reversed(changed):
            p = safe_child(destination,name)
            saved = safe_child(backup,name)
            if existed and saved.exists(): atomic_write(p,saved.read_bytes())
            elif not existed and p.exists():
                saved=safe_child(data_dir/'incomplete'/uuid.uuid4().hex,name)
                saved.parent.mkdir(parents=True,exist_ok=True); shutil.move(str(p),str(saved))
        if (backup/MARKER).exists(): atomic_write(marker_path,(backup/MARKER).read_bytes())
        raise
    receipt = {'output':str(destination),'files':len(output),'ai_entries':count,'baseline_version':scan.version,'backup':str(backup),'built_at':time.strftime('%Y-%m-%d %H:%M:%S'),'status_aligned':len({r['uid'] for r in scan.status_alignment_changes}),'status_conflicts':sum(r.get('needs_review',True) for r in scan.status_alignment_conflicts)}
    atomic_write(data_dir/'last-build.json',dumps(receipt))
    return receipt

def export_report(scan, data_dir):
    directory = pathlib.Path(data_dir)/'reports'/time.strftime('%Y%m%d-%H%M%S')
    directory.mkdir(parents=True,exist_ok=True)
    atomic_write(directory/'scan.json',dumps({'summary':scan.summary(),'entries':[e.public() for e in scan.entries],'exclusions':scan.exclusions,'status_alignment':scan.status_alignment_changes,'status_conflicts':scan.status_alignment_conflicts,'term_alignment':scan.consistency_changes,'term_conflicts':scan.consistency_conflicts}))
    buf=io.StringIO(newline=''); writer=csv.writer(buf)
    writer.writerow(['文件','字段位置','原因','推荐','状态','原文','现有译文','AI译文','错误'])
    for e in scan.entries:
        def safe(v):
            s=str(v or '')
            return "'"+s if s.startswith(('=','+','-','@')) else s
        writer.writerow([safe(v) for v in [e.file,e.path,e.reason,e.recommended,e.status,e.source,e.target,e.translation,e.error]])
    atomic_write(directory/'scan.csv',buf.getvalue().encode('utf-8-sig'))
    from .consistency import export_consistency_report
    export_consistency_report(scan,directory)
    from .language_knowledge import export_language
    export_language(scan,directory)
    return directory

def detect_game():
    candidates=[]
    if os.name == 'nt':
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,r'Software\Valve\Steam') as key:
                steam=pathlib.Path(winreg.QueryValueEx(key,'SteamPath')[0])
            candidates.append(steam/'steamapps/common/Limbus Company')
            lib=steam/'steamapps/libraryfolders.vdf'
            if lib.exists():
                for p in re.findall(r'"path"\s+"([^"]+)"',lib.read_text(encoding='utf-8')):
                    candidates.append(pathlib.Path(p.replace('\\\\','\\'))/'steamapps/common/Limbus Company')
        except OSError: pass
    for letter in ('E','D','F','C'):
        for name in ('Steam','SteamLibrary','Program Files (x86)/Steam'):
            candidates.append(pathlib.Path(f'{letter}:/{name}/steamapps/common/Limbus Company'))
    return next((str(p) for p in candidates if (p/'LimbusCompany.exe').is_file()),'')
