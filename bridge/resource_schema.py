"""Known exported schemas not listed in the legacy remote resource manifest."""
import pathlib
import re

_RPG_NAME=re.compile(r'rpg-loc-(dialogue-choice|dialogue|item|location|narration|npc|quest|ui)-.+\.json',re.I)

def rpg_kind(rel):
    path=pathlib.PurePosixPath(rel)
    if len(path.parts)!=2 or path.parts[0].casefold()!='rpgsystem':return ''
    match=_RPG_NAME.fullmatch(path.name)
    return match.group(1).lower() if match else ''

def rpg_text_field(rel,name):
    kind=rpg_kind(rel)
    return bool((kind=='dialogue' and name=='speaker')
                or (kind in ('npc','item') and name=='displayName')
                or (kind=='item' and name=='statText')
                or (kind=='quest' and re.fullmatch(r'goalDescription[1-9]\d*',name)))

def rpg_hidden_row(rel,source,path):
    # Explicit engine-only quest marker, not a heuristic based on Korean text.
    if rpg_kind(rel)!='quest' or len(path)<2 or path[0]!='dataList':return False
    rows=source.get('dataList',[])
    if not isinstance(rows,list) or not isinstance(path[1],int) or path[1]>=len(rows):return False
    row=rows[path[1]]
    return isinstance(row,dict) and '숨겨진 퀘스트' in str(row.get('description',''))
